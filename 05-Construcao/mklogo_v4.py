"""v4: troca o logotipo (logo.bmp + logo_kernel.bmp no RSCE do 'second') de boot-v3.img e recovery-v3.img
pelo novo ../07-Logo/logo_v2_1080.bmp ("by Ivo Barbosa" em Segoe UI normal). O BMP tem exactamente o mesmo
tamanho, por isso o layout do RSCE e da imagem nao muda: so os bytes do logo, os SHA-1 das entradas e o id
do cabecalho. Kernel, ramdisk (Magisk), recovery_dtbo e dtb ficam iguais byte a byte (verificado).
Uso: python3 -I mklogo_v4.py   ->  boot-v4.img, recovery-v4.img
"""
import sys, os, struct, hashlib
B = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [B, B + '/autoflash']
import bootimg, rsce

BMP_PROCESSED_FLAG = 8399   # U-Boot Rockchip: dados ja top-down, sem espelho em Y (layout do logo HK1)


def bmp_rows(b):
    _, _, res1, _, off, hs, w, h, _, bpp, comp = struct.unpack_from('<2sIHHIIiiHHI', b, 0)
    assert bpp == 24 and comp == 0
    stride = (w * 3 + 3) & ~3
    rows = [b[off + y * stride: off + y * stride + w * 3] for y in range(abs(h))]
    if h > 0:
        rows.reverse()
    return w, abs(h), rows


def rk_processed(std):
    w, h, rows = bmp_rows(std)
    pix = b''.join(rows)
    hdr = struct.pack('<2sIHHI', b'BM', 54 + len(pix), BMP_PROCESSED_FLAG, 0, 54)
    dib = struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 24, 0, 0, 0, 0, 0, 0)
    return hdr + dib + pix


def idof(k, r, s, ro, dt, hv):
    sh = hashlib.sha1()
    for b in (k, r, s):
        sh.update(b); sh.update(struct.pack('<I', len(b)))
    if hv >= 1: sh.update(struct.pack('<I', len(ro)))
    if hv >= 2: sh.update(struct.pack('<I', len(dt)))
    return sh.digest().ljust(32, b'\0')


std = open(B + '/../07-Logo/logo_v2_1080.bmp', 'rb').read()
w, h, PIX = bmp_rows(std)
assert (w, h) == (1920, 1080)
proc = rk_processed(std)

for name in ('boot', 'recovery'):
    src, out = B + '/%s-v3.img' % name, B + '/%s-v4.img' % name
    d, k, r, s, ro, pg, hv = bootimg.rd(src); dt = bootimg.rd.dtb
    pad = lambda b: b + b'\0' * ((-len(b)) % pg)
    assert d[:pg] + pad(k) + pad(r) + pad(s) + pad(ro) + pad(dt) == d, 'layout inesperado: ' + src
    R = rsce.parse(s)
    assert rsce.build(R) == s
    old = {e['name']: e['data'] for e in R['entries']}
    assert old['logo.bmp'][6:8] == struct.pack('<H', BMP_PROCESSED_FLAG) and len(old['logo.bmp']) == len(proc)
    rsce.replace(R, 'logo.bmp', proc)
    rsce.replace(R, 'logo_kernel.bmp', proc)
    ns = rsce.build(R)
    assert len(ns) == len(s), 'RSCE mudou de tamanho'
    hdr = bytearray(d[:pg])
    hdr[576:608] = idof(k, r, ns, ro, dt, hv)
    img = bytes(hdr) + pad(k) + pad(r) + pad(ns) + pad(ro) + pad(dt)
    assert len(img) == len(d)
    open(out, 'wb').write(img)

    # verificacao a partir do disco
    d2, k2, r2, s2, ro2, pg2, hv2 = bootimg.rd(out); dt2 = bootimg.rd.dtb
    assert (k2, r2, ro2, dt2, pg2, hv2) == (k, r, ro, dt, pg, hv), 'kernel/ramdisk/dtbo/dtb mudaram'
    assert idof(k2, r2, s2, ro2, dt2, hv2) == d2[576:608]
    diff = [i for i in range(pg) if d[i] != d2[i]]
    assert all(576 <= i < 608 for i in diff), diff
    N = rsce.parse(s2)['entries']
    for e in N:
        assert e['hash'][:20] == hashlib.sha1(e['data']).digest(), e['name']
        if e['name'] in ('logo.bmp', 'logo_kernel.bmp'):
            assert e['data'] == proc and bmp_rows(e['data'])[2] == PIX
        else:
            assert e['data'] == old[e['name']], e['name']
    print('%-16s %d bytes  md5 %s  (so logo.bmp/logo_kernel.bmp + id mudaram)'
          % (os.path.basename(out), len(img), hashlib.md5(img).hexdigest()))
print('LOGO v4 OK')
