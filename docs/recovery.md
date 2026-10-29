# Restoration and recovery limits

## Steam

Save and close games and exit Steam fully before replacing its SDL library. The build tool keeps the supported original at `artifacts/steam/original/SDL3.dll`. Verify its hash against [the recorded original](steam-reader.md).

```powershell
./tools/Set-SteamReader.ps1 -SteamDirectory 'C:\Program Files (x86)\Steam' -BuildDirectory ./artifacts/steam -Action Restore
```

The script restores only when the installed file matches the known patched hash. It returns without replacement if the known original is already installed, and refuses an unknown DLL. Steam may have installed a newer library in that case; inspect it before any replacement.

Restoring the host reader makes it use the preserved 8-bit axes. It does not undo the receiver patch.

## Receiver

The physical experiment saved repeated readbacks of the receiver and verified that its application region matched the official 1.06 payload. Original 4 KB sectors at `0xB000` and `0xE000` were retained. A stock erase/program/readback/restart cycle passed before the diagnostic was written.

The same bounded sector plan was simulated in reverse against the diagnostic image. It recreated the original bytes offline. A diagnostic-to-stock rollback was not subsequently exercised on the physical device. Recovery from a damaged application that no longer accepts the normal software boot transition was not demonstrated.

Firmware 1.06 in the version response does not distinguish stock and modified applications. Compare readback hashes. The raw stock application payload hash is:

```text
e5bc101ea9b9f1c970a7fbffe4a92261400ad49cbdb58d4190d08a6fd404b3fe
```

Backups of the boot area, update metadata and upper configuration are device-specific recovery material. They are excluded from this repository. Do not restore another receiver's full flash dump or configuration. The tested sector writes excluded these areas.

The official `.dat` file is an application package, not a complete receiver flash backup. Its presence alone does not prove a recovery route for every failure. Other receiver revisions and firmware versions require their own identity, layout, integrity and recovery checks.

## Controller

The October 29 startup experiment used controller firmware 1.10. Repeated reads saved `0..0x1FFFF` and `0x70000..0x7FFFF`; the installed program matched the exact stock input through both integrity words. The backup includes the full two sectors used by the startup patch, at `0x10000` and `0x1C000`.

Software entry to boot `2DC8:3208`, bounded reads and restart to normal USB `2DC8:310B` were tested before writing. The original sectors were rewritten, verified and restarted before the modified sectors were installed. Physical candidate-to-stock rollback was not subsequently performed; the reverse plan restored the original bytes in the offline NOR model.

The generator supplies an unmodified raw stock application alongside the modified one. These files do not contain a complete controller backup, an OEM `.dat` wrapper or device-specific configuration. Original sector contents from the actual unit are still required for a bounded restore that preserves surrounding data. No controller flasher is supplied.

The patch leaves the bootloader untouched, but hardware-button recovery and recovery from an application that cannot accept the software boot command were not established. An interrupted write or unexpected firmware behavior can leave the controller unusable. Successful readback and normal restart on one unit do not establish recovery for other revisions or failure modes.

The firmware response remains 1.10. [Controller startup documentation](controller-startup.md) distinguishes the full generated payload hashes from the physically compared program hashes.
