#!/usr/bin/env python3
"""Patch one exact local init file. No device access or image/OTA modification."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.is_symlink() or not stat.S_ISREG(args.source.stat().st_mode):
        raise ValueError('Input must be a regular local file, not a symlink or device.')
    if args.source.resolve() == args.output.resolve():
        raise ValueError('Input and output must differ.')
    spec = json.loads((Path(__file__).resolve().parents[1] / 'evidence/init-patch.json').read_text())
    if args.source.stat().st_size != spec['init_size']:
        raise ValueError('Unexpected init size; no output written.')
    original = args.source.read_bytes()
    if hashlib.sha256(original).hexdigest() != spec['init_original_sha256']:
        raise ValueError('Unknown init SHA256; no output written.')
    patched = bytearray(original)
    for change in spec['instruction_changes']:
        offset = change['offset']
        before = bytes.fromhex(change['before'])
        after = bytes.fromhex(change['after'])
        if len(before) != 4 or len(after) != 4 or original[offset:offset+4] != before:
            raise ValueError('Instruction mismatch; no output written.')
        patched[offset:offset+4] = after
    digest = hashlib.sha256(patched).hexdigest()
    if digest != spec['init_patched_sha256']:
        raise ValueError('Patched hash mismatch; no output written.')
    with args.output.open('xb') as stream:
        stream.write(patched)
    print(f'PATCH_FILE_OK SHA256={digest}')
    print('Only a local file was created; no system image, ZIP or phone was modified.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        sys.exit(1)
