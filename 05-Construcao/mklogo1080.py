"""Build boot/recovery images with the 1920x1080 boot logo (version B) in the RSCE ('second').
Inputs (read-only): boot-hybrid-dtbfix.img, recovery-hybrid-dtbfix.img (DTB hash already fixed),
                    ../07-Logo/logo_v2_1080.bmp (standard 24-bit bottom-up BMP from gerar_logo.py)
Outputs: <name>-hybrid-logo1080.img    logo in the Rockchip "processed" layout used by the original HK1 logo:
                                       bfReserved1 = 8399 (BMP_PROCESSED_FLAG), height < 0, rows top-down.
                                       U-Boot then sets logo->ymirror = 0 (no VOP Y-mirror needed).
         <name>-hybrid-logo1080bu.img  fallback: the plain BMP (reserved 0, bottom-up) -> U-Boot sets ymirror = 1.
The RSCE grows (data/offsets rebuilt by rsce.build), so second_size, page padding, the header id and
(recovery only) the absolute recovery_dtbo_offset are updated. Kernel/ramdisk/recovery_dtbo/dtb untouched.
Uso: python3 -I mklogo1080.py [--force]
"""
import sys, struct, hashlib, os
B = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [B, B + '/autoflash']
import bootimg, rsce
L = B + '/../07-Logo/'
FORCE = '--force' in sys.argv
BMP_PROCESSED_FLAG = 8399  # Rockchip U-Boot: reserved == 8399 -> data already top-down, ymirror = 0


def bmp_info(b):
    _, bfsize, res1, res2, off, hs, w, h, planes, bpp, comp = struct.unpack_from('<2sIHHIIiiHHI', b, 0)
    return dict(bfsize=bfsize, res1=res1, off=off, hs=hs, w=w, h=h, bpp=bpp, comp=comp)


def bmp_rows(b):
    """Decode uncompressed 24-bit BMP -> (w, h, list of top-down rows)."""
    i = bmp_info(b)
    assert i['bpp'] == 24 and i['comp'] == 0, i
    w, h, off = i['w'], i['h'], i['off']
    stride = (w * 3 + 3) & ~3
    rows = [b[off + y * stride: off + y * stride + w * 3] for y in range(abs(h))]
    if h > 0:
        rows.reverse()  # bottom-up -> top-down
    return w, abs(h), rows


def rk_processed(std):
    """Same pixels, HK1-style header: 8399 flag, negative height, top-down rows (1920*3 needs no padding)."""
    w, h, rows = bmp_rows(std)
    assert (w * 3) % 4 == 0
    pix = b''.join(rows)
    hdr = struct.pack('<2sIHHI', b'BM', 54 + len(pix), BMP_PROCESSED_FLAG, 0, 54)
    dib = struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 24, 0, 0, 0, 0, 0, 0)  # zeros like the HK1 original
    out = hdr + dib + pix
    assert bmp_rows(out)[2] == rows
    return out


def idof(k, r, s, ro, dt, hv):
    # Same scheme as mklogo.py / hybrid.py (only the SIZES of recovery_dtbo/dtb are hashed).
    sh = hashlib.sha1()
    for b in (k, r, s):
        sh.update(b); sh.update(struct.pack('<I', len(b)))
    if hv >= 1: sh.update(struct.pack('<I', len(ro)))
    if hv >= 2: sh.update(struct.pack('<I', len(dt)))
    return sh.digest().ljust(32, b'\0')


std = open(L + 'logo_v2_1080.bmp', 'rb').read()
si = bmp_info(std)
assert (si['w'], si['h'], si['bpp'], si['comp'], si['hs'], si['off'], si['res1']) == (1920, 1080, 24, 0, 40, 54, 0), si
assert si['bfsize'] == len(std) == 54 + 1920 * 1080 * 3
PIX = bmp_rows(std)[2]
proc = rk_processed(std)

for name, lim in (('boot', 64 << 20), ('recovery', 96 << 20)):
    src = B + '/%s-hybrid-dtbfix.img' % name
    d, k, r, s, ro, pg, hv = bootimg.rd(src); dt = bootimg.rd.dtb
    pad = lambda b: b + b'\0' * ((-len(b)) % pg)
    assert idof(k, r, s, ro, dt, hv) == d[576:608], 'input id not reproduced: ' + src
    assert d[:pg] + pad(k) + pad(r) + pad(s) + pad(ro) + pad(dt) == d, 'unexpected layout'
    if hv >= 1 and ro:
        assert struct.unpack_from('<Q', d, 1636)[0] == pg + len(pad(k)) + len(pad(r)) + len(pad(s))
    R0 = rsce.parse(s)
    assert rsce.build(R0) == s
    for suffix, logo in (('logo1080', proc), ('logo1080bu', std)):
        out = B + '/%s-hybrid-%s.img' % (name, suffix)
        R = rsce.parse(s)
        rsce.replace(R, 'logo.bmp', logo)
        rsce.replace(R, 'logo_kernel.bmp', logo)
        ns = rsce.build(R)
        h = bytearray(d[:pg])
        struct.pack_into('<I', h, 24, len(ns))                       # second_size
        if hv >= 1 and ro:                                            # absolute offset moves with 'second'
            struct.pack_into('<Q', h, 1636, pg + len(pad(k)) + len(pad(r)) + len(pad(ns)))
        h[576:608] = idof(k, r, ns, ro, dt, hv)
        img = bytes(h) + pad(k) + pad(r) + pad(ns) + pad(ro) + pad(dt)
        assert len(img) <= lim, (out, len(img))
        if os.path.exists(out) and not FORCE: sys.exit('exists: %s (use --force)' % out)
        open(out, 'wb').write(img)

        # ---- verify from disk
        d2, k2, r2, s2, ro2, pg2, hv2 = bootimg.rd(out); dt2 = bootimg.rd.dtb
        assert (k2, r2, ro2, dt2, pg2, hv2) == (k, r, ro, dt, pg, hv), 'kernel/ramdisk/dtbo/dtb changed'
        assert idof(k2, r2, s2, ro2, dt2, hv2) == d2[576:608]
        hd = [i for i in range(pg) if d[i] != d2[i]]
        A, N = R0['entries'], rsce.parse(s2)['entries']
        assert [a['name'] for a in A] == [n['name'] for n in N]
        for a, n in zip(A, N):
            assert n['hash'][:20] == hashlib.sha1(n['data']).digest() and n['hash_size'] == 20, n['name']
            if n['name'] in ('logo.bmp', 'logo_kernel.bmp'):
                assert n['data'] == logo and bmp_rows(n['data'])[2] == PIX
                assert n['data'][:2] == b'BM'
            else:
                assert n['data'] == a['data'] and n['hash'] == a['hash'], n['name']
        assert (N[-1]['offset'] * 512 + len(rsce._pad(N[-1]['data']))) == len(s2)
        li = bmp_info([n for n in N if n['name'] == 'logo.bmp'][0]['data'])
        print('==', os.path.basename(out))
        print('   size %d (%.1f%% of %d MiB)  md5 %s' % (len(img), 100 * len(img) / lim, lim >> 20, hashlib.md5(img).hexdigest()))
        print('   second %d -> %d | header bytes changed at %s' % (len(s), len(s2), sorted(set(i // 4 * 4 for i in hd))))
        print('   logo: %dx%d bpp %d reserved %d -> U-Boot ymirror=%d | entries:' % (li['w'], li['h'], li['bpp'], li['res1'], li['res1'] != BMP_PROCESSED_FLAG),
              ', '.join('%s@%d' % (n['name'], n['offset']) for n in N))
