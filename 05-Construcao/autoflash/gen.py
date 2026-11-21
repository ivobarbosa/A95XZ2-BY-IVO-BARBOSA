"""Gera plano de gravação (autoflash) a partir de update-hybrid.img: GPT, partições raw, mapa do super sparse.
Uso: python3 -I gen.py <update.img> <disk_sectors> <out_dir>"""
import struct, sys, os, hashlib, zlib, uuid, re
img, DISK, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]; os.makedirs(out, exist_ok=True)
f = open(img, 'rb'); h = f.read(0x66); base = struct.unpack_from('<I', h, 0x21)[0]
f.seek(base); hdr = f.read(0x800); n = struct.unpack_from('<I', hdr, 0x88)[0]
ents = {}
for i in range(n):
    e = hdr[0x8C + i*112: 0x8C + (i+1)*112]
    name = e[:32].split(b'\0')[0].decode(); _, pos, nand, _, size = struct.unpack_from('<IIIII', e, 92)
    ents[name] = (base + pos, size)
o, s = ents['parameter']; f.seek(o); par = f.read(s)[8:-4].decode()
parts = []
for m in re.finditer(r'(-|0x[0-9a-f]+)@(0x[0-9a-f]+)\(([\w]+)(:grow)?\)', par):
    st = int(m.group(2), 16); sz = (DISK - 34 - st) if m.group(1) == '-' else int(m.group(1), 16)
    parts.append((m.group(3), st, sz))
P = {p[0]: (p[1], p[2]) for p in parts}
# ---- GPT
def guid(name, salt): return uuid.UUID(bytes=hashlib.md5((salt + name).encode()).digest(), version=4)
ent = bytearray(128 * 128)
for i, (nm, st, sz) in enumerate(parts):
    e = guid(nm, 'type').bytes_le + guid(nm, 'uniq-a95xz2').bytes_le + struct.pack('<QQQ', st, st + sz - 1, 0) + nm.encode('utf-16le').ljust(72, b'\0')
    ent[i*128:(i+1)*128] = e
ecrc = zlib.crc32(ent) & 0xffffffff
dguid = guid('disk', 'a95xz2').bytes_le
def ghdr(cur, alt, elba):
    x = struct.pack('<8sIIIIQQQQ16sQIII', b'EFI PART', 0x10000, 92, 0, 0, cur, alt, 34, DISK - 34, dguid, elba, 128, 128, ecrc)
    x = x[:16] + struct.pack('<I', zlib.crc32(x) & 0xffffffff) + x[20:]
    return x.ljust(512, b'\0')
mbr = bytearray(512); mbr[446:462] = struct.pack('<BBBBBBBBII', 0, 0, 2, 0, 0xEE, 0xff, 0xff, 0xff, 1, min(DISK - 1, 0xffffffff)); mbr[510:] = b'\x55\xaa'
open(os.path.join(out, 'gpt_primary.bin'), 'wb').write(bytes(mbr) + ghdr(1, DISK - 1, 2) + bytes(ent))      # sectores 0..33
open(os.path.join(out, 'gpt_backup.bin'), 'wb').write(bytes(ent) + ghdr(DISK - 1, 1, DISK - 33))            # sectores DISK-33..DISK-1
# ---- plano: W nome src_off len dst_sector md5 | Z nome dst_sector n_sectores | S (super)
L = []
for nm in ['uboot', 'trust', 'misc', 'dtbo', 'vbmeta', 'boot', 'recovery', 'baseparameter']:
    so, sz = ents[nm]; st, psz = P[nm]; assert sz <= psz * 512, nm
    f.seek(so); md = hashlib.md5(f.read(sz)).hexdigest()
    assert so % 4 == 0 and st % 8 == 0
    L.append('W %s %d %d %d %s %d' % (nm, so // 4, sz, st // 8, md, st))
for nm, nsec in [('security', None), ('frp', None), ('logo', None), ('metadata', 8192), ('cache', 8192), ('userdata', 8192), ('dtb', None)]:
    st, psz = P[nm]; L.append('Z %s %d %d' % (nm, st // 8, (nsec or psz) // 8))
# super sparse
so, sz = ents['super']; f.seek(so); sh = f.read(28)
magic, maj, mi, fhs, chs, bsz, tblk, tch, _ = struct.unpack('<IHHHHIIII', sh); assert magic == 0xED26FF3A
st, psz = P['super']; assert tblk * bsz <= psz * 512
off = so + fhs; blk = 0; spb = bsz // 512; FILLS = {}; S = []; allmd = hashlib.md5(); nraw = 0
for c in range(tch):
    f.seek(off); ct, _, cs, tot = struct.unpack('<HHII', f.read(12)); dat = off + chs
    if ct == 0xCAC1:
        assert dat % 4 == 0; S.append('R %d %d %d %d' % (dat // 4, cs * bsz, (st + blk * spb) // 8, st + blk * spb)); nraw += cs
        f.seek(dat); left = cs * bsz
        while left: b = f.read(min(left, 1 << 22)); allmd.update(b); left -= len(b)
    elif ct == 0xCAC2:
        f.seek(dat); fv = f.read(4)
        if fv == b'\0\0\0\0': S.append('Z super %d %d' % ((st + blk * spb) // 8, cs * spb // 8))
        else:
            fn = 'fill_%s.bin' % fv.hex(); FILLS[fn] = max(FILLS.get(fn, 0), cs)
            S.append('F %s %d %d %d' % (fn, (st + blk * spb) // 8, cs * bsz, st + blk * spb))
            fb = fv * (bsz // 4); [allmd.update(fb) for _ in range(cs)]
    elif ct == 0xCAC3: pass
    else: assert ct == 0xCAC4
    blk += cs; off += tot
for fn, cs in FILLS.items():
    open(os.path.join(out, fn), 'wb').write(bytes.fromhex(fn[5:13]) * (cs * bsz // 4))
L.append('S %d %s' % (len(S), allmd.hexdigest()))
open(os.path.join(out, 'plano.txt'), 'w').write('\n'.join(L + S) + '\n')
print('parts', len(parts), 'super chunks raw', sum(1 for x in S if x[0] == 'R'), 'zero', sum(1 for x in S if x[0] == 'Z'), 'raw MB', nraw * bsz >> 20)
print('\n'.join(L))
