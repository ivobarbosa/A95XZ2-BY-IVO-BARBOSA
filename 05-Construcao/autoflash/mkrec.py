"""Gera recovery-autoflash.img: recovery original da box + /sbin/autoflash.sh a correr em vez do recovery.
Uso: python3 -I mkrec.py <recovery_orig.img> <autoflash.sh> <out.img>"""
import sys, struct, gzip, hashlib
sys.path.insert(0, '.'); import bootimg
src, scr, out = sys.argv[1:4]
d, k, r, s, ro, pg, hv = bootimg.rd(src)
e = bootimg.cpio_read(gzip.decompress(r))
names = [x[0] for x in e]
SH = '/system/bin/sh' if 'system/bin/sh' in names else '/sbin/sh'; SCR = '/autoflash.sh' if SH == '/system/bin/sh' else '/sbin/autoflash.sh'
for x in e:
    if x[0] == 'init.rc':
        t = x[2].decode(); old = [l for l in t.splitlines() if l.startswith('service recovery ')]; assert len(old) == 1
        x[2] = t.replace(old[0] + '\n', 'service recovery %s %s\n' % (SH, SCR)).encode()
tmpl = [x for x in e if x[0] == SH[1:]][0]
e.append([SCR[1:], list(tmpl[1]), open(scr, 'rb').read().replace(b'\r\n', b'\n')])
nr = gzip.compress(bootimg.cpio_write(e), 9)
def pad(b): return b + b'\0' * ((-len(b)) % pg)
h = bytearray(d[:pg]); struct.pack_into('<I', h, 16, len(nr))
sh = hashlib.sha1()
for b in (k, nr, s): sh.update(b); sh.update(struct.pack('<I', len(b)))
if hv >= 1: sh.update(ro); sh.update(struct.pack('<I', len(ro)))
if hv >= 2: sh.update(bootimg.rd.dtb); sh.update(struct.pack('<I', len(bootimg.rd.dtb)))
h[576:608] = sh.digest().ljust(32, b'\0')
img = bytes(h) + pad(k) + pad(nr) + pad(s) + (pad(ro) if hv >= 1 else b'') + (pad(bootimg.rd.dtb) if hv >= 2 else b'')
assert len(img) <= 96 << 20  # partição recovery: 64 MB no A9, 96 MB no A10
open(out, 'wb').write(img)
d2, k2, r2, s2, ro2, _, _ = bootimg.rd(out); assert k2 == k and s2 == s and r2 == nr
print('ok', len(img), hashlib.md5(img).hexdigest())
