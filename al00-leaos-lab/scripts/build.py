#!/usr/bin/env python3
"""Offline-only experimental AL00 repack. Never invokes adb/fastboot."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
WORK = ROOT / 'work'
OUT = ROOT / 'output'
REPORT = ROOT / 'reports'
SOURCE = REPO / 'LeaOS-OSS-20.0-20260815-harry.zip'
MIB = 1024 * 1024
PRODUCT_SIZE = 1400 * MIB
DEVICES = dict(system=1896, cust=88, odm=96, preas=136, product=1048, vendor=480)
GROUP = 'huawei_dynamic_partitions'
# Preserve the source's 1 MiB reserved prefix on every block device.
GROUP_SIZE = (sum(DEVICES.values()) - len(DEVICES)) * MIB


def run(args, name=None):
    p = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
    if name:
        (REPORT / (name + '.txt')).write_text(p.stdout)
    if p.returncode:
        raise RuntimeError(f'{args}: status {p.returncode}\n{p.stdout}')
    return p.stdout


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def ranges(line):
    v = list(map(int, line.split()[1].split(',')))
    assert v[0] == len(v) - 1 and v[0] % 2 == 0
    pairs = list(zip(v[1::2], v[2::2]))
    assert all(0 <= a < b for a, b in pairs)
    return pairs


def restore(br, transfer, target, size):
    lines = transfer.splitlines()
    assert lines[:1] == ['4'] and lines[2:4] == ['0', '0']
    proc = subprocess.Popen(['brotli', '-d', '-c', str(br)], stdout=subprocess.PIPE)
    count = 0
    with open(target, 'wb') as dst:
        dst.truncate(size)
        for line in lines[4:]:
            cmd = line.split()[0]
            assert cmd in ('new', 'zero', 'erase'), cmd
            for a, b in ranges(line):
                assert b * 4096 <= size
                if cmd != 'new':
                    continue
                count += b - a
                dst.seek(a * 4096)
                left = (b - a) * 4096
                while left:
                    data = proc.stdout.read(min(left, MIB))
                    assert data, 'truncated brotli stream'
                    dst.write(data)
                    left -= len(data)
        assert proc.stdout.read(1) == b'', 'unused data'
    assert proc.wait() == 0
    # Header count includes both new and zero operations in this full OTA.
    zeros = sum(b-a for l in lines[4:] if l.startswith('zero ') for a,b in ranges(l))
    assert count + zeros == int(lines[1])


def lp_parse(path):
    data = path.read_bytes()
    assert data[:4] == b'gDla'
    gs = struct.unpack_from('<I', data, 4)[0]
    geom = bytearray(data[:gs]); geom[8:40] = bytes(32)
    assert hashlib.sha256(geom).digest() == data[8:40]
    off = 4096
    magic, major, minor, hs = struct.unpack_from('<IHHI', data, off)
    assert magic == 0x414c5030 and (major, minor) == (10, 0)
    h = bytearray(data[off:off+hs]); h[12:44] = bytes(32)
    assert hashlib.sha256(h).digest() == data[off+12:off+44]
    ts = struct.unpack_from('<I', data, off+44)[0]
    table = data[off+hs:off+hs+ts]
    assert hashlib.sha256(table).digest() == data[off+48:off+80]
    result = {'geometry': list(struct.unpack_from('<III', data, 40)),
              'version': [major, minor], 'devices': [], 'partitions': [], 'groups': [], 'extents': []}
    for name, pos, fmt, expected in [('partitions',80,'<36sIIII',52),
                                    ('extents',92,'<QIQI',24),
                                    ('groups',104,'<36sIQ',48),
                                    ('devices',116,'<QIIQ36sI',64)]:
        start, count, es = struct.unpack_from('<III',data,off+pos)
        assert es == expected
        for i in range(count):
            row = struct.unpack_from(fmt,table,start+i*es)
            result[name].append([v.rstrip(b'\0').decode() if isinstance(v,bytes) else v for v in row])
    assert len(data) == off + hs + ts
    return result


def metadata(sizes, output):
    args = ['lpmake','--metadata-size','65536','--metadata-slots','2',
            '--super-name','system','--group',f'{GROUP}:{GROUP_SIZE}', '--output',output]
    for name, size in DEVICES.items():
        args += ['--device',f'{name}:{size*MIB}:1048576:0']
    for name in sorted(sizes):
        args += ['--partition',f'{name}:none:{sizes[name]}:{GROUP}']
    run(args, output.stem + '-lpmake')
    return args


def check_layout(info, sizes):
    devices = info['devices']; extents = info['extents']
    assert {d[4]: d[3] for d in devices} == {n:s*MIB for n,s in DEVICES.items()}
    assert all(d[0] == 2048 and d[5] == 0 for d in devices)
    occupied = {}
    for name, attrs, first, count, group in info['partitions']:
        assert attrs == 0
        own = extents[first:first+count]
        assert len(own) == count
        assert sum(e[0]*512 for e in own) == sizes[name]
        for sectors, kind, start, device in own:
            assert kind == 0 and 0 <= device < len(devices)
            assert start >= devices[device][0]
            assert (start+sectors)*512 <= devices[device][3]
            occupied.setdefault(device,[]).append((start,start+sectors))
    for spans in occupied.values():
        spans.sort()
        assert all(a[1] <= b[0] for a,b in zip(spans,spans[1:]))


def make_product_dat(img):
    # Full block OTA: explicitly write every byte, including zeroed free space.
    # Avoids requiring an external img2sdat and never references old partition data.
    size = img.stat().st_size
    assert size % 4096 == 0
    blocks = size // 4096
    lines = ['4',str(blocks),'0','0']
    for a in range(0,blocks,1024):
        lines.append(f'new 2,{a},{min(a+1024,blocks)}')
    transfer = '\n'.join(lines)+'\n'
    (OUT/'product.transfer.list').write_text(transfer)
    (OUT/'product.patch.dat').write_bytes(b'')
    run(['brotli','-q','6','-f','-o',OUT/'product.new.dat.br',img], 'product-compress')
    restore(OUT/'product.new.dat.br',transfer,WORK/'product-roundtrip.img',size)
    assert sha(img) == sha(WORK/'product-roundtrip.img')
    (WORK/'product-roundtrip.img').unlink()


def main():
    if not __debug__:
        raise RuntimeError("Run without -O/PYTHONOPTIMIZE; format checks require assertions.")
    if sha(SOURCE) != "9958ee9b21517538cbb42d7f1c79e96fb4449173945594d574516175ec17a81a":
        raise RuntimeError("Unknown source ROM SHA256; refusing to build.")
    for p in (WORK,OUT,REPORT,ROOT/'inputs'):
        p.mkdir(parents=True,exist_ok=True)
    report = {'status':'EXPERIMENTAL_OFFLINE_ONLY_NOT_DEVICE_TESTED','source_sha256':sha(SOURCE)}
    with zipfile.ZipFile(SOURCE) as z:
        ops = z.read('dynamic_partitions_op_list').decode()
        sizes = {n:int(s) for n,s in re.findall(r'^resize (\w+) (\d+)$',ops,re.M)}
        (ROOT/'inputs'/'unsparse_super_empty.img').write_bytes(z.read('unsparse_super_empty.img'))
        source_lp = lp_parse(ROOT/'inputs'/'unsparse_super_empty.img')
        report['source_lp'] = source_lp
        report['images'] = {}
        for name,size in sizes.items():
            br = WORK/(name+'.new.dat.br')
            with z.open(name+'.new.dat.br') as src, open(br,'wb') as dst:
                shutil.copyfileobj(src,dst)
            img = WORK/(name+'-original.img')
            restore(br,z.read(name+'.transfer.list').decode(),img,size)
            br.unlink()
            run(['e2fsck','-fn',img], name+'-original-fsck')
            run(['dumpe2fs','-h',img], name+'-original-ext4')
            with img.open('rb') as f:
                f.seek(-64,2); footer=f.read(64)
                f.seek(1024); sb=f.read(1024)
            block_size=1024<<struct.unpack_from('<I',sb,24)[0]
            blocks=struct.unpack_from('<I',sb,4)[0]
            fs_size=blocks*block_size
            with img.open('rb') as f:
                f.seek(fs_size); tail=f.read()
            report['images'][name]={'bytes':size,'sha256':sha(img),'filesystem_bytes':fs_size,
                                   'tail_all_zero':not any(tail),'avb_footer':footer[:4]==b'AVBf',
                                   'free_bytes':struct.unpack_from('<I',sb,12)[0]*block_size}
        original=WORK/'product-original.img'
        assert report['images']['product']['tail_all_zero'], 'Nonzero trailer requires explicit AVB handling'
        img=WORK/'product-1400MiB.img'
        shutil.copyfile(original,img)
        run(['resize2fs',img,'1400M'],'product-resize')
        run(['e2fsck','-fn',img],'product-resized-fsck')
        run(['dumpe2fs','-h',img],'product-resized-ext4')
        assert img.stat().st_size==PRODUCT_SIZE
        sizes['product']=PRODUCT_SIZE
        report['logical_sizes']=sizes
        report['physical_sizes']={n:s*MIB for n,s in DEVICES.items()}
        report['usable_bytes']=GROUP_SIZE
        report['remaining_pool_bytes']=GROUP_SIZE-sum(sizes.values())
        assert report['remaining_pool_bytes'] > 0
        empty=OUT/'unsparse_super_empty-al00.img'
        report['lpmake_empty_command']=list(map(str,metadata({n:0 for n in sizes},empty)))
        check_layout(lp_parse(empty),{n:0 for n in sizes})
        allocated=REPORT/'allocated-layout-OFFLINE-CHECK-ONLY.img'
        report['lpmake_allocated_command']=list(map(str,metadata(sizes,allocated)))
        check_layout(lp_parse(allocated),sizes)
        run(['lpdump',empty],'al00-empty-lpdump')
        run(['lpdump',allocated],'al00-allocated-lpdump')
        new_ops='remove_all_groups\n'+f'add_group {GROUP} {GROUP_SIZE}\n'
        new_ops+=''.join(f'add {n} {GROUP}\n' for n in sizes)
        new_ops+=''.join(f'resize {n} {s}\n' for n,s in sizes.items())
        (OUT/'dynamic_partitions_op_list').write_text(new_ops)
        make_product_dat(img)
        replacements={'unsparse_super_empty.img':empty,
                      'dynamic_partitions_op_list':OUT/'dynamic_partitions_op_list',
                      **{n:OUT/n for n in ['product.new.dat.br','product.transfer.list','product.patch.dat']}}
        target=OUT/'LeaOS-OSS-20.0-20260815-harry-AL00-EXPERIMENTAL-UNSIGNED.zip'
        report['changed_zip_entries']=list(replacements)
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as dest:
            for info in z.infolist():
                # Keep all payloads except the five explicitly replaced entries.
                # otacert is the original package certificate, not a valid signature of this ZIP.
                ni=zipfile.ZipInfo(info.filename,info.date_time)
                ni.external_attr=info.external_attr
                with dest.open(ni,'w',force_zip64=True) as out:
                    if info.filename in replacements:
                        with open(replacements[info.filename],'rb') as src:shutil.copyfileobj(src,out)
                    else:
                        with z.open(info) as src:shutil.copyfileobj(src,out)
        with zipfile.ZipFile(target) as verify:
            assert verify.testzip() is None
            assert verify.namelist()==z.namelist()
            for n in z.namelist():
                if n not in replacements:
                    with z.open(n) as a,verify.open(n) as b:
                        assert hashlib.file_digest(a,'sha256').digest()==hashlib.file_digest(b,'sha256').digest(),n
        report['output_zip_sha256']=sha(target)
        report['product_resized_sha256']=sha(img)
        report['product_dat_roundtrip']='PASS byte-for-byte'
        report['zip_crc_and_unchanged_entries']='PASS'
    (REPORT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (OUT/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    print(json.dumps({k:report[k] for k in ['status','logical_sizes','remaining_pool_bytes','output_zip_sha256']},indent=2))


if __name__=='__main__':
    main()
