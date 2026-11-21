"""Build update-hybrid.img: original RKFW with boot/recovery/super replaced (same sizes),
RKAF CRC (Rockchip rkcrc, poly 0x04c10db7, init 0, MSB-first) and MD5 trailer recomputed.
Aborts unless the CRC algorithm reproduces the original stored CRC.
Usage: python3 -I build_update.py <orig.img> <out.img> <boot> <recovery> <super>
"""
import struct, sys, os, shutil, hashlib, time

T = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04c10db7) if c & 0x80000000 else (c << 1)
    T.append(c & 0xFFFFFFFF)

def rkcrc(f, off, length):
    f.seek(off); crc = 0; left = length; t0 = time.time(); done = 0
    tab = T
    while left:
        buf = f.read(min(left, 1 << 22)); left -= len(buf); done += len(buf)
        for b in buf:
            crc = ((crc << 8) & 0xFFFFFFFF) ^ tab[(crc >> 24) ^ b]
        if done % (256 << 20) < (1 << 22):
            print('  crc %d MB (%.0fs)' % (done >> 20, time.time() - t0), flush=True)
    return crc

def md5_trailer(f, size):
    h = hashlib.md5(); f.seek(0); left = size - 32
    while left:
        c = f.read(min(left, 1 << 24)); h.update(c); left -= len(c)
    return h.hexdigest().encode()

def main():
    orig, out, boot, rec, sup = sys.argv[1:6]
    f = open(orig, 'rb'); head = f.read(0x66)
    assert head[:4] == b'RKFW'
    base = struct.unpack_from('<I', head, 0x21)[0]
    f.seek(base); hdr = f.read(0x800); assert hdr[:4] == b'RKAF'
    rlen = struct.unpack_from('<I', hdr, 4)[0]
    nparts = struct.unpack_from('<I', hdr, 0x88)[0]
    parts = {}
    for k in range(nparts):
        o = 0x8C + k * 112
        name = hdr[o:o + 32].split(b'\0')[0].decode()
        _ns, pos, _na, _pad, size = struct.unpack_from('<IIIII', hdr, o + 92)
        parts[name] = (pos, size)
    f.seek(base + rlen); stored = struct.unpack('<I', f.read(4))[0]
    print('RKAF @%#x len=%d stored crc=%08x' % (base, rlen, stored), flush=True)
    calc = rkcrc(f, base, rlen)
    print('calculated crc=%08x' % calc, flush=True)
    assert calc == stored, 'CRC algorithm mismatch - aborting'
    f.close()
    shutil.copyfile(orig, out)
    g = open(out, 'r+b')
    for name, path in (('boot', boot), ('recovery', rec), ('super', sup)):
        pos, size = parts[name]
        assert os.path.getsize(path) == size, (name, os.path.getsize(path), size)
        g.seek(base + pos)
        with open(path, 'rb') as s:
            left = size
            while left:
                c = s.read(min(left, 1 << 24)); g.write(c); left -= len(c)
        print('replaced', name, size, flush=True)
    g.flush()
    newcrc = rkcrc(g, base, rlen)
    g.seek(base + rlen); g.write(struct.pack('<I', newcrc)); g.flush()
    total = os.path.getsize(out)
    m = md5_trailer(g, total)
    g.seek(total - 32); g.write(m); g.close()
    print('new crc=%08x md5=%s' % (newcrc, m.decode()), flush=True)
    print('CONCLUIDO')

if __name__ == '__main__':
    main()
