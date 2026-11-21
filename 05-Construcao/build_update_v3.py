"""Build an RKFW update image from an original one, replacing RKAF entries with files of ANY size.

build_update.py only allows same-size replacements. This one re-lays out the RKAF:
  RKFW  : header (0x66) | loader | RKAF | (nothing else) | 32-byte ASCII MD5 trailer
          @0x21 u32 RKAF offset (unchanged), @0x25 u32 RKAF length = RKAF len + 4 (includes CRC)
  RKAF  : 0x800 header: @4 u32 length (end of last entry, aligned to ALIGN); @0x88 u32 count;
          entries @0x8C, 112 bytes: name[32] file[60] u32 nand_size, u32 pos, u32 nand_addr,
          u32 padded (2048-byte sectors), u32 size
          data: entries laid out in original position order, first at 0x800, each aligned to ALIGN (0x800)
          then u32 rkcrc(RKAF[0:length]) little-endian right after RKAF.
  rkcrc : poly 0x04c10db7 (NOT the standard 0x04c11db7, so zlib cannot be used), init 0, MSB-first, no
          final xor. Bytewise table version run on 32 MiB pieces in parallel (fork pool) and combined with
          crc(A||B) = crc(A)*x^(8|B|) mod P ^ crc(B); self-tested and validated against the CRC stored in the
          original image (aborts otherwise).
Header bytes, loader, package-file, parameter and all non-replaced entries are copied verbatim; nand_size /
nand_addr (from parameter) are kept. Aborts if a replacement does not fit its partition (nand_size sectors), if the
original layout is not reproduced by the layout rule, or if the original MD5 trailer / CRC do not verify.

Usage: python3 -I build_update_v3.py <orig.img> <out.img> name=file [name=file ...] [--force]
"""
import struct, sys, os, hashlib

ALIGN = 0x800
SECT = 2048
CH = 1 << 24

# ---- rkcrc (reference, bytewise) and fast version
T = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04c10db7) if c & 0x80000000 else (c << 1)
    T.append(c & 0xFFFFFFFF)


def rkcrc_ref(buf, crc=0):
    for b in buf:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ T[(crc >> 24) ^ b]
    return crc


POLY = 0x104c10db7  # x^32 + 0x04c10db7


def clmulmod(a, b):
    """a*b mod POLY over GF(2) (a, b < 2^32)."""
    r = 0
    while b:
        if b & 1:
            r ^= a
        b >>= 1
        a <<= 1
        if a & 0x100000000:
            a ^= POLY
    return r


def xpow8n(n):
    """x^(8n) mod POLY."""
    r, base, e = 1, 1 << 8, n
    while e:
        if e & 1:
            r = clmulmod(r, base)
        base = clmulmod(base, base)
        e >>= 1
    return r


def combine(crc_a, crc_b, len_b):
    """rkcrc(A||B) from rkcrc(A), rkcrc(B), len(B): init 0 / no xorout -> linear."""
    return clmulmod(crc_a, xpow8n(len_b)) ^ crc_b


def _crc_job(job):
    path, off, n = job
    with open(path, 'rb') as f:
        f.seek(off); crc = 0; left = n
        while left:
            b = f.read(min(left, CH)); left -= len(b)
            crc = rkcrc_ref(b, crc)
    return crc, n


def rkcrc_file(path, off, length, piece=32 << 20):
    """rkcrc of path[off:off+length], pieces computed in parallel (fork) and combined."""
    import multiprocessing as mp
    jobs = [(path, off + i, min(piece, length - i)) for i in range(0, length, piece)]
    crc = 0
    with mp.get_context('fork').Pool(os.cpu_count() or 2) as pool:
        for k, (c, n) in enumerate(pool.imap(_crc_job, jobs)):
            crc = combine(crc, c, n)
            if k % 16 == 15:
                print('  crc %d/%d MB' % ((k + 1) * piece >> 20, length >> 20), flush=True)
    return crc


def selftest():
    import random, tempfile
    rnd = random.Random(1)
    a = bytes(rnd.getrandbits(8) for _ in range(5000)); b = bytes(rnd.getrandbits(8) for _ in range(3333))
    assert rkcrc_ref(b'\x01') == 0x04c10db7
    assert combine(rkcrc_ref(a), rkcrc_ref(b), len(b)) == rkcrc_ref(a + b)
    assert combine(rkcrc_ref(a), 0, 0) == rkcrc_ref(a)
    with tempfile.NamedTemporaryFile() as t:
        t.write(a + b); t.flush()
        assert rkcrc_file(t.name, 7, len(a + b) - 7, piece=1000) == rkcrc_ref((a + b)[7:])


# ---- parsing
def parse(path):
    f = open(path, 'rb')
    head = f.read(0x66)
    assert head[:4] == b'RKFW', 'not RKFW'
    hlen = struct.unpack_from('<H', head, 4)[0]
    assert hlen == 0x66
    lo, ll, base, blen = struct.unpack_from('<IIII', head, 0x19)
    f.seek(base); hdr = f.read(ALIGN)
    assert hdr[:4] == b'RKAF'
    rlen, = struct.unpack_from('<I', hdr, 4)
    n, = struct.unpack_from('<I', hdr, 0x88)
    ents = []
    for k in range(n):
        o = 0x8C + k * 112
        nand_size, pos, nand_addr, padded, size = struct.unpack_from('<5I', hdr, o + 92)
        ents.append(dict(idx=k, name=hdr[o:o + 32].split(b'\0')[0].decode(),
                         file=hdr[o + 32:o + 92].split(b'\0')[0].decode(),
                         nand_size=nand_size, pos=pos, nand_addr=nand_addr, padded=padded, size=size))
    tot = os.path.getsize(path)
    return dict(f=f, head=head, loader=(lo, ll), base=base, blen=blen, hdr=hdr, rlen=rlen, ents=ents, total=tot)


