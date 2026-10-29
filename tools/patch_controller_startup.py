"""Generate the tested controller 1.10 startup swap. Offline; no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from controller_startup_fragment import ENTRY, END, KEYS, MODE, SWITCH_MASK, ORIGINAL, REPLACEMENT
from patch_receiver import verify

INPUT_SHA = '968edee528c23d56e2059288f90c109fa5135f060de5b403e72d0b6c50f5eb87'
STOCK_PAYLOAD_SHA = '43d8cd222586f8a118d867cb60b0711dee504aed1354d548958d0e985dac30e7'
OUTPUT_SHA = '08eb82611760db9200b2d435138c3b0e565a70830a4934f22ce577773f3816a1'
TESTED_PROGRAM_SHA = '14694a61ab1fd6fe525622e71b7c37fc4e1cfaca22e77c79d4e15eeafff6db25'
BASE = 0x5000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(raw):
    if len(raw) != 145436 or digest(raw) != INPUT_SHA:
        raise ValueError('Unsupported stock controller .dat; exact 1.10 hash required')
    original = raw[28:]
    if digest(original) != STOCK_PAYLOAD_SHA:
        raise ValueError('Unexpected stock payload')
    program = verify(original)
    if program != 0x17a64 or original[ENTRY - BASE:END - BASE] != ORIGINAL:
        raise ValueError('Unexpected startup block or program length')
    if struct.unpack_from('<III', original, 0x10090 - BASE) != (KEYS, SWITCH_MASK, MODE):
        raise ValueError('Unexpected literal pool')
    candidate = bytearray(original)
    candidate[ENTRY - BASE:END - BASE] = REPLACEMENT
    crc = (~zlib.crc32(candidate[:program - 4])) & 0xffffffff
    byte_sum = sum(candidate[:program - 4]) & 0xffffffff
    struct.pack_into('<II', candidate, program - 4, crc, byte_sum)
    verify(candidate)
    differing = [i for i, (a, b) in enumerate(zip(original, candidate)) if a != b]
    allowed = set(range(ENTRY - BASE, END - BASE)) | set(range(program - 4, program + 4))
    if len(candidate) != len(original) or len(differing) != 27 or not set(differing) <= allowed:
        raise ValueError('Unexpected differences')
    if digest(candidate) != OUTPUT_SHA or digest(candidate[:program + 4]) != TESTED_PROGRAM_SHA:
        raise ValueError('Candidate differs from physically tested program')
    return original, bytes(candidate), differing


def build(source, output):
    original, candidate, differing = transform(source.read_bytes())
    names = ('controller-1.10-home-hid-application.bin',
             'controller-1.10-stock-application.bin', 'controller-startup-build.json')
    if any((output / name).exists() for name in names):
        raise FileExistsError('An output file already exists; choose a new directory')
    result = {'input_sha256': INPUT_SHA, 'stock_payload_sha256': STOCK_PAYLOAD_SHA,
              'candidate_payload_sha256': OUTPUT_SHA, 'tested_program_sha256': TESTED_PROGRAM_SHA,
              'application_base': hex(BASE), 'payload_bytes': len(candidate),
              'differing_bytes': len(differing), 'changed_flash_addresses': [hex(BASE + i) for i in differing],
              'erase_sectors': ['0x10000', '0x1c000'], 'reported_version': '1.10',
              'output': names[0], 'stock_output': names[1],
              'format': 'Raw application payloads, not OEM .dat packages or complete flash backups.',
              'hardware_written': False}
    output.mkdir(parents=True, exist_ok=True)
    for name, data in ((names[0], candidate), (names[1], original)):
        with (output / name).open('xb') as stream:
            stream.write(data)
    with (output / names[2]).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output_dir), indent=2))
