# Controller 1.10: Home starts native HID

Tested October 29, 2026 on one Ultimate 2 Wireless Controller for PC and its receiver. The receiver already had the precision extension, and Steam already had the matching reader. This experiment changed the controller firmware only.

## Observed behavior

All wireless tests used the rear switch in 2.4G with the controller's USB cable disconnected.

| Test | Stock controller | Patched controller | Evidence |
| --- | --- | --- | --- |
| Home-only start after shutdown and five-second wait | XInput | HID, `2DC8:6012` | Windows enumeration |
| B + Home start after shutdown and five-second wait | HID | XInput, `2DC8:310B` | Windows enumeration |
| Quick Home-only restart | XInput | Not repeated | Stock Windows enumeration |
| Dock/lift starting in HID | HID retained | HID retained | Stock final state captured; patched result reported by owner |
| Dock/lift starting in XInput | Not tested | XInput retained | Reported by owner |

The two patched dock transitions were not captured independently. After the owner's reply, Windows showed an idle receiver (`2DC8:6013`); that later snapshot does not establish the cause of the idle state or verify either transition.

The requested Home and B+Home behavior was verified. Extended gameplay, battery life, auto-sleep/wake, receiver power cycles and PC restart behavior were not evaluated for this startup patch. The earlier precision/gameplay captures predate it.

## Mode selection

The receiver boots with USB mode 4, idle, rather than an XInput default. Its connection selector at RAM `0x948` reads classification byte `0x8432BC`:

| Classification | Receiver USB mode |
| --- | --- |
| `0x73`, `0x77`, `0xAD` | DInput/native HID |
| `0x70`, `0x76`, `0xAC` | Switch |
| Other values | XInput fallback |

Several receive handlers copy byte 5 of the received buffer into that classification byte. The full radio protocol has not been decoded.

The controller's frame builder at RAM `0xDE8` reads mode byte `0x84615D`. Value 1 selects type `0x73`, value 2 selects `0x70`, and the default type is `0xB0`. The controller's reset code clears the RAM region containing that mode byte.

The startup initializer at flash `0xFF94` contains the selection block at `0x10044..0x10063`. It reads key-state word `0x845FE8`. Starting from reset mode 0, its original behavior is:

```text
if keys & 0x21000: mode = 1
else if keys & 0x20020: mode = 2
else: mode remains 0
```

The replacement is:

```text
if keys & 0x21000: mode = 0
else if keys & 0x20020: mode = 2
else: mode = 1
```

The current HID shortcut therefore becomes XInput, and the no-shortcut case becomes HID. The live B+Home test established the resulting shortcut behavior. Individual physical pin-to-button mappings have not been established. The existing Switch-mask priority is retained from the reset baseline; Switch startup was not physically tested after this change. Other shortcut combinations, including X+Home, were not retested.

The replacement fits the existing 32-byte block and reuses the literal pool and return instruction. Twenty-one instruction bytes differ. It does not add a code area or change the firmware layout. A warm invocation without shortcut bits now writes mode 1 instead of leaving retained state alone; the complete dock/sleep control flow is not established.

## Input, offsets and integrity

The generator accepts only the stock controller 1.10 `.dat`, 145,436 bytes:

```text
968edee528c23d56e2059288f90c109fa5135f060de5b403e72d0b6c50f5eb87
```

Its 28-byte wrapper precedes a 145,408-byte raw application payload at flash base `0x5000`. The code block is at payload offset `0xB044`, `.dat` offset `0xB060`. The declared program length at payload `0x18` is `0x17A64` (96,868 bytes).

The application CRC is `~zlib.crc32(payload[:program_length-4]) & 0xffffffff`; the byte sum is `sum(payload[:program_length-4]) & 0xffffffff`. The words are stored at payload offsets `program_length-4` and `program_length`, or flash `0x1CA60` and `0x1CA64`.

There are **27 differing byte positions**: 21 in the selector and six in the integrity words. Physical erase/program operations covered two 4 KiB sectors, `0x10000` and `0x1C000`. Each full sector was reconstructed from the tested unit's backup; the write size was 8,192 bytes rather than 27 bytes.

| Compared region | Stock SHA-256 | Modified SHA-256 |
| --- | --- | --- |
| Complete raw payload, 145,408 bytes | `43d8cd222586f8a118d867cb60b0711dee504aed1354d548958d0e985dac30e7` | `08eb82611760db9200b2d435138c3b0e565a70830a4934f22ce577773f3816a1` |
| Declared program and both integrity words, 96,872 bytes | `d7fdb52f7e5a2f632eb850358c674833e73324bfdb426927e4cadfd71fc0ced2` | `14694a61ab1fd6fe525622e71b7c37fc4e1cfaca22e77c79d4e15eeafff6db25` |

The 96,872-byte modified program hash was verified on the physical controller. The complete raw payload hash describes the generated file; a complete 145,408-byte modified payload was not read back from the device. Bytes outside the program were retained from the official input by the generator.

The version response remains **1.10**. The hash, not that version response, identifies the modified program. [Patch metadata](../patches/controller-startup.json) lists exact changed addresses.

## Verification

Before writing, two readbacks matched for flash `0..0x1FFFF` and `0x70000..0x7FFFF`. The installed program matched stock 1.10 through both integrity words. This was a bounded backup, not a claimed whole-chip dump.

The controller's normal USB vendor interface accepted command 5 reads. Software recovery entry used `81 05 00 51 00`, traced to the existing boot handler. Boot mode enumerated as `2DC8:3208`. Boot-header, program-header and startup-block reads matched the backups. Command 7 returned the controller to normal USB `2DC8:310B`.

The two original sectors were rewritten first. Both sectors and the complete program read back unchanged, and the controller restarted with a 1.10 response. The candidate was then written using the same sector boundaries. Sector verification, complete program comparison and restart all passed.

Postflight normal-USB reads of `0..0x1FFFF` matched the prepared candidate exactly and differed from the original at precisely 27 addresses. The bootloader and the separately backed-up upper-storage region were unchanged. The receiver and Steam were not written during this trial.

The private sector runner was checked against a NOR model for stock rewrite, candidate application, restoration and an interrupted transfer. Missing acknowledgement after an erase attempt suppressed automatic restart of partial application code. The published instruction runner checks all eight relevant mask-bit combinations with 256 variations of other bits/registers, for 2,048 cases. The fragment was also decoded with the pinned TC32 disassembler. These are bounded checks, not full hardware emulation.

[Sanitized results](../evidence/controller-startup/results.json) distinguish measured results from owner observations.

## Generate files locally

```powershell
python tools/test_controller_startup.py
python tools/patch_controller_startup.py --input inputs/ultimate2-wireless-controller-v1.10.dat --output-dir artifacts/controller-startup
```

The generator writes the modified raw application, an unmodified raw stock copy and a hash/change manifest. It refuses a different input hash and existing output filenames. It performs no device I/O. Neither raw output is an OEM update package or a complete flash backup.

No general-purpose controller flasher is included. A normal software recovery transition was verified; hardware-button recovery, a failure that prevents normal application USB access, and physical candidate-to-stock restoration were not tested. The stock rewrite demonstrates writing original sector bytes while the application is healthy. It does not establish recovery from every failure. Do not copy another unit's configuration or full flash backup. See [recovery limits](recovery.md#controller).
