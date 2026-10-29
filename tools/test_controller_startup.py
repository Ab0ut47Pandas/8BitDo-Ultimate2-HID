"""Offline startup selection and integrity checks. No controller required."""
import random
import struct
import tempfile
import unittest
from pathlib import Path
import zlib

from controller_startup_fragment import ORIGINAL, REPLACEMENT, HID_SHORTCUT_MASK, SWITCH_MASK, execute
from patch_controller_startup import build, transform
from patch_receiver import verify


class StartupTests(unittest.TestCase):
    def test_all_mask_classes_and_unrelated_bits(self):
        relevant = (5, 12, 17)
        union = HID_SHORTCUT_MASK | SWITCH_MASK
        for selection in range(8):
            bits = sum(1 << bit for i, bit in enumerate(relevant) if selection & (1 << i))
            stock = 1 if bits & HID_SHORTCUT_MASK else 2 if bits & SWITCH_MASK else 0
            changed = 0 if bits & HID_SHORTCUT_MASK else 2 if bits & SWITCH_MASK else 1
            for seed in range(256):
                rng = random.Random(seed)
                keys = bits | (rng.getrandbits(32) & ~union)
                regs = [rng.getrandbits(32) for _ in range(8)]
                self.assertEqual(execute(ORIGINAL, keys, registers=regs)['mode'], stock)
                actual = execute(REPLACEMENT, keys, registers=regs)
                self.assertEqual(actual['mode'], changed)
                self.assertEqual(actual['writes'], [changed])
                self.assertEqual(actual['return_at'], 0x10062)

    def test_flag_changing_move_cannot_replace_the_shortcut_test(self):
        broken = bytearray(REPLACEMENT)
        struct.pack_into('<H', broken, 8, 0xa000)  # movs r0, 0, instead of test
        self.assertNotEqual(execute(broken, 0x1000)['mode'], 0)

    def test_unknown_input_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'unsupported.dat'
            source.write_bytes(b'unsupported firmware')
            output = Path(temp) / 'output'
            with self.assertRaises(ValueError):
                build(source, output)
            self.assertFalse(output.exists())
        with self.assertRaises(ValueError):
            transform(bytes(145436))

    def test_both_integrity_words_are_required(self):
        payload = bytearray(68)
        struct.pack_into('<I', payload, 0x18, 64)
        struct.pack_into('<II', payload, 60, (~zlib.crc32(payload[:60])) & 0xffffffff, sum(payload[:60]))
        self.assertEqual(verify(payload), 64)
        payload[32] ^= 1
        with self.assertRaises(ValueError):
            verify(payload)
        struct.pack_into('<I', payload, 60, (~zlib.crc32(payload[:60])) & 0xffffffff)
        with self.assertRaises(ValueError):
            verify(payload)


if __name__ == '__main__':
    unittest.main()
