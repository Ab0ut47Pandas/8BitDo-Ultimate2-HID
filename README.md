# 8BitDo Ultimate 2 Wireless: native HID precision and startup mode

Controller and receiver firmware patches, analysis and Windows/Steam measurements for the **8BitDo Ultimate 2 Wireless Controller for PC** and its included 2.4 GHz receiver.

Precision tests: October 24, 2026. Startup-mode tests: October 29, 2026. Hardware coverage: one controller/receiver pair, controller firmware **1.10**, receiver firmware **1.06**.

## Result

The stock receiver reduces four 16-bit source stick values to four 8-bit values when building its native HID report. The finer values reach the receiver in this mode; they are discarded during report construction.

A receiver patch copies those source words into eight previously zero vendor bytes. It preserves the existing axes, buttons, triggers, descriptor, report length and device identity. A matching patch to Steam's local `SDL3.dll` reads the added words.

The paired precision test confirmed fine stick values and four separately bound extra buttons through Steam Input, with the software bridge stopped and HidHide disabled. That October 24 experiment did not change the controller firmware. The optional startup patch below was tested separately.

```text
controller 1.10 -> patched receiver 1.06 -> patched Steam reader -> Steam Input -> game
```

Both patches are required for this direct path. The receiver patch alone leaves Steam using the original 8-bit fields. An unmodified Steam installation on another PC will also use those fields.

## Optional HID startup patch

A controller 1.10 patch swaps the wireless startup selection:

| Startup action | Result confirmed in Windows |
| --- | --- |
| Home alone after shutdown | Native HID, `2DC8:6012` |
| B + Home after shutdown | XInput, `2DC8:310B` |

The owner also tested dock/lift in both modes and reported that each retained its selected mode. Those dock transitions were not independently captured.

The patch changes 21 code bytes and six integrity bytes across two controller application sectors. The version response remains 1.10. Startup selection does not require a bridge or a modified Steam reader; the fine-axis path above still requires the receiver and reader patches.

[Startup patch, write verification and limits](docs/controller-startup.md). The generator below runs offline and accepts only the exact stock 1.10 file. No controller flasher, full firmware image or device backup is published.

## Measurements

Distinct output codes observed during the stock two-minute recordings:

| Connection | Windows LX / LY / RX / RY | Steam LX / LY / RX / RY |
| --- | --- | --- |
| Wireless XInput | 13,376 / 13,378 / 15,370 / 15,482 | 8,325 / 8,380 / 9,695 / 9,797 |
| Wired XInput | 15,618 / 15,081 / 17,792 / 18,303 | 9,602 / 9,348 / 11,231 / 11,629 |
| Wireless native HID | 255 / 256 / 255 / 256 | 255 / 256 / 255 / 256 |

The stock wireless HID capture averaged approximately 1,000 report arrivals per second. USB connection returned the controller to XInput; wired native HID was not established using the tested mode selection.

The 60-second paired capture with both patches installed produced:

| Axis | Legacy byte codes | Fine receiver codes | Steam output codes |
| --- | ---: | ---: | ---: |
| LX | 255 | 10,658 | 6,554 |
| LY | 256 | 10,656 | 6,469 |
| RX | 255 | 11,506 | 6,910 |
| RY | 256 | 11,736 | 7,120 |

There were 59,969 physical reports, approximately 1,000.025 arrivals/sec, and no disconnects. Each of PL, PR, L4 and R4 was pressed twice and matched its separate diagnostic binding. No PC interpolation was added.

A later Witcher 3 capture covered 52 minutes 40 seconds and 3,159,783 physical reports. Median host read interval was 0.9994 ms; the 99th percentile was 1.0895 ms. No malformed reports or fine/legacy axis mismatches were found. Three read gaps above 5 ms occurred within a 0.2-second period; the largest was 16.7893 ms. Their cause was not established. See [measurements](docs/measurements.md).

Code counts depend on movement and sampling. They do not establish sensor accuracy or ADC bit depth. Report arrivals, changed stick states, Steam processing frequency and input latency are separate measurements. The receiver patch does not increase the report rate.

## Changes

| Component | Change | Scope |
| --- | --- | --- |
| Controller, optional startup patch | 27 differing bytes, including integrity fields | Application sectors `0x10000` and `0x1C000`; still identifies as 1.10 |
| Receiver | 43 differing bytes, including integrity fields | Application sectors `0xB000` and `0xE000`; still identifies as 1.06 |
| Steam `SDL3.dll` | 296 differing bytes, including PE checksum | Existing 298-byte axis conversion region; exact original hash required |

The firmware version strings are unchanged. Identify a patched build by its hash.

## Files

- [Receiver changes and boot protocol](docs/receiver.md)
- [Controller startup selection patch](docs/controller-startup.md)
- [Native HID report layout](docs/report-format.md)
- [Steam reader patch and local installation](docs/steam-reader.md)
- [Test methods, results and limitations](docs/measurements.md)
- [Restoration and recovery limits](docs/recovery.md)
- [Firmware sources and references](docs/sources.md)
- [Patch generators and offline parser tests](tools/)
- [Capture tools](measurement/)
- [Normalized captures and result files](evidence/)

## Build the patches

Python 3.10 or later is required. Steam parser execution tests require 64-bit Windows and 64-bit Python. The receiver generator uses the Python standard library. The Steam generator requires the packages in `requirements.txt`.

```powershell
python -m pip install -r requirements.txt

python tools/patch_receiver.py --input inputs/ultimate2-wireless-receiver-v1.06.dat --output-dir artifacts/receiver

python tools/patch_controller_startup.py --input inputs/ultimate2-wireless-controller-v1.10.dat --output-dir artifacts/controller-startup
python tools/test_controller_startup.py

python tools/build_steam_patch.py --input inputs/SDL3.dll --output-dir artifacts/steam
python tools/test_steam_reader.py original --directory artifacts/steam
python tools/test_steam_reader.py candidate --directory artifacts/steam
```

The generators refuse inputs with a different SHA-256. They write to a separate output directory. They do not flash hardware or replace Steam files. Full manufacturer firmware, controller/receiver backups and Steam DLLs are excluded from this repository. [Source URLs and hashes](docs/sources.md) identify the required inputs.

The receiver output is a raw application payload for flash base `0x5000`. It is not an OEM `.dat` update package. No general-purpose receiver flasher is supplied; the tested sector procedure and its limits are documented.

The controller startup generator also writes raw application payloads, including an unmodified stock copy. Neither output is a complete device backup or an OEM update package. It does not write to the controller.

## Compatibility limits

Only the hardware and binary hashes recorded here were tested. The receiver sectors were physically written and read back on one device. Restoration of stock sectors was tested before installing the diagnostic; recovery from a failed modified application was not tested.

Steam updates can replace its patched reader. The patch must be reviewed again for a different DLL hash. Rumble, motion controls, battery life and compatibility with other host software remain unverified. Existing game layouts were retained; the independent button test used a separate diagnostic layout.

Receiver firmware writing can leave the receiver unusable. Preserve the original contents before writing and review the recovery limits before attempting a hardware change.

The controller startup patch was written and verified on one unit. A stock sector rewrite passed first. Recovery through the normal software command was tested; hardware-button recovery and recovery from an unusable application were not established. See [controller recovery limits](docs/recovery.md#controller).