def al(x):
    return (x + ALIGN - 1) // ALIGN * ALIGN


def layout(ents, sizes):
    """Assign positions in original position order; zero-size entries (e.g. backup/RESERVED) keep pos 0."""
    pos = ALIGN; out = {}
    for e in sorted([e for e in ents if sizes[e['name']]], key=lambda e: e['pos']):
        out[e['name']] = pos
        pos = al(pos + sizes[e['name']])
    return out, pos


def copy(src, off, n, dst, sinks):
    src.seek(off); left = n
    while left:
        c = src.read(min(left, CH))
        assert c, 'short read'
        left -= len(c); dst.write(c)
        for s in sinks: s.update(c)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    orig, out = args[0], args[1]
    repl = dict(a.split('=', 1) for a in args[2:])
    selftest()
    O = parse(orig); f = O['f']; base = O['base']
    ents = O['ents']; byname = {e['name']: e for e in ents}
    for n in repl:
        assert n in byname, 'unknown entry %s' % n

    # ---- validate the original: layout rule, RKFW lengths, CRC, MD5 trailer
    osz = {e['name']: e['size'] for e in ents}
    lay, end = layout(ents, osz)
    for e in ents:
        if e['size']:
            assert lay[e['name']] == e['pos'], ('layout rule mismatch', e)
            assert e['padded'] == (e['size'] + SECT - 1) // SECT, ('padded rule', e)
    assert end == O['rlen'], (end, O['rlen'])
    assert O['blen'] == O['rlen'] + 4 and O['total'] == base + O['rlen'] + 4 + 32
    assert O['loader'] == (0x66, base - 0x66), O['loader']
    print('original: RKAF @%#x len=%d, %d entries, layout rule OK' % (base, O['rlen'], len(ents)), flush=True)
    md5 = hashlib.md5(); f.seek(0); left = O['total'] - 32
    while left:
        c = f.read(min(left, CH)); left -= len(c); md5.update(c)
    trailer = f.read(32)
    assert md5.hexdigest().encode() == trailer, 'MD5 trailer mismatch on original'
    f.seek(base + O['rlen']); stored = struct.unpack('<I', f.read(4))[0]
    oc = rkcrc_file(orig, base, O['rlen'])
    assert oc == stored, 'CRC mismatch on original - aborting (%08x != %08x)' % (oc, stored)
    print('original: CRC %08x OK, MD5 trailer %s OK' % (oc, trailer.decode()), flush=True)
    # gaps in the original are zero (so writing zero padding matches the vendor tool)
    for e in ents:
        if e['size']:
            g = al(e['pos'] + e['size']) - (e['pos'] + e['size'])
            f.seek(base + e['pos'] + e['size']); assert f.read(g) == b'\0' * g, ('nonzero gap', e['name'])

    # ---- new layout
    nsz = dict(osz)
    for n, p in repl.items():
        nsz[n] = os.path.getsize(p)
        e = byname[n]
        assert nsz[n] <= e['nand_size'] * 512, '%s: %d bytes > partition %#x sectors' % (n, nsz[n], e['nand_size'])
        print('replace %-9s %10d -> %10d bytes  (partition %#x sectors = %d bytes, %.1f%%)' % (
            n, osz[n], nsz[n], e['nand_size'], e['nand_size'] * 512, 100.0 * nsz[n] / (e['nand_size'] * 512)))
    lay, rlen = layout(ents, nsz)
    assert rlen < 1 << 32 and rlen + 4 < 1 << 32
    hdr = bytearray(O['hdr'])
    struct.pack_into('<I', hdr, 4, rlen)
    for e in ents:
        o = 0x8C + e['idx'] * 112
        if nsz[e['name']]:
            struct.pack_into('<5I', hdr, o + 92, e['nand_size'], lay[e['name']], e['nand_addr'],
                             (nsz[e['name']] + SECT - 1) // SECT, nsz[e['name']])
    head = bytearray(O['head'])
    struct.pack_into('<I', head, 0x25, rlen + 4)

    if os.path.exists(out) and not force:
        sys.exit('exists: %s (use --force)' % out)
    md5 = hashlib.md5()
    with open(out, 'wb') as g:
        g.write(head); md5.update(head)
        copy(f, 0x66, base - 0x66, g, [md5])
        g.write(hdr); md5.update(hdr)
        pos = ALIGN
        for e in sorted([e for e in ents if nsz[e['name']]], key=lambda e: lay[e['name']]):
            assert pos == lay[e['name']]
            n = e['name']
            if n in repl:
                with open(repl[n], 'rb') as s:
                    copy(s, 0, nsz[n], g, [md5])
            else:
                copy(f, base + e['pos'], e['size'], g, [md5])
            pad = al(pos + nsz[n]) - (pos + nsz[n])
            z = b'\0' * pad; g.write(z); md5.update(z)
            pos += nsz[n] + pad
            print('  %-14s pos=%#010x size=%10d%s' % (n, lay[n], nsz[n], '  (new)' if n in repl else ''), flush=True)
        assert pos == rlen
        g.flush()
        nc = rkcrc_file(out, base, rlen)  # CRC of the RKAF as written to disk
        c = struct.pack('<I', nc); g.write(c); md5.update(c)
        m = md5.hexdigest().encode(); g.write(m)
    assert os.path.getsize(out) == base + rlen + 4 + 32
    print('RKAF len=%d crc=%08x md5 trailer=%s' % (rlen, nc, m.decode()))
    print('CONCLUIDO')


if __name__ == '__main__':
    main()
