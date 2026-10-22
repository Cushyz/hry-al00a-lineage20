#!/usr/bin/env python3
"""Compare file payloads and inode metadata before/after ext4 resize, without mounting."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work'
REPORT=ROOT/'reports'


def manifest(folder):
    result={}
    for base,dirs,files in os.walk(folder,followlinks=False):
        for name in dirs+files:
            p=Path(base)/name
            s=p.lstat()
            row={'mode':stat.S_IMODE(s.st_mode),'type':stat.S_IFMT(s.st_mode)}
            if p.is_symlink(): row['target']=os.readlink(p)
            elif p.is_file():
                with p.open('rb') as f:row['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
                row['bytes']=s.st_size
            result[str(p.relative_to(folder))]=row
    return result


def inode_records(img, paths, label):
    commands=WORK/(label+'-debugfs-commands.txt')
    # Compare stable stat fields and extended attributes; block addresses are expected to change.
    commands.write_text(''.join(f'stat "/{p}"\nea_list "/{p}"\n' for p in ['']+list(paths)))
    proc=subprocess.run(['debugfs','-f',str(commands),str(img)],capture_output=True,text=True,check=True)
    (REPORT/(label+'-inode-audit.txt')).write_text(proc.stdout+proc.stderr)
    assert 'File not found' not in proc.stdout+proc.stderr
    result=[]
    for line in proc.stdout.splitlines():
        if line.startswith(('Inode:','User:','Links:','Extended attributes:')):
            if line.startswith('Inode:'):
                line=re.sub(r'^Inode: \d+\s*','',line)
            if line.startswith('Links:'):
                line=line.split('Blockcount:')[0].rstrip()
            result.append(line)
        elif line.startswith('  ') and re.match(r'\s+[\w.]+ \(\d+\) = ',line):
            result.append(line)
    return result


def main():
    if not __debug__:
        raise RuntimeError("Run without -O/PYTHONOPTIMIZE; format checks require assertions.")
    manifests=[]; audits=[]
    for label,filename in [('before','product-original.img'),('after','product-1400MiB.img')]:
        dest=WORK/('product-files-'+label)
        if dest.exists():shutil.rmtree(dest)
        dest.mkdir()
        p=subprocess.run(['debugfs','-R',f'rdump / {dest}',str(WORK/filename)],capture_output=True,text=True,check=True)
        (REPORT/(label+'-rdump.txt')).write_text(p.stdout+p.stderr)
        assert 'error' not in (p.stdout+p.stderr).lower()
        m=manifest(dest);manifests.append(m)
        (REPORT/(label+'-files.json')).write_text(json.dumps(m,indent=2)+'\n')
        audits.append(inode_records(WORK/filename,sorted(m),label))
    assert manifests[0] and manifests[0]==manifests[1], 'File contents, symlinks or modes changed'
    assert audits[0] and audits[0]==audits[1], 'Stable inode metadata or xattrs changed'
    result={'file_tree_match':True,'inode_metadata_and_xattrs_match':True,
            'entries':len(manifests[0]),'regular_files':sum('sha256' in v for v in manifests[0].values()),
            'compared_inode_metadata_lines':len(audits[0])}
    (REPORT/'product-integrity.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    for label in ['before','after']:shutil.rmtree(WORK/('product-files-'+label))


if __name__=='__main__':main()
