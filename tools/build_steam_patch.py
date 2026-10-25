"""Build an exact-version, in-place SDL parser patch in a separate output folder."""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64

ORIGINAL_SHA='e8656a70d57eb5cfa5e20a4c96c45f7f72325a3a109135e919d033f233fa3fb7'
START,END=0xDEC5B,0xDED85
REMAP,SEND_AXIS=0x10AAB0,0x115F90


class Assembly:
    def __init__(self,base):self.base=base;self.nodes=[]
    def raw(self,hexbytes):self.nodes.append(['raw',bytes.fromhex(hexbytes)])
    def label(self,name):self.nodes.append(['label',name])
    def branch(self,kind,target):self.nodes.append([kind,target,False])
    def rip(self,prefix,target):self.nodes.append(['rip',bytes.fromhex(prefix),target])
    def size(self,n):
        if n[0]=='raw':return len(n[1])
        if n[0]=='label':return 0
        if n[0]=='rip':return len(n[1])+4
        return 2 if n[2] else 6 if n[0] in ('je','jne','jb') else 5
    def positions(self):
        labels={};offset=self.base;positions=[]
        for n in self.nodes:
            positions.append(offset)
            if n[0]=='label':labels[n[1]]=offset
            offset+=self.size(n)
        return labels,positions
    def encode(self):
        while True:
            labels,positions=self.positions();changed=False
            for n,pos in zip(self.nodes,positions):
                if n[0] not in ('jmp','je','jne','jb') or n[2]:continue
                target=labels[n[1]] if isinstance(n[1],str) else n[1]
                shrink=self.size(n)-2
                if target>pos and isinstance(n[1],str):target-=shrink
                if -128<=target-(pos+2)<=127:n[2]=True;changed=True
            if not changed:break
        labels,positions=self.positions();out=bytearray()
        condition={'je':4,'jne':5,'jb':2}
        for n,pos in zip(self.nodes,positions):
            kind=n[0]
            if kind=='raw':out.extend(n[1]);continue
            if kind=='label':continue
            target=n[2] if kind=='rip' else n[1]
            if isinstance(target,str):target=labels[target]
            if kind=='rip':out.extend(n[1]+struct.pack('<i',target-pos-self.size(n)));continue
            delta=target-pos-self.size(n)
            if n[2]:out.extend(bytes([0xEB if kind=='jmp' else 0x70+condition[kind],delta&255]))
            else:
                prefix=bytes([0xE8 if kind=='call' else 0xE9]) if kind in ('call','jmp') else bytes([0x0F,0x80+condition[kind]])
                out.extend(prefix+struct.pack('<i',delta))
        return bytes(out),labels


