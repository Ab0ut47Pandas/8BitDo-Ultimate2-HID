# Steam reader patch

The tested Windows x64 `SDL3.dll` reports version 3.5.0 and is 3,093,144 bytes. The SHA-256 is the build identifier used by the tools:

| File | SHA-256 |
| --- | --- |
| Original | `e8656a70d57eb5cfa5e20a4c96c45f7f72325a3a109135e919d033f233fa3fb7` |
| Patched | `55a6d7993ad945fa26ee30b046d553e3c1d7c7b8f97c064e491158af1aad30df` |

The generator refuses a different original hash. Matching the version string alone is insufficient.

## Conversion

The patch replaces the existing 298-byte axis conversion region at RVA `0xDEC5B..0xDED85`, file offset `0xDE05B`. It contains 258 bytes of code/table data followed by NOP padding. The PE checksum at file offset `0x160` is regenerated. There are 296 differing bytes overall.

The extension is accepted only when all of these checks pass:

1. Joystick VID/PID is `2DC8:6012`.
2. The report length is exactly 34 bytes and ID is 1.
3. The four extension words are not all zero.
4. Every original byte axis agrees with its corresponding extension word's high-byte conversion.

If any check fails, the parser uses the original float-based byte conversion. The fine path sends the four signed values described in [report format](report-format.md). The existing downstream axis function performs its normal remapping and event delivery.

DLL size, sections, imports, exports, relocations and unwind tables are unchanged. The change stays within the existing function. Button, trigger, battery and sensor handling is outside the modified region. Exact offsets, labels and guards are in [patch metadata](../patches/steam-reader.json).

## Build and parser replay

Copy the supported original DLL into a local input directory. The generator backs up that input inside the selected build directory; the DLL is not supplied here.

```powershell
python -m pip install -r requirements.txt
python tools/build_steam_patch.py --input inputs/SDL3.dll --output-dir artifacts/steam
python tools/test_steam_reader.py original --directory artifacts/steam
python tools/test_steam_reader.py candidate --directory artifacts/steam
```

The tests load each copied DLL in its own process and execute its actual parser. Physical input backends are disabled before SDL initialization. The test joystick is private to that SDL process; it does not create a Windows HID device. The tools do not need Steam to exit for this offline replay.

The test covers 262,144 fine-axis cases, all 45,252 saved receiver-motion reports, buttons/hat/triggers, 4,096 fallback cases and 256 wrong-PID cases. The candidate's stock replay digest must equal the original's digest. The tests use internal addresses and structures from this exact DLL, so the file hash is checked before loading it.

## Local installation

Save and close Steam games, then exit Steam fully. Keep `artifacts/steam/original/SDL3.dll` as the original backup. The optional installer verifies both file hashes and completed replay results before replacing the known original:

```powershell
./tools/Set-SteamReader.ps1 -SteamDirectory 'C:\Program Files (x86)\Steam' -BuildDirectory ./artifacts/steam -Action Install
```

Use the actual Steam installation directory. Windows permissions may require an elevated shell. This installer is a portable adaptation of the local installation procedure. Installation/restoration on disposable file copies, refusal while Steam is running, and refusal to overwrite an unknown build passed in Windows PowerShell 5.1. The published command-line interface was not used to reinstall the live Steam library or tested on another PC.

The receiver must already carry the tested extension. Start the controller in wireless native HID with the receiver connected and USB cable unplugged. On the tested unit, B + Home from fully off with the rear switch on 2.4G selected this mode. Verify `2DC8:6012` before attributing any measurement to it.

Steam recognizes the physical controller through its 8BitDo reader. No bridge or HidHide is required for the direct path. Game bindings remain per-game settings.

## Updates

Steam may replace its SDL library during an update. Recheck the hash afterward. Do not apply these offsets to a different binary, and do not use this repository's restoration script to overwrite an unknown newer DLL. A new Steam build requires fresh inspection and parser replay.
