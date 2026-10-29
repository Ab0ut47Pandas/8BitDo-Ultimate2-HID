"""Controller 1.10 startup selection block and bounded offline instruction runner."""
import struct

ENTRY = 0x10044
END = 0x10064
KEYS = 0x845fe8
MODE = 0x84615d
HID_SHORTCUT_MASK = 0x21000
SWITCH_MASK = 0x20020
ORIGINAL = bytes.fromhex('120b1a58120b1a0202c002a1110b194084a39bf21a0202c001a20e0b1a40306d')
REPLACEMENT = struct.pack('<16H',
    0x0812,  # load r0, key-state pointer literal
    0x5800,  # load r0, [r0]
    0xa184,  # movs r1, 132
    0xf289,  # shift r1 left 10 -> 0x21000
    0x0208,  # test r0, r1
    0xc001,  # equal -> no shortcut bits, 0x10054
    0xa200,  # movs r2, 0 -> XInput
    0x8004,  # jump to store, 0x1005e
    0xa201,  # movs r2, 1 -> default HID
    0x090f,  # load r1, Switch-mask literal
    0x0208,  # test r0, r1
    0xc000,  # equal -> store default
    0xa202,  # movs r2, 2 -> Switch
    0x0b0e,  # load r3, mode-byte pointer literal
    0x401a,  # store byte r2, [r3]
    0x6d30,  # existing pop {r4, r5, pc}
)


def execute(code, keys, initial_mode=0, registers=None):
    """Run this selection block only. No peripheral, radio or device emulation.

    The literal addresses are the existing stock 1.10 pool, verified separately
    by the patch generator. Only its key-word load and mode-byte stores exist in
    this model. Stop before executing the original stack-pop return.
    """
    if len(code) != END - ENTRY:
        raise ValueError('Expected the 32-byte selection block')
    regs = list(registers) if registers is not None else [0] * 8
    if len(regs) != 8:
        raise ValueError('Expected eight low registers')
    initial_preserved = regs[4:]
    literals = {0x10090: KEYS, 0x10094: SWITCH_MASK, 0x10098: MODE}
    mode, writes, pc, zero = initial_mode, [], ENTRY, False
    for _ in range(32):
        if not ENTRY <= pc < END or pc & 1:
            raise ValueError('Execution escaped the selection block')
        op = struct.unpack_from('<H', code, pc - ENTRY)[0]
        nxt = pc + 2
        if op & 0xf800 == 0x0800:
            address = ((pc + 4) & ~3) + (op & 255) * 4
            regs[(op >> 8) & 7] = literals[address]
        elif op & 0xf800 == 0x5800:
            address = regs[(op >> 3) & 7] + ((op >> 6) & 31) * 4
            if address != KEYS:
                raise ValueError('Unexpected word read')
            regs[op & 7] = keys & 0xffffffff
        elif op & 0xf800 == 0xa000:
            regs[(op >> 8) & 7] = op & 255
            zero = (op & 255) == 0
        elif op & 0xf800 == 0xf000:
            regs[op & 7] = (regs[(op >> 3) & 7] << ((op >> 6) & 31)) & 0xffffffff
            zero = regs[op & 7] == 0
        elif op & 0xffc0 == 0x0200:
            zero = (regs[op & 7] & regs[(op >> 3) & 7]) == 0
        elif op & 0xff00 == 0xc000:
            displacement = op & 255
            if displacement & 128:
                displacement -= 256
            if zero:
                nxt = pc + 4 + displacement * 2
        elif op & 0xf800 == 0x8000:
            displacement = op & 2047
            if displacement & 1024:
                displacement -= 2048
            nxt = pc + 4 + displacement * 2
        elif op & 0xf800 == 0x4000:
            address = regs[(op >> 3) & 7] + ((op >> 6) & 31)
            if address != MODE:
                raise ValueError('Unexpected write destination')
            mode = regs[op & 7] & 255
            writes.append(mode)
        elif op == 0x6d30:
            if regs[4:] != initial_preserved:
                raise ValueError('Preserved register changed')
            return {'mode': mode, 'writes': writes, 'return_at': pc}
        else:
            raise ValueError(f'Unsupported instruction {op:04x} at {pc:x}')
        pc = nxt
    raise ValueError('Instruction bound exceeded')
