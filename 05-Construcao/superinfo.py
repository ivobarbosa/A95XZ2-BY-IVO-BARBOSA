"""Unsparse an Android sparse image and dump LP (dynamic partition) metadata.
Usage: python3 -I superinfo.py <super.img(sparse)> <super.raw> [--extract name1,name2 outdir]
"""
import struct, sys, os

def unsparse(src, dst):
    f = open(src, 'rb'); h = f.read(28)
    magic, maj, mnr, fhs, chs, blk, tblk, tchunk, crc = struct.unpack('<IHHHHIIII', h)
    assert magic == 0xED26FF3A
    f.seek(fhs)
    with open(dst, 'wb') as o:
        for _ in range(tchunk):
            ct, _r, csz, tsz = struct.unpack('<HHII', f.read(chs))
            data_len = tsz - chs; n = csz * blk
            if ct == 0xCAC1:
                left = data_len
                while left: c = f.read(min(left, 1 << 22)); o.write(c); left -= len(c)
            elif ct == 0xCAC2:
                fill = f.read(4); chunk = fill * (1 << 20)
                left = n
                while left: w = min(left, len(chunk)); o.write(chunk[:w]); left -= w
            elif ct == 0xCAC3: o.seek(n, 1)
            elif ct == 0xCAC4: f.read(4)
            else: raise ValueError(hex(ct))
        o.truncate(tblk * blk)
    print('raw size', tblk * blk)

def lp(raw):
    f = open(raw, 'rb'); f.seek(4096)
    g = f.read(4096)
    magic, mj, mn, sz, csum, msmax, slots, lbs = struct.unpack_from('<IHHI32sIII', g, 0)
    assert magic == 0x616c4467, hex(magic)
    f.seek(4096 + 4096 * 2)  # primary metadata slot 0 after geometry + backup geometry
    hdr = f.read(256)
    m, mj, mn, hsz = struct.unpack_from('<IHHI', hdr, 0)
    assert m == 0x414C5030, hex(m)
    tables_size = struct.unpack_from('<I', hdr, 44)[0]
    def desc(off): return struct.unpack_from('<III', hdr, off)
    p_off, p_n, p_sz = desc(80); e_off, e_n, e_sz = desc(92); g_off, g_n, g_sz = desc(104); b_off, b_n, b_sz = desc(116)
    f.seek(4096 + 4096 * 2 + hsz); t = f.read(tables_size)
    parts = []
    for k in range(p_n):
        o = p_off + k * p_sz
        name = t[o:o + 36].split(b'\0')[0].decode(); attrs, first_ext, n_ext, grp = struct.unpack_from('<IIII', t, o + 36)
        exts = []
        for j in range(n_ext):
            eo = e_off + (first_ext + j) * e_sz
            nsec, ttype, tdata, tsrc = struct.unpack_from('<QIQI', t, eo)
            exts.append((nsec, ttype, tdata))
        parts.append((name, attrs, exts))
    return parts

def main():
    src, raw = sys.argv[1], sys.argv[2]
    if not os.path.exists(raw): unsparse(src, raw)
    parts = lp(raw)
    for name, attrs, exts in parts:
        tot = sum(e[0] for e in exts) * 512
        print('%-12s attrs=%d size=%10d extents=%s' % (name, attrs, tot, [(hex(e[2] * 512), e[0] * 512) for e in exts]))
    if '--extract' in sys.argv:
        want = sys.argv[sys.argv.index('--extract') + 1].split(','); outd = sys.argv[sys.argv.index('--extract') + 2]
        os.makedirs(outd, exist_ok=True); f = open(raw, 'rb')
        for name, attrs, exts in parts:
            if name not in want: continue
            with open(os.path.join(outd, name + '.img'), 'wb') as o:
                for nsec, tt, td in exts:
                    f.seek(td * 512); left = nsec * 512
                    while left: c = f.read(min(left, 1 << 22)); o.write(c); left -= len(c)
            print('->', name)

if __name__ == '__main__':
    main()
