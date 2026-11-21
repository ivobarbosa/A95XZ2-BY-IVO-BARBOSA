"""Unpack a Rockchip RKFW update image (RKFW -> loader + RKAF -> partitions).
Usage: python3 -I unrkfw.py <update.img> <out_dir> [--list] [--only name1,name2]
"""
import struct, sys, os

def cstr(b): return b.split(b'\0')[0].decode('latin-1')

def main():
    path, out = sys.argv[1], sys.argv[2]
    listonly = '--list' in sys.argv
    only = None
    if '--only' in sys.argv: only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    fh = open(path, 'rb'); head = fh.read(0x66)
    base = 0
    if head[:4] == b'RKFW':
        hlen = struct.unpack_from('<H', head, 4)[0]
        ver = struct.unpack_from('<I', head, 6)[0]
        y, mo, d, h, mi, s = struct.unpack_from('<HBBBBB', head, 0x0E)
        chip = struct.unpack_from('<I', head, 0x15)[0]
        lo, ll, io, il = struct.unpack_from('<IIII', head, 0x19)
        print('RKFW hdr=%d version=%d.%d.%d date=%04d-%02d-%02d %02d:%02d chip=0x%x' % (
            hlen, ver >> 24, (ver >> 16) & 0xff, ver & 0xffff, y, mo, d, h, mi, chip))
        print('  loader @0x%x len=%d   RKAF @0x%x len=%d' % (lo, ll, io, il))
        if not listonly and (only is None or 'loader' in only):
            os.makedirs(out, exist_ok=True)
            fh.seek(lo); open(os.path.join(out, 'loader_from_rkfw.bin'), 'wb').write(fh.read(ll))
        base = io
    fh.seek(base); hdr = fh.read(0x800)
    assert hdr[:4] == b'RKAF', 'RKAF not found at 0x%x' % base
    length = struct.unpack_from('<I', hdr, 4)[0]
    model = cstr(hdr[8:8 + 0x22]); fid = cstr(hdr[0x2A:0x2A + 0x1E]); manu = cstr(hdr[0x48:0x48 + 0x38])
    version, nparts = struct.unpack_from('<II', hdr, 0x84)
    print('RKAF len=%d model=%r id=%r manufacturer=%r parts=%d' % (length, model, fid, manu, nparts))
    off = 0x8C
    parts = []
    for k in range(nparts):
        name = cstr(hdr[off:off + 32]); fname = cstr(hdr[off + 32:off + 92])
        nand_size, pos, nand_addr, padded, size = struct.unpack_from('<IIIII', hdr, off + 92)
        parts.append((name, fname, nand_size, pos, nand_addr, padded, size)); off += 112
        print('  %-14s %-28s pos=0x%08x size=%10d flash_sector=0x%08x' % (name, fname, pos, size, nand_addr))
    if listonly: return
    os.makedirs(out, exist_ok=True)
    for name, fname, nand_size, pos, nand_addr, padded, size in parts:
        if only and name not in only: continue
        if size == 0 or fname in ('', 'RESERVED', 'SELF'): continue
        dst = os.path.join(out, os.path.basename(fname.replace('\\', '/')) or name)
        fh.seek(base + pos); left = size
        with open(dst, 'wb') as o:
            while left:
                c = fh.read(min(left, 1 << 22)); o.write(c); left -= len(c)
        print('->', dst, size, flush=True)

if __name__ == '__main__':
    main()
