"""Generate the tested receiver 1.06 raw application payload; no device access."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from receiver_fragment import PROTOTYPE

INPUT_SHA='1018a299f3662098fcd7d2a71789d1290bb7603dd1998fe03759c5643cd05401'
STOCK_PAYLOAD_SHA='e5bc101ea9b9f1c970a7fbffe4a92261400ad49cbdb58d4190d08a6fd404b3fe'
OUTPUT_SHA='7f47efe7dd3bb08f648a7602ec600a7d6675cb377bbfc3bf8925bbbccfa63e01'


def digest(data): return hashlib.sha256(data).hexdigest()


def verify(payload):
    if len(payload)<32: raise ValueError('Truncated application')
    end=struct.unpack_from('<I',payload,0x18)[0]
    if not 32<=end<=len(payload)-4 or end%4: raise ValueError('Invalid application length')
    expected=((~zlib.crc32(payload[:end-4]))&0xffffffff,sum(payload[:end-4])&0xffffffff)
    if struct.unpack_from('<II',payload,end-4)!=expected: raise ValueError('Application integrity mismatch')
    return end


def build(source,output):
    raw=source.read_bytes()
    if digest(raw)!=INPUT_SHA or len(raw)!=40476: raise ValueError('Unsupported firmware input; no output produced')
    original=raw[28:]
    if digest(original)!=STOCK_PAYLOAD_SHA: raise ValueError('Unexpected original payload')
    end=verify(original)
    candidate=bytearray(original)
    if len(PROTOTYPE)!=46: raise ValueError('Unexpected fragment size')
    candidate[0x6b7e:0x6bac]=PROTOTYPE
    struct.pack_into('<II',candidate,end-4,(~zlib.crc32(candidate[:end-4]))&0xffffffff,sum(candidate[:end-4])&0xffffffff)
    verify(candidate)
    differences=[i for i,(a,b) in enumerate(zip(original,candidate)) if a!=b]
    allowed=set(range(0x6b7e,0x6bac))|set(range(end-4,end+4))
    if len(candidate)!=len(original) or len(differences)!=43 or not set(differences)<=allowed:
        raise ValueError('Unexpected changes')
    if digest(candidate)!=OUTPUT_SHA: raise ValueError('Candidate differs from physically tested payload')
    output.mkdir(parents=True,exist_ok=True)
    name=output/'receiver-1.06-native-fine-application.bin'
    if name.exists(): raise FileExistsError('Output already exists: '+str(name))
    with name.open('xb') as stream: stream.write(candidate)
    result=dict(input_sha256=INPUT_SHA,original_payload_sha256=STOCK_PAYLOAD_SHA,
                candidate_payload_sha256=OUTPUT_SHA,application_base='0x5000',bytes=len(candidate),
                differing_bytes=len(differences),changed_flash_addresses=[hex(0x5000+i) for i in differences],
                erase_sectors=['0xb000','0xe000'],output=name.name,
                format='Raw application payload. Not an OEM .dat or a complete flash image.',hardware_written=False)
    (output/'receiver-build.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.input,args.output_dir),indent=2))
