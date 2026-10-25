"""Read XInput state only; never send rumble or modify controller state."""
import argparse
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import json
import math
import statistics
import time

class GAMEPAD(C.Structure):
    _fields_ = [('buttons', W.WORD), ('lt', C.c_ubyte), ('rt', C.c_ubyte), ('lx', C.c_short), ('ly', C.c_short), ('rx', C.c_short), ('ry', C.c_short)]

class STATE(C.Structure):
    _fields_ = [('packet', W.DWORD), ('pad', GAMEPAD)]

dll = C.WinDLL('xinput1_4.dll')
getstate = dll.XInputGetState
getstate.argtypes, getstate.restype = [W.DWORD, C.POINTER(STATE)], W.DWORD

def connected():
    found = []
    for i in range(4):
        s = STATE()
        if getstate(i, C.byref(s)) == 0:
            found.append((i, s))
    return found

def summary(rows):
    result = {'samples': len(rows)}
    for j, name in enumerate(['lt','rt','lx','ly','rx','ry'], 2):
        values = sorted(set(r[j] for r in rows))
        deltas = [b-a for a,b in zip(values, values[1:])]
        result[name] = {'minimum': min(values), 'maximum': max(values), 'unique_values': len(values), 'minimum_observed_step': min(deltas) if deltas else None, 'gcd_observed_steps': math.gcd(*deltas) if deltas else None}
    return result

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=0)
    ap.add_argument('--output', default='work/xinput_movement.json')
    args = ap.parse_args()
    found = connected()
    print(json.dumps({'connected_slots': [i for i,_ in found]}), flush=True)
    if args.seconds:
        if len(found) != 1:
            raise RuntimeError(f'Expected exactly one XInput controller, got {len(found)}')
        slot = found[0][0]
        start = time.perf_counter_ns()
        rows = []
        print(json.dumps({'status': 'capture_started', 'slot': slot, 'seconds': args.seconds}), flush=True)
        last_progress = 0
        while (time.perf_counter_ns()-start)/1e9 < args.seconds:
            state = STATE()
            rc = getstate(slot, C.byref(state))
            if rc:
                raise OSError(rc, 'XInputGetState')
            p = state.pad
            rows.append((time.perf_counter_ns()-start, state.packet, p.lt, p.rt, p.lx, p.ly, p.rx, p.ry, p.buttons))
            if len(rows) % 1000 == 0 and rows[-1][0]/1e9-last_progress >= 10:
                last_progress = rows[-1][0]/1e9
                print(json.dumps({'elapsed_seconds': last_progress, 'summary': summary(rows)}), flush=True)
            time.sleep(0.0004)
        result = {'slot': slot, 'elapsed_seconds': (time.perf_counter_ns()-start)/1e9, 'summary': summary(rows), 'reports': rows, 'columns': ['elapsed_ns','packet','lt','rt','lx','ly','rx','ry','buttons'], 'limitation': 'Host state sampling; not a physical input latency measurement or USB report-rate measurement.'}
        Path(args.output).write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ['reports']}, indent=2), flush=True)
