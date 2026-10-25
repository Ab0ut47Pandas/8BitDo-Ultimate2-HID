# Native HID report format

Tested device: Ultimate 2 Wireless receiver, VID `2DC8`, PID `6012`, usage page 1, usage 5. Reports are 34 bytes including report ID 1. Offsets below include the report ID.

| Offset | Size | Field |
| --- | ---: | --- |
| 0 | 1 | Report ID, `01` |
| 1 | 1 | Hat in low nibble; 0 up, 2 right, 4 down, 6 left, 15 neutral |
| 2–5 | 4 | Original LX, LY, RX, RY unsigned byte axes |
| 6 | 1 | RT, 0–255 |
| 7 | 1 | LT, 0–255 |
| 8–10 | 3 | Button bits |
| 11–12 | 2 | Added LX source word, little-endian |
| 13 | 1 | Preserved vendor byte |
| 14 | 1 | Existing battery field: low 7 bits level, high bit charging |
| 15–26 | 12 | Existing sensor fields, preserved |
| 27–28 | 2 | Added LY source word, little-endian |
| 29–30 | 2 | Added RX source word, little-endian |
| 31–32 | 2 | Added RY source word, little-endian |
| 33 | 1 | Preserved vendor byte |

The added fields retain the source orientation and unsigned 16-bit range. For SDL axis orientation:

```python
lx = 32767 - u16le(report, 11)
ly = u16le(report, 27) - 32768
rx = 32767 - u16le(report, 29)
ry = u16le(report, 31) - 32768
```

Steam's later XInput translation applies its own conventions, including vertical sign inversion and endpoint handling.

The old fields remain byte-for-byte compatible with the stock conversion. Given `high = source >> 8`, the expected original byte is `high` for Y and `127 if high == 127 else 255 - high` for X. This relation is checked for all four axes before the patched reader accepts the extension. An all-zero extension uses the original parser path.

## Buttons

Bit numbers are zero-based. HID button usages are one-based.

| Control | Byte | Bit | HID usage |
| --- | ---: | ---: | ---: |
| A | 8 | 0 | 1 |
| B | 8 | 1 | 2 |
| PR | 8 | 2 | 3 |
| X | 8 | 3 | 4 |
| Y | 8 | 4 | 5 |
| PL | 8 | 5 | 6 |
| LB | 8 | 6 | 7 |
| RB | 8 | 7 | 8 |
| View | 9 | 2 | 11 |
| Menu | 9 | 3 | 12 |
| Home | 9 | 4 | 13 |
| L3 | 9 | 5 | 14 |
| R3 | 9 | 6 | 15 |
| L4 | 10 | 0 | 17 |
| R4 | 10 | 1 | 18 |

The extra controls were identified by ordered physical presses and Windows HID parser output. Their lower-numbered usages do not make PL or PR aliases of ordinary controls. Steam bindings can intentionally map distinct physical controls to the same game-facing button.
