"""Execute the copied DLL's actual parser against saved/synthetic reports.

All physical input backends are disabled before SDL joystick initialization.
The only joystick created is an SDL object private to this test process, not
a Windows HID device and not a controller visible to Steam.
"""
import argparse
from collections import Counter
import ctypes as c
import csv
import gzip
import hashlib
import json
from pathlib import Path
import random
import struct
import time

ROOT=Path(__file__).resolve().parent
FINE=(11,27,29,31)
BUTTONS=((8,0,0),(8,1,1),(8,3,2),(8,4,3),(8,6,9),(8,7,10),(8,5,13),(8,2,14),
         (9,2,4),(9,4,5),(9,3,6),(9,5,7),(9,6,8),(10,0,11),(10,1,12))


class VirtualDesc(c.Structure):
    _fields_=[('version',c.c_uint32)]+[(k,c.c_uint16) for k in ('type','padding','vendor_id','product_id','naxes','nbuttons','nballs','nhats','ntouchpads','nsensors')]+[('padding2',c.c_uint16*2),('button_mask',c.c_uint32),('axis_mask',c.c_uint32)]+[(k,c.c_void_p) for k in ('name','touchpads','sensors','userdata','Update','SetPlayerIndex','Rumble','RumbleTriggers','SetLED','SendEffect','SetSensorsEnabled','Cleanup')]


