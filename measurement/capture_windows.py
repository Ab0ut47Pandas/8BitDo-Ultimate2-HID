"""Read-only Windows capture paired with the Steam-launched tester.

Start this OUTSIDE Steam before arming the tester. It waits for a new session
marker, then records on the same Windows QPC clock. It never writes device data.
"""
import argparse
import csv
import ctypes as C
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import controller_probe as hid
import xinput_probe as xi

_qpc = C.WinDLL("kernel32").QueryPerformanceCounter
_qpf = C.WinDLL("kernel32").QueryPerformanceFrequency
_qpc.argtypes = _qpf.argtypes = [C.POINTER(C.c_longlong)]
_qpc.restype = _qpf.restype = C.c_int
_frequency = C.c_longlong()
_qpf(C.byref(_frequency))
FREQUENCY = _frequency.value


def qpc():
    value = C.c_longlong()
    _qpc(C.byref(value))
    return value.value


def describe_devices():
    return [hid.describe(p) for p in hid.paths() if "vid_2dc8" in p.lower()]


def wait_for_session(source):
    started = qpc()
    ready = {"status": "waiting", "source": source, "process": os.getpid(),
             "qpc": started, "qpc_frequency": FREQUENCY,
             "utc": datetime.now(timezone.utc).isoformat()}
    (ROOT/"physical-ready.json").write_text(json.dumps(ready, indent=2))
    print(json.dumps(ready), flush=True)
    marker = ROOT/"active-session.json"
    while True:
        try:
            request = json.loads(marker.read_text())
            if request["start_qpc"] >= started:
                if request["condition"].split("-",1)[0] != source:
                    raise RuntimeError("Test condition does not match this Windows recorder's source")
                if request["qpc_frequency"] != FREQUENCY:
                    raise RuntimeError("QPC frequencies do not match")
                folder = Path(request["session"]).resolve()
                if not folder.is_relative_to((ROOT/"sessions").resolve()):
                    raise RuntimeError("Session path is outside the capture directory")
                return request, folder
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.02)


def capture_xinput(writer, stop_at, folder, stats):
    found = xi.connected()
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one physical XInput slot, found {len(found)}")
    slot = found[0][0]
    stats["slot"] = slot
    writer.writerow(["qpc_ticks","event","slot","connected","packet","buttons","lx","ly","rx","ry","lt","rt"])
    previous = None
    last_row = 0
    check_at = 0
    while qpc() < stop_at:
        now = qpc()
        state = xi.STATE()
        rc = xi.getstate(slot, C.byref(state))
        stats["sampler_calls"] += 1
        if rc:
            writer.writerow([now,"disconnect",slot,0,0,0,0,0,0,0,0,0])
            raise RuntimeError(f"Physical XInput disconnected, status {rc}")
        p = state.pad
        row = (state.packet,p.buttons,p.lx,p.ly,p.rx,p.ry,p.lt,p.rt)
        if row != previous or now-last_row >= FREQUENCY//4:
            event = "change" if row != previous else "heartbeat"
            writer.writerow([now,event,slot,1,*row])
            stats["rows"] += 1
            stats.setdefault("first_qpc",now)
            last_row = now
            previous = row
        if now >= check_at:
            stats["last_qpc"] = now
            if (folder/"finished.json").exists():
                break
            check_at = now + FREQUENCY//10
        time.sleep(.0002)


def capture_hid(writer, stop_at, folder, stats, devices):
    matches = [d for d in devices if d.get("caps",{}).get("UsagePage") == 1
               and d["caps"]["Usage"] in (4,5)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one 8BitDo HID gamepad collection, found {len(matches)}")
    info = matches[0]
    stats["vid_pid"] = info["vid"]+":"+info["pid"]
    handle = hid.openfile(info["path"],0x80000000,3,None,3,0x40000000,None)
    if handle == hid.INVALID:
        raise OSError(C.get_last_error(),"Cannot open shared read-only HID handle")
    event = hid.event(None,True,False,None)
    ov = hid.OVERLAPPED(hEvent=event)
    buffer = C.create_string_buffer(info["caps"]["InputReportByteLength"])
    writer.writerow(["qpc_ticks","report_hex"])
    check_at = 0
    try:
        while qpc() < stop_at:
            hid.reset(event)
            n = hid.W.DWORD()
            if not hid.read(handle,buffer,len(buffer),C.byref(n),C.byref(ov)):
                code = C.get_last_error()
                if code != 997:
                    raise OSError(code,"HID ReadFile")
                if hid.wait(event,100) == 258:
                    hid.cancel(handle,C.byref(ov))
                    hid.getover(handle,C.byref(ov),C.byref(n),True)
                    if (folder/"finished.json").exists():
                        break
                    continue
                if not hid.getover(handle,C.byref(ov),C.byref(n),False):
                    raise OSError(C.get_last_error(),"HID GetOverlappedResult")
            now = qpc()
            if n.value:
                writer.writerow([now,buffer.raw[:n.value].hex()])
                stats["rows"] += 1
                stats.setdefault("first_qpc",now)
                stats["last_qpc"] = now
            if now >= check_at:
                if (folder/"finished.json").exists():
                    break
                check_at = now + FREQUENCY//10
    finally:
        hid.cancel(handle,None)
        hid.close(event)
        hid.close(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["xinput","hid"], required=True)
    args = parser.parse_args()
    if os.environ.get("SteamAppId") or os.environ.get("SteamGameId"):
        raise RuntimeError("Launch the Windows recorder outside Steam, without Steam app environment variables")
    stats = {"source": args.source,"rows":0,"sampler_calls":0,"qpc_frequency":FREQUENCY}
    folder = None
    try:
        request, folder = wait_for_session(args.source)
        devices = describe_devices()
        if not devices:
            raise RuntimeError("No physical 8BitDo HID interfaces found")
        context = {"request":request,"capture_start_qpc":qpc(),
                   "devices":[{k:v for k,v in d.items() if k!="path"} for d in devices],
                   "outside_steam_xinput_slots":[i for i,_ in xi.connected()],
                   "scope":"Windows API/report capture; not physical latency or USB-bus timing"}
        (folder/"windows-context.json").write_text(json.dumps(context,indent=2))
        if args.source == "hid" and context["outside_steam_xinput_slots"]:
            raise RuntimeError("XInput slots are visible during native HID test; resolve extra devices before recording")
        stats["capture_start_qpc"] = qpc()
        with (folder/f"windows-{args.source}.csv").open("x",newline="") as stream:
            writer = csv.writer(stream)
            if args.source == "hid":
                capture_hid(writer,request["stop_qpc"],folder,stats,devices)
            else:
                capture_xinput(writer,request["stop_qpc"],folder,stats)
        stats["outcome"] = "finished"
        finished = folder/"finished.json"
        if finished.exists():
            stats["steam_outcome"] = json.loads(finished.read_text())["outcome"]
    except Exception as exc:
        stats["outcome"] = "error"
        stats["error"] = str(exc)
        raise
    finally:
        stats["capture_end_qpc"] = qpc()
        if "capture_start_qpc" in stats:
            stats["capture_elapsed_seconds"] = (stats["capture_end_qpc"]-stats["capture_start_qpc"])/FREQUENCY
        if folder:
            (folder/"windows-summary.json").write_text(json.dumps(stats,indent=2))
        (ROOT/"physical-ready.json").write_text(json.dumps({"status":"stopped","process":os.getpid()}))
        print(json.dumps(stats,indent=2),flush=True)


if __name__ == "__main__":
    main()
