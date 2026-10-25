# Receiver firmware change

## Input and address mapping

The patched input is the official receiver 1.06 `.dat` file, 40,476 bytes, SHA-256:

```text
1018a299f3662098fcd7d2a71789d1290bb7603dd1998fe03759c5643cd05401
```

Its 28-byte outer header precedes a 40,448-byte application payload. The application maps to flash base `0x5000`. A RAM-code prefix also runs at low RAM aliases; adding `0x5000` to every call target gives incorrect cross-region references. The instruction stream was decoded as Telink TC32. The exact chip part was not identified.

The native axis block is at payload offset `0x6B7E`, `.dat` offset `0x6B9A`, flash address `0xBB7E`. It occupies 46 bytes through `0xBBAB`. The original 46-byte conversion block is identical in inspected receiver versions 1.04 and 1.06. Only 1.06 was physically patched and tested.

## Data path

The receive handler at RAM `0x14A4` processes frame type `0x73`. The inspected state buffers include:

| State | Address | Bytes |
| --- | --- | ---: |
| Buttons | `0x843644` | 4 |
| Left stick pair | `0x84363C` | 4 |
| Right stick pair | `0x843640` | 4 |
| Triggers | `0x843648` | 2 |

The XInput caller at flash `0xBC78` and native HID caller at `0xBEB4` consume these buffers. XInput's packer at RAM `0x19D0` reconstructs the full source words. Native HID's packer at flash `0xB9F8` originally extracts only the high bytes of each source axis.

Live receiver testing established that the low bytes vary in native mode. The controller already supplies them; no controller firmware change was required.

## Replacement

`tools/receiver_fragment.py` contains the 23 replacement halfwords and a bounded interpreter for the instructions used by the original and modified fragments. The replacement fits in the original 46-byte block. It adds four aligned halfword stores to existing vendor bytes while preserving the four legacy byte stores and the inspected downstream live registers.

The fragment uses 16-bit stores relative to the payload buffer. The final report includes a leading ID byte, so the added word offsets become 11, 27, 29 and 31. The descriptor and 34-byte report size stay unchanged.

## Integrity

The payload's declared program length is the little-endian u32 at offset `0x18`. For this image it is 40,308 bytes (`0x9D74`). Two integrity words must be updated:

```python
crc_offset = program_length - 4
crc = (~zlib.crc32(payload[:crc_offset])) & 0xffffffff
byte_sum = sum(payload[:crc_offset]) & 0xffffffff
# CRC at crc_offset; byte sum immediately afterward.
```

The corresponding flash addresses are `0xED70` and `0xED74`. The byte-sum rule was traced in the receiver's read-back boot code at function `0x1E4`, called from `0x102E`. Updating the CRC alone leaves the boot byte-sum check invalid.

The modified application differs at **43 byte positions**: 37 in the conversion block and 6 in the integrity words. It is the same length as the original. [Patch metadata](../patches/receiver.json) lists the changed flash addresses.

| Payload | SHA-256 |
| --- | --- |
| Stock | `e5bc101ea9b9f1c970a7fbffe4a92261400ad49cbdb58d4190d08a6fd404b3fe` |
| Modified | `7f47efe7dd3bb08f648a7602ec600a7d6675cb377bbfc3bf8925bbbccfa63e01` |

Outer `.dat` integrity/updater acceptance was not resolved. `patch_receiver.py` therefore writes a raw application payload, not a repackaged OEM update.

## Physical write procedure tested

The receiver's application supports a software transition to its boot interface; the tested receiver has no user-accessible pairing/update button. Recovery/boot identity was `2DC8:6013`. The reviewed raw boot procedure erased and programmed only two 4 KB application sectors, `0xB000` and `0xE000`.

Original sectors were rewritten first, read back, and compared. The full application readback matched stock and the receiver restarted. The diagnostic was then written with the same sector boundaries. Both sectors and the full application matched the prepared output on readback. Normal native HID, wireless XInput and a receiver/controller power cycle were checked afterward.

The boot area `0x0000..0x4FFF`, update metadata at `0x12000`, staging area at `0x13000`, upper configuration area and physical controller were excluded from writes. Erasing 8,192 bytes was necessary even though only 43 bytes differed. Receiver identifiers, firmware version 1.06 and HID descriptors were retained.

The tested boot packet is 65 bytes: report byte `00`, prefix `05`, then `<HHIII` command/parameters/length-or-CRC/second-length/address, followed by data and zero padding. Command 4 erases one aligned 4 KB sector; command 3 programs data. The tested program size was at most 46 bytes, split at 256-byte pages and sector boundaries. Program packets carry reflected CRC16, initial value `FFFF`, polynomial `A001`, in the upper 16 bits of the first length word. Readback verification is required independently of a successful command return.

This protocol description records the tested procedure. It does not establish recovery from a failed modified application, support for other receivers, or safe use of another unit's configuration/backup. See [recovery](recovery.md).