class Reader:
    def __init__(self,path):
        self.s=c.CDLL(str(path.resolve()));s=self.s
        def api(name,restype,*argtypes):
            fn=getattr(s,name);fn.restype=restype;fn.argtypes=list(argtypes);return fn
        self.hint=api('SDL_SetHint',c.c_bool,c.c_char_p,c.c_char_p)
        self.init=api('SDL_Init',c.c_bool,c.c_uint32);self.error=api('SDL_GetError',c.c_char_p)
        self.list=api('SDL_GetJoysticks',c.POINTER(c.c_uint32),c.POINTER(c.c_int));self.free=api('SDL_free',None,c.c_void_p)
        self.attach=api('SDL_AttachVirtualJoystick',c.c_uint32,c.POINTER(VirtualDesc));self.open=api('SDL_OpenJoystick',c.c_void_p,c.c_uint32)
        self.close=api('SDL_CloseJoystick',None,c.c_void_p);self.detach=api('SDL_DetachVirtualJoystick',c.c_bool,c.c_uint32)
        self.axis=api('SDL_GetJoystickAxis',c.c_int16,c.c_void_p,c.c_int);self.button=api('SDL_GetJoystickButton',c.c_bool,c.c_void_p,c.c_int);self.hat=api('SDL_GetJoystickHat',c.c_uint8,c.c_void_p,c.c_int)
        self.vendor=api('SDL_GetJoystickVendor',c.c_uint16,c.c_void_p);self.product=api('SDL_GetJoystickProduct',c.c_uint16,c.c_void_p)
        self.lock=api('SDL_LockJoysticks',None);self.unlock=api('SDL_UnlockJoysticks',None)
        self.parser=c.WINFUNCTYPE(None,c.c_void_p,c.c_void_p,c.c_void_p,c.c_int)(s._handle+0xDE9A0)
        for name in ('SDL_JOYSTICK_HIDAPI','SDL_JOYSTICK_RAWINPUT','SDL_JOYSTICK_WGI','SDL_JOYSTICK_GAMEINPUT','SDL_JOYSTICK_GAMEINPUT_RAW','SDL_JOYSTICK_DIRECTINPUT','SDL_XINPUT_ENABLED','SDL_JOYSTICK_DINPUT'):
            self.hint(name.encode(),b'0')
        self.hint(b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS',b'1')
        if not self.init(0x200):raise RuntimeError(self.error())
        n=c.c_int();ids=self.list(c.byref(n));self.free(ids)
        if n.value:raise RuntimeError(f'Unexpected pre-existing joystick in isolated SDL: {n.value}')
        self.pads=[];self.pad=None;self.ctx=None;self.buffer=(c.c_ubyte*64)()
        self.add_pad(0x2dc8,0x6012)
    def add_pad(self,vid,pid):
        desc=VirtualDesc();desc.version=c.sizeof(desc);desc.type=1;desc.vendor_id=vid;desc.product_id=pid
        desc.naxes=6;desc.nbuttons=15;desc.nhats=1;desc.button_mask=0x7fff;desc.axis_mask=0x3f
        name=c.create_string_buffer(b'Private offline parser replay');desc.name=c.addressof(name)
        id=self.attach(c.byref(desc))
        if not id:raise RuntimeError(self.error())
        pad=self.open(id)
        if not pad:raise RuntimeError(self.error())
        if (self.vendor(pad),self.product(pad))!=(vid,pid):raise RuntimeError('Virtual identity differs')
        inline=(c.c_uint16.from_address(pad+0x24).value,c.c_uint16.from_address(pad+0x28).value)
        if inline!=(vid,pid) or c.c_int.from_address(pad+0x70).value!=15:raise RuntimeError('Pinned joystick layout differs')
        self.pad=pad;self.ctx=c.create_string_buffer(128);self.pads.append((id,pad))
        self.warm()
    def feed(self,raw,size=34,buttons=False):
        c.memset(c.addressof(self.buffer),0,64);c.memmove(self.buffer,raw,len(raw))
        self.lock()
        try:self.parser(self.pad,self.ctx,self.buffer,size)
        finally:self.unlock()
        axes=tuple(self.axis(self.pad,i) for i in range(6))
        if not buttons:return axes
        mask=sum((1<<i) for i in range(15) if self.button(self.pad,i));hat=self.hat(self.pad,0)
        return axes,mask,hat
    def warm(self):
        raw=bytearray(34);raw[0]=1;raw[1]=15
        for v in (255,0,127):
            raw[2:6]=bytes([v]*4);raw[6:8]=bytes([255 if v==0 else 0]*2);self.feed(bytes(raw))
    def finish(self):
        for id,pad in self.pads:self.close(pad);self.detach(id)
        self.s.SDL_Quit()


def report(values=(32767,)*4):
    raw=bytearray(34);raw[0]=1;raw[1]=15
    for i,value in enumerate(values):
        struct.pack_into('<H',raw,FINE[i],value);h=value>>8;raw[i+2]=(127 if h==127 else 255-h) if i%2==0 else h
    return raw


def fine_expected(raw):
    words=[struct.unpack_from('<H',raw,off)[0] for off in FINE]
    return tuple(32767-v if i%2==0 else v-32768 for i,v in enumerate(words))+(raw[7]*257-32768,raw[6]*257-32768)


def run(kind,smoke=False):
    manifest=json.loads((ROOT/'patch-manifest.json').read_text());path=ROOT/kind/'SDL3.dll'
    expected_hash=manifest['original_sha256' if kind=='original' else 'candidate_sha256']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected_hash:raise RuntimeError('Reader hash mismatch')
    r=Reader(path);result=dict(kind=kind,physical_backends_disabled=True,private_virtual_only=True,passed=False)
    try:
        samples=[]
        for value in (0,1,2048,2049,32766,32767,32768,32769,65534,65535):
            raw=report((value,)*4);observed=r.feed(bytes(raw));samples.append(dict(source=value,observed=observed))
            if kind=='candidate' and observed!=fine_expected(raw):raise AssertionError(samples[-1])
        result['smoke_samples']=samples
        if smoke:result['passed']=True;return result
        # Native original table, rather than a Python reimplementation of the
        # original float remap, is the reference for every fallback condition.
        table=[];r.warm()
        for value in range(256):
            raw=bytearray(34);raw[0]=1;raw[1]=15;raw[2:6]=bytes([value]*4)
            axes=r.feed(bytes(raw))
            if len(set(axes[:4]))!=1:raise AssertionError('Legacy axes differ')
            table.append(axes[0])
        if kind=='original':(ROOT/'original-legacy-table.json').write_text(json.dumps(table))
        elif table!=json.loads((ROOT/'original-legacy-table.json').read_text()):raise AssertionError('Stock byte conversion changed')
        fallback_count=0
        rng=random.Random(47)
        for mode in ('stock','bad_extension','report3','short_report'):
            for _ in range(1024):
                raw=report(tuple(rng.randrange(65536) for _ in range(4)));size=34
                if mode=='stock':
                    for off in FINE:raw[off:off+2]=b'\0\0'
                elif mode=='bad_extension':raw[2]^=1
                elif mode=='report3':raw[0]=3
                else:size=12
                observed=r.feed(bytes(raw),size)
                wanted=tuple(table[v] for v in raw[2:6])+(0,0)
                # Trigger zero raw codes represent -32768.
                wanted=wanted[:4]+(-32768,-32768)
                if observed!=wanted:raise AssertionError(dict(mode=mode,observed=observed,wanted=wanted))
                fallback_count+=1
        result['fallback_cases']=fallback_count
        fixture=FIXTURE
        rows=0;unique=[set() for _ in range(4)];digest=hashlib.sha256();stock_digest=hashlib.sha256()
        with gzip.open(fixture,'rt',newline='') as stream:
            for row in csv.DictReader(stream):
                raw=bytes.fromhex(row['report_hex']);axes,buttons,hat=r.feed(raw,buttons=True)
                wanted=fine_expected(raw) if kind=='candidate' else tuple(table[v] for v in raw[2:6])+(raw[7]*257-32768,raw[6]*257-32768)
                if axes!=wanted:raise AssertionError(dict(row=rows,observed=axes,wanted=wanted))
                wanted_buttons=sum(1<<dest for off,bit,dest in BUTTONS if raw[off]&(1<<bit))
                wanted_hat=(1,3,2,6,4,12,8,9)[raw[1]] if raw[1]<8 else 0
                if (buttons,hat)!=(wanted_buttons,wanted_hat):raise AssertionError('Button or hat changed')
                digest.update(struct.pack('<6hHB',*axes,buttons,hat));rows+=1
                for i,value in enumerate(axes[:4]):unique[i].add(value)
                stock=bytearray(raw)
                for off in FINE:stock[off:off+2]=b'\0\0'
                legacy_axes,legacy_buttons,legacy_hat=r.feed(bytes(stock),buttons=True)
                expected_legacy=tuple(table[v] for v in stock[2:6])+(stock[7]*257-32768,stock[6]*257-32768)
                if legacy_axes!=expected_legacy or (legacy_buttons,legacy_hat)!=(wanted_buttons,wanted_hat):raise AssertionError('Stock replay changed')
                stock_digest.update(struct.pack('<6hHB',*legacy_axes,legacy_buttons,legacy_hat))
        result.update(fixture_rows=rows,fine_unique_axis_values=[len(v) for v in unique],replay_output_sha256=digest.hexdigest(),stock_replay_sha256=stock_digest.hexdigest())
        if kind=='candidate':
            previous=json.loads((ROOT/'original-result.json').read_text())
            if result['stock_replay_sha256']!=previous['stock_replay_sha256']:raise AssertionError('Original and candidate stock replay hashes differ')
            exhaustive=0
            for axis in range(4):
                values=[32767]*4
                for value in range(65536):
                    values[axis]=value;raw=report(values);observed=r.feed(bytes(raw))
                    if observed!=fine_expected(raw):raise AssertionError(dict(axis=axis,source=value,observed=observed))
                    exhaustive+=1
            result['exhaustive_fine_cases']=exhaustive
            r.add_pad(0x2dc8,0x6013)
            for value in range(256):
                raw=report((value*257,)*4);observed=r.feed(bytes(raw))
                if observed[:4]!=tuple(table[v] for v in raw[2:6]):raise AssertionError('Other PID used fine extension')
            result['other_pid_fallback_cases']=256
        result['passed']=True;return result
    finally:r.finish()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('kind',choices=['original','candidate']);parser.add_argument('--smoke',action='store_true');parser.add_argument('--directory',type=Path,required=True);parser.add_argument('--fixture',type=Path,default=Path(__file__).resolve().parents[1]/'evidence/receiver-motion.csv.gz');args=parser.parse_args();ROOT=args.directory.resolve();FIXTURE=args.fixture.resolve()
    began=time.perf_counter()
    try:
        result=run(args.kind,args.smoke);result['seconds']=time.perf_counter()-began
        (ROOT/f'{args.kind}-{"smoke" if args.smoke else "result"}.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    except BaseException as error:
        import traceback
        (ROOT/f'{args.kind}-error.txt').write_text(traceback.format_exc());raise