def build(source, destination):
    global ROOT
    ROOT=destination.resolve()
    original=source.read_bytes()
    if hashlib.sha256(original).hexdigest()!=ORIGINAL_SHA:raise ValueError('Unknown SDL build; no patch produced')
    ROOT.mkdir(parents=True,exist_ok=True)
    backup=ROOT/'original'/'SDL3.dll'
    backup.parent.mkdir(exist_ok=True)
    if backup.exists() and backup.read_bytes()!=original:raise ValueError('Existing backup differs')
    if not backup.exists():backup.write_bytes(original)
    pe=pefile.PE(data=original);a=Assembly(START)
    # Preserve original remap constants and use the same float conversion for
    # stock reports. Everything stays in the original function/unwind range.
    decoder=Cs(CS_ARCH_X86,CS_MODE_64)
    for instruction_rva in (0xDEC5F,0xDEC67,0xDEC6F,0xDEC78):
        instruction=next(decoder.disasm(pe.get_data(instruction_rva,15),instruction_rva))
        if instruction.mnemonic!='movss':raise ValueError('Unexpected original constant loader')
        target=instruction.address+instruction.size+struct.unpack('<i',instruction.bytes[-4:])[0]
        a.rip(instruction.bytes[:-4].hex(),target)
    a.raw('45 31 e4')                         # r12d = legacy by default
    # Pinned SDL_Joystick GUID offset 0x20: VID +4, PID +8. Native replay checks
    # these against the public SDL getters before exercising this code.
    a.raw('66 81 7e 24 c8 2d');a.branch('jne','guard_done')
    a.raw('66 81 7e 28 12 60');a.branch('jne','guard_done')
    a.raw('41 83 ff 22');a.branch('jne','guard_done')  # exact 34-byte packet
    a.raw('80 3f 01');a.branch('jne','guard_done')     # native report ID 1
    a.raw('0f b7 47 0b 66 0b 47 1b 66 0b 47 1d 66 0b 47 1f 66 85 c0')
    a.branch('je','guard_done')                      # stock extension is zero
    for axis,high in enumerate((12,28,30,32)):
        a.raw(f'8a 47 {high:02x}')
        if axis%2==0:
            a.raw('3c 7f');a.branch('je',f'x_center_{axis}');a.raw('f6 d0');a.label(f'x_center_{axis}')
        a.raw(f'3a 47 {axis+2:02x}');a.branch('jne','guard_done')
    a.raw('41 bc 01 00 00 00')                      # validated fine extension
    a.label('guard_done');a.raw('31 db')             # ebx = axis index
    a.label('axis_loop');a.raw('45 85 e4');a.branch('je','legacy')
    a.rip('48 8d 05','fine_offsets')
    a.raw('0f b6 04 18 0f b7 04 07 f6 c3 01');a.branch('jne','fine_y')
    a.raw('f7 d8 05 ff 7f 00 00');a.branch('jmp','send')
    a.label('fine_y');a.raw('2d 00 80 00 00');a.branch('jmp','send')
    a.label('legacy');a.raw('0f b6 44 1f 02 3c 7f');a.branch('jne','legacy_scale')
    a.raw('31 c0');a.branch('jmp','send')
    a.label('legacy_scale')
    a.raw('83 e8 7f f3 0f 11 74 24 20 0f 28 df 41 0f 28 d0 41 0f 28 c9 66 0f 6e c0 0f 5b c0')
    a.branch('call',REMAP);a.raw('f3 0f 2c c0')
    a.label('send');a.raw('44 0f b7 c8 41 89 d8 48 89 f2 48 89 e9')
    a.branch('call',SEND_AXIS);a.raw('ff c3 83 fb 04');a.branch('jb','axis_loop')
    a.branch('jmp',END)
    a.label('fine_offsets');a.raw('0b 1b 1d 1f')
    code,labels=a.encode()
    if len(code)>END-START:raise ValueError(f'Patch does not fit: {len(code)} > {END-START}')
    code=code+b'\x90'*(END-START-len(code));offset=pe.get_offset_from_rva(START)
    candidate=bytearray(original);candidate[offset:offset+len(code)]=code
    patched=pefile.PE(data=candidate)
    checksum_offset=patched.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum')
    struct.pack_into('<I',candidate,checksum_offset,patched.generate_checksum())
    changed=[i for i,(before,after) in enumerate(zip(original,candidate)) if before!=after]
    if len(original)!=len(candidate) or any(not(offset<=i<offset+len(code) or checksum_offset<=i<checksum_offset+4) for i in changed):raise ValueError('Unexpected changes outside axes/checksum')
    outdir=ROOT/'candidate';outdir.mkdir(exist_ok=True)
    (outdir/'SDL3.dll').write_bytes(candidate)
    (ROOT/'axis-patch.bin').write_bytes(code)
    md=Cs(CS_ARCH_X86,CS_MODE_64)
    listing=[f'{i.address:08x}: {i.bytes.hex():24s} {i.mnemonic} {i.op_str}' for i in md.disasm(code[:labels['fine_offsets']-START],START)]
    (ROOT/'axis-patch.asm.txt').write_text('\n'.join(listing)+'\n')
    manifest=dict(original_sha256=ORIGINAL_SHA,candidate_sha256=hashlib.sha256(candidate).hexdigest(),bytes=len(candidate),changed_bytes=len(changed),axis_rva_start=hex(START),axis_rva_end=hex(END),axis_file_offset=hex(offset),reserved_patch_bytes=END-START,encoded_code_and_table_bytes=labels['fine_offsets']-START+4,labels={k:hex(v) for k,v in labels.items()},checksum_file_offset=hex(checksum_offset),guards=['VID 2DC8 / PID 6012','report length 34','report ID 1','nonzero fine extension','all four fine words match original public high-byte conversion'],preserved=['original float legacy scaling','buttons/triggers/battery/sensor code','PE size/sections/exports/imports/relocations/unwind tables'],installed_steam_modified=False,physical_firmware_modified=False)
    (ROOT/'patch-manifest.json').write_text(json.dumps(manifest,indent=2));return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(build(args.input,args.output_dir),indent=2))
