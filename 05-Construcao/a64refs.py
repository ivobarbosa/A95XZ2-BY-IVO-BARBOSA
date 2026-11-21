"""Tiny AArch64 scanner: list ADRP(+ADD/LDR) data refs, BL targets and immediates in a function.
Usage: python3 -I a64refs.py <Image> <text_base_hex> <func_va_hex> [max_insns]
"""
import struct, sys

def sx(v, bits): return v - (1 << bits) if v & (1 << (bits - 1)) else v

def main():
    img = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16)
    va = int(sys.argv[3], 16); maxn = int(sys.argv[4]) if len(sys.argv) > 4 else 400
    regs = {}
    for k in range(maxn):
        pc = va + 4 * k; off = pc - base
        ins = struct.unpack_from('<I', img, off)[0]
        txt = ''
        if ins & 0x9F000000 == 0x90000000:  # ADRP
            rd = ins & 31; immlo = (ins >> 29) & 3; immhi = (ins >> 5) & 0x7FFFF
            imm = sx((immhi << 2) | immlo, 21) << 12
            regs[rd] = (pc & ~0xFFF) + imm; txt = 'adrp x%d, %#x' % (rd, regs[rd])
        elif ins & 0x7F800000 == 0x11000000:  # ADD imm (32/64)
            rd = ins & 31; rn = (ins >> 5) & 31; imm = (ins >> 10) & 0xFFF
            if (ins >> 22) & 1: imm <<= 12
            if rn in regs:
                regs[rd] = regs[rn] + imm; txt = 'add x%d, x%d, #%#x   => %#x' % (rd, rn, imm, regs[rd])
            else: txt = 'add x%d, x%d, #%#x' % (rd, rn, imm)
        elif ins & 0x3B000000 == 0x39000000:  # LDR/STR unsigned imm
            size = ins >> 30; opc = (ins >> 22) & 3; rt = ins & 31; rn = (ins >> 5) & 31
            imm = ((ins >> 10) & 0xFFF) << size
            kind = ['str', 'ldr', 'ldrs', 'ldrs'][opc] + ['b', 'h', '', ''][size] + ('' if size < 2 else (' w' if size == 2 else ' x'))
            tgt = (' => [%#x]' % (regs[rn] + imm)) if rn in regs else ''
            txt = '%s r%d, [x%d, #%#x]%s' % (kind, rt, rn, imm, tgt)
        elif ins & 0xFC000000 == 0x94000000:
            txt = 'bl %#x' % (pc + (sx(ins & 0x3FFFFFF, 26) << 2))
        elif ins & 0xFC000000 == 0x14000000:
            txt = 'b %#x' % (pc + (sx(ins & 0x3FFFFFF, 26) << 2))
        elif ins & 0xFF000010 == 0x54000000:
            txt = 'b.%d %#x' % (ins & 15, pc + (sx((ins >> 5) & 0x7FFFF, 19) << 2))
        elif ins & 0x7F000000 == 0x34000000 or ins & 0x7F000000 == 0x35000000:
            txt = 'cb%sz r%d, %#x' % ('n' if ins & 0x01000000 else '', ins & 31, pc + (sx((ins >> 5) & 0x7FFFF, 19) << 2))
        elif ins & 0x7F800000 == 0x52800000:
            txt = 'movz r%d, #%#x lsl %d' % (ins & 31, (ins >> 5) & 0xFFFF, ((ins >> 21) & 3) * 16)
        elif ins & 0x7F800000 == 0x71000000 and (ins & 31) == 31:
            txt = 'cmp r%d, #%#x' % ((ins >> 5) & 31, (ins >> 10) & 0xFFF)
        elif ins & 0x3B200C00 == 0x38200800:
            txt = 'ldr/str (reg idx) size=%d rt=%d rn=%d rm=%d%s' % (ins >> 30, ins & 31, (ins >> 5) & 31, (ins >> 16) & 31, (' base=%#x' % regs[(ins >> 5) & 31]) if (ins >> 5) & 31 in regs else '')
        elif ins == 0xD65F03C0:
            print('%#x: ret' % pc); break
        if txt: print('%#x: %s' % (pc, txt))

if __name__ == '__main__':
    main()
