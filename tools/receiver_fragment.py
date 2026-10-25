"""46-byte TC32 fragment and its bounded offline instruction model."""
import struct

ASSEMBLY = [
    (0x0651, 'tmov r1, sl'),
    (0x214e, 'tstorerh r6, [r1, #10]'),   # LX full word, report offset 11
    (0xfc30, 'tshftrs r0, r6, #16'),
    (0x2348, 'tstorerh r0, [r1, #26]'),   # LY, report offset 27
    (0x238f, 'tstorerh r7, [r1, #28]'),   # RX, report offset 29
    (0xfc38, 'tshftrs r0, r7, #16'),
    (0x23c8, 'tstorerh r0, [r1, #30]'),   # RY, report offset 31
    (0xf433, 'tshftls r3, r6, #16'),
    (0xfe1b, 'tshftrs r3, r3, #24'),
    (0xab7f, 'tcmp r3, #127'),
    (0xc000, 'tjeq skip one inversion instruction'),
    (0x03db, 'tmovns r3, r3'),
    (0x404b, 'tstorerb r3, [r1, #1]'),
    (0xfe36, 'tshftrs r6, r6, #24'),
    (0x408e, 'tstorerb r6, [r1, #2]'),
    (0xf43b, 'tshftls r3, r7, #16'),
    (0xfe1b, 'tshftrs r3, r3, #24'),
    (0xab7f, 'tcmp r3, #127'),
    (0xc000, 'tjeq skip one inversion instruction'),
    (0x03db, 'tmovns r3, r3'),
    (0x40cb, 'tstorerb r3, [r1, #3]'),
    (0xfe3f, 'tshftrs r7, r7, #24'),
    (0x410f, 'tstorerb r7, [r1, #4]'),
]
PROTOTYPE = struct.pack('<'+'H'*len(ASSEMBLY),*(x[0] for x in ASSEMBLY))
ALLOWED_VENDOR_BYTES = {10,11,26,27,28,29,30,31}  # excludes report ID


def emulate(fragment, axes):
    """Small interpreter for only the actual instructions in these fragments.

    No calls, arbitrary addresses, stack, device registers or host I/O.
    It is not a general TC32 emulator or a hardware execution claim.
    """
    regs = [0x12340000+i for i in range(16)]
    regs[6] = axes[0] | (axes[1]<<16)
    regs[7] = axes[2] | (axes[3]<<16)
    regs[10] = 0x1000
    mem = bytearray((i*37+5)&255 for i in range(64))
    pc = steps = 0
    equal = False
    while pc < len(fragment):
        if pc < 0 or pc&1 or steps > 40:
            raise ValueError('Unexpected fragment control flow')
        ins = struct.unpack_from('<H',fragment,pc)[0]
        pc += 2
        steps += 1
        dest, src, imm5 = ins&7, (ins>>3)&7, (ins>>6)&31
        if ins&0xf800 == 0xf000:  # tshftls Rd, Rs, #imm
            regs[dest] = (regs[src]<<imm5)&0xffffffff
        elif ins&0xf800 == 0xf800:  # tshftrs
            regs[dest] = regs[src]>>imm5
        elif ins&0xf800 == 0xa000:  # tmovs
            regs[(ins>>8)&7] = ins&255
        elif ins&0xf800 == 0xa800:  # tcmp immediate
            equal = regs[(ins>>8)&7] == ins&255
        elif ins&0xff00 == 0xc000:  # tjeq, target is original PC+4+offset
            disp = ins&255
            if disp&128:
                disp -= 256
            if equal:
                pc += 2+disp*2
        elif ins&0xffc0 == 0x03c0:  # tmovns
            regs[dest] = (~regs[src])&0xffffffff
        elif ins&0xff00 == 0x0600:  # high-register tmov
            regs[dest|((ins>>4)&8)] = regs[(ins>>3)&15]
        elif ins&0xf800 in (0x4000,0x2000):
            half = ins&0xf800 == 0x2000
            at = regs[src]-0x1000 + imm5*(2 if half else 1)
            n = 2 if half else 1
            if not 0<=at<=len(mem)-n or (half and at&1):
                raise ValueError('Out-of-buffer or unaligned store')
            mem[at:at+n] = (regs[dest]&((1<<(8*n))-1)).to_bytes(n,'little')
        else:
            raise ValueError(f'Unsupported instruction {ins:04x}')
    if pc != len(fragment):
        raise ValueError('Branch beyond fragment')
    return mem,regs


def decode_extension(body):
    # body excludes report ID. These words retain the source orientation,
    # unsigned range and fine values; they are not scaled API axes.
    return [struct.unpack_from('<H',body,x)[0] for x in (10,26,28,30)]


def check_case(original, axes):
    old, old_regs = emulate(original,axes)
    new, new_regs = emulate(PROTOTYPE,axes)
    if decode_extension(new) != axes:
        raise AssertionError(('Fine axis mismatch',axes))
    if any(a!=b and i not in ALLOWED_VENDOR_BYTES for i,(a,b) in enumerate(zip(old,new))):
        raise AssertionError(('Legacy/guard byte changed',axes))
    # r0/r2/r3 are scratch/dead before their next use in the downstream
    # inspected native packer. r1/r6/r7/r8/sl must remain compatible.
    if any(old_regs[r]!=new_regs[r] for r in (1,6,7,8,10)):
        raise AssertionError(('Live register mismatch',axes))
