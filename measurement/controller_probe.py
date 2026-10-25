"""Read-only Windows HID descriptor and report capture for the connected 8BitDo.

No output reports, feature writes, firmware changes, or input injection.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import statistics
import time

K = C.WinDLL('kernel32', use_last_error=True)
S = C.WinDLL('setupapi', use_last_error=True)
H = C.WinDLL('hid', use_last_error=True)

class GUID(C.Structure):
    _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', C.c_ubyte * 8)]

class IFACE(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('InterfaceClassGuid', GUID), ('Flags', W.DWORD), ('Reserved', C.c_void_p)]

class ATTR(C.Structure):
    _fields_ = [('Size', W.ULONG), ('VendorID', W.USHORT), ('ProductID', W.USHORT), ('VersionNumber', W.USHORT)]

class CAPS(C.Structure):
    _fields_ = [(n, W.USHORT) for n in ['Usage', 'UsagePage', 'InputReportByteLength', 'OutputReportByteLength', 'FeatureReportByteLength']] + [('Reserved', W.USHORT * 17)] + [(n, W.USHORT) for n in ['NumberLinkCollectionNodes', 'NumberInputButtonCaps', 'NumberInputValueCaps', 'NumberInputDataIndices', 'NumberOutputButtonCaps', 'NumberOutputValueCaps', 'NumberOutputDataIndices', 'NumberFeatureButtonCaps', 'NumberFeatureValueCaps', 'NumberFeatureDataIndices']]

class VALUECAP(C.Structure):
    _fields_ = [('UsagePage', W.USHORT), ('ReportID', C.c_ubyte), ('IsAlias', C.c_ubyte), ('BitField', W.USHORT), ('LinkCollection', W.USHORT), ('LinkUsage', W.USHORT), ('LinkUsagePage', W.USHORT), ('IsRange', C.c_ubyte), ('IsStringRange', C.c_ubyte), ('IsDesignatorRange', C.c_ubyte), ('IsAbsolute', C.c_ubyte), ('HasNull', C.c_ubyte), ('Reserved', C.c_ubyte), ('BitSize', W.USHORT), ('ReportCount', W.USHORT), ('Reserved2', W.USHORT * 5), ('UnitsExp', W.ULONG), ('Units', W.ULONG), ('LogicalMin', W.LONG), ('LogicalMax', W.LONG), ('PhysicalMin', W.LONG), ('PhysicalMax', W.LONG), ('Range', W.USHORT * 8)]

class OVERLAPPED(C.Structure):
    _fields_ = [('Internal', C.c_size_t), ('InternalHigh', C.c_size_t), ('Offset', W.DWORD), ('OffsetHigh', W.DWORD), ('hEvent', W.HANDLE)]

def proto(dll, name, ret, args):
    f = getattr(dll, name)
    f.restype, f.argtypes = ret, args
    return f

getguid = proto(H, 'HidD_GetHidGuid', None, [C.POINTER(GUID)])
getdevs = proto(S, 'SetupDiGetClassDevsW', W.HANDLE, [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD])
enumif = proto(S, 'SetupDiEnumDeviceInterfaces', W.BOOL, [W.HANDLE, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(IFACE)])
detail = proto(S, 'SetupDiGetDeviceInterfaceDetailW', W.BOOL, [W.HANDLE, C.POINTER(IFACE), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p])
destroy = proto(S, 'SetupDiDestroyDeviceInfoList', W.BOOL, [W.HANDLE])
openfile = proto(K, 'CreateFileW', W.HANDLE, [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE])
close = proto(K, 'CloseHandle', W.BOOL, [W.HANDLE])
attrs = proto(H, 'HidD_GetAttributes', C.c_ubyte, [W.HANDLE, C.POINTER(ATTR)])
getproduct = proto(H, 'HidD_GetProductString', C.c_ubyte, [W.HANDLE, C.c_void_p, W.ULONG])
getpre = proto(H, 'HidD_GetPreparsedData', C.c_ubyte, [W.HANDLE, C.POINTER(C.c_void_p)])
freepre = proto(H, 'HidD_FreePreparsedData', C.c_ubyte, [C.c_void_p])
getcaps = proto(H, 'HidP_GetCaps', W.LONG, [C.c_void_p, C.POINTER(CAPS)])
getvalues = proto(H, 'HidP_GetValueCaps', W.LONG, [C.c_int, C.POINTER(VALUECAP), C.POINTER(W.USHORT), C.c_void_p])
read = proto(K, 'ReadFile', W.BOOL, [W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.POINTER(OVERLAPPED)])
event = proto(K, 'CreateEventW', W.HANDLE, [C.c_void_p, W.BOOL, W.BOOL, W.LPCWSTR])
wait = proto(K, 'WaitForSingleObject', W.DWORD, [W.HANDLE, W.DWORD])
getover = proto(K, 'GetOverlappedResult', W.BOOL, [W.HANDLE, C.POINTER(OVERLAPPED), C.POINTER(W.DWORD), W.BOOL])
cancel = proto(K, 'CancelIoEx', W.BOOL, [W.HANDLE, C.POINTER(OVERLAPPED)])
reset = proto(K, 'ResetEvent', W.BOOL, [W.HANDLE])
INVALID = C.c_void_p(-1).value

def paths():
    guid = GUID()
    getguid(C.byref(guid))
    devs = getdevs(C.byref(guid), None, None, 0x12)
    try:
        i = 0
        while True:
            item = IFACE(cbSize=C.sizeof(IFACE))
            if not enumif(devs, None, C.byref(guid), i, C.byref(item)):
                break
            i += 1
            needed = W.DWORD()
            detail(devs, C.byref(item), None, 0, C.byref(needed), None)
            buf = C.create_string_buffer(needed.value)
            W.DWORD.from_buffer(buf).value = 8 if C.sizeof(C.c_void_p) == 8 else 6
            if detail(devs, C.byref(item), buf, len(buf), C.byref(needed), None):
                yield C.wstring_at(C.addressof(buf) + 4)
    finally:
        destroy(devs)

def describe(path):
    h = openfile(path, 0, 3, None, 3, 0, None)
    if h == INVALID:
        return {'path': path, 'error': C.get_last_error()}
    pp = C.c_void_p()
    try:
        at = ATTR(Size=C.sizeof(ATTR))
        attrs(h, C.byref(at))
        product = C.create_unicode_buffer(256)
        getproduct(h, product, C.sizeof(product))
        out = dict(path=path, vid=f'{at.VendorID:04x}', pid=f'{at.ProductID:04x}', bcd_device=at.VersionNumber, product=product.value)
        if getpre(h, C.byref(pp)):
            caps = CAPS()
            status = getcaps(pp, C.byref(caps))
            out['caps_status'] = f'{status & 0xffffffff:08x}'
            out['caps'] = {n: getattr(caps, n) for n, _ in CAPS._fields_ if n != 'Reserved'}
            count = W.USHORT(caps.NumberInputValueCaps)
            values = (VALUECAP * count.value)()
            status = getvalues(0, values, C.byref(count), pp)
            out['value_caps'] = [dict(usage_page=v.UsagePage, report_id=v.ReportID, bit_size=v.BitSize, report_count=v.ReportCount, logical_min=v.LogicalMin, logical_max=v.LogicalMax, usage_min=v.Range[0], usage_max=v.Range[1] if v.IsRange else v.Range[0], is_range=bool(v.IsRange)) for v in values[:count.value]]
        return out
    finally:
        if pp:
            freepre(pp)
        close(h)

def capture(info, seconds, output):
    h = openfile(info['path'], 0x80000000, 3, None, 3, 0x40000000, None)
    if h == INVALID:
        raise OSError(C.get_last_error(), 'Cannot open HID input read handle')
    ev = event(None, True, False, None)
    ov = OVERLAPPED(hEvent=ev)
    buf = C.create_string_buffer(info['caps']['InputReportByteLength'])
    rows = []
    started = time.perf_counter_ns()
    print(json.dumps({'status': 'capture_started', 'seconds': seconds, 'product': info['product']}), flush=True)
    try:
        while (time.perf_counter_ns()-started)/1e9 < seconds:
            reset(ev)
            n = W.DWORD()
            ok = read(h, buf, len(buf), C.byref(n), C.byref(ov))
            if not ok:
                err = C.get_last_error()
                if err != 997:
                    raise OSError(err, 'ReadFile')
                result = wait(ev, 100)
                if result == 258:
                    cancel(h, C.byref(ov))
                    getover(h, C.byref(ov), C.byref(n), True)
                    continue
                if not getover(h, C.byref(ov), C.byref(n), False):
                    raise OSError(C.get_last_error(), 'GetOverlappedResult')
            if n.value:
                rows.append((time.perf_counter_ns()-started, bytes(buf.raw[:n.value]).hex()))
    finally:
        cancel(h, None)
        close(ev)
        close(h)
    payload = {'device': info, 'requested_seconds': seconds, 'elapsed_seconds': (time.perf_counter_ns()-started)/1e9, 'reports': rows}
    Path(output).write_text(json.dumps(payload), encoding='utf-8')
    counts = {}
    for _, raw in rows:
        rid = raw[:2]
        counts[rid] = counts.get(rid, 0)+1
    summary = {'output': str(Path(output).resolve()), 'elapsed_seconds': payload['elapsed_seconds'], 'report_count': len(rows), 'report_ids': counts, 'first_reports': rows[:3]}
    for rid in counts:
        parsed = [(t, bytes.fromhex(raw)) for t, raw in rows if raw[:2] == rid]
        if len(parsed) < 2:
            continue
        dt = [(b[0]-a[0])/1e6 for a,b in zip(parsed, parsed[1:])]
        axes = {name: {'min': min(p[1][offset] for p in parsed), 'max': max(p[1][offset] for p in parsed), 'unique': len(set(p[1][offset] for p in parsed))} for name, offset in [('lx',2),('ly',3),('rx',4),('ry',5),('rt',6),('lt',7)] if min(len(p[1]) for p in parsed) > offset}
        summary[rid] = {'host_report_rate_hz': (len(parsed)-1)/((parsed[-1][0]-parsed[0][0])/1e9), 'median_interval_ms': statistics.median(dt), 'p95_interval_ms': sorted(dt)[int(len(dt)*.95)], 'axes_bytes': axes}
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=float, default=0)
    ap.add_argument('--output', default='work/dinput_capture.json')
    args = ap.parse_args()
    devices = [describe(p) for p in paths() if 'vid_2dc8' in p.lower()]
    print(json.dumps({'structure_sizes': {'caps': C.sizeof(CAPS), 'value_caps': C.sizeof(VALUECAP)}, 'devices': devices}, indent=2), flush=True)
    if args.seconds:
        matches = [d for d in devices if d.get('caps', {}).get('UsagePage') == 1 and d['caps']['Usage'] in [4,5]]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one 8BitDo gamepad, got {len(matches)}')
        capture(matches[0], args.seconds, args.output)
