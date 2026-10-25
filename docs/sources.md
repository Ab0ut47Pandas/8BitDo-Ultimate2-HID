# Sources

The source catalog and hashes were recorded during the investigation. Download links may change; verify SHA-256 before comparing or generating a patch. Full inputs are not stored in this repository.

## Official firmware files

| Component | Version | Bytes | Source |
| --- | --- | ---: | --- |
| Controller | 1.10 | 145,436 | [8BitDo download](https://support.8bitdo.cn/bd-uploads/files/2026-05/dce4031137ac325384afbc6c3ba2f269.dat) |
| Controller | 1.09 | 145,436 | [8BitDo download](https://support.8bitdo.cn/bd-uploads/files/2026-01/f49da7b0ff8bb0747c17cd624866216b.dat) |
| Receiver | 1.06 | 40,476 | [8BitDo download](https://support.8bitdo.cn/bd-uploads/files/2025-09/7607115e6716732ae948b19514560cfe.dat) |
| Receiver | 1.04 | 40,476 | [8BitDo download](https://support.8bitdo.cn/bd-uploads/files/old/d8b942df-1d27-4aa4-b827-ca98be108a82.dat) |

Full hashes are in [firmware-sources.json](../evidence/firmware-sources.json). The receiver generator supports only the recorded 1.06 file. The other images were inspection references.

## Public implementation references

- [SDL 8BitDo HIDAPI reader](https://github.com/libsdl-org/SDL/blob/3da8c67d8d045c139d8fb77dd11934b606ceacdd/src/joystick/hidapi/SDL_hidapi_8bitdo.c): pinned source used to understand report offsets and byte scaling. The shipped Steam DLL was inspected and tested separately.
- [Telink B85 startup source](https://github.com/telink-semi/tc_platform_sdk/blob/19fbf0cd289e558a4c299734380746e91ebdcd3f/chip/B85/boot/cstartup_flash.S): reference for startup structure and RAM-code loading.
- [Telink linker source](https://github.com/telink-semi/tc_platform_sdk/blob/19fbf0cd289e558a4c299734380746e91ebdcd3f/project/tlsr_tc32/B85/boot.link): reference for split RAM-code/text layout.

These Telink references support the address interpretation. They do not identify the exact receiver chip, OEM source tree or build configuration.

The Steam patch targets the original DLL hash recorded in [steam-reader.md]. No supported download URL for that exact Steam library is asserted. Obtain it from an existing matching installation or backup; a current Steam build may differ.

## Published evidence

`evidence/capture-index.json` contains normalized capture hashes, source-file hashes and row counts. QPC timestamps are relative to the shared session start, preserving physical/Steam timing alignment. CSV compression uses a deterministic gzip timestamp. Raw report bytes and game-facing input values are otherwise retained.

Result files contain observed measurements. Source paths, serial numbers, USB history and local process metadata were removed during export. The gameplay publication is a summary snapshot; the full long gameplay recording remains local.
