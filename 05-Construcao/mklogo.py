"""Build boot/recovery images with new boot logo and/or fixed rk-kernel.dtb hash in the RSCE.
Inputs (read-only): boot-hybrid.img, recovery-hybrid.img, ../07-Logo/logo_v2.bmp, logo_kernel_v2.bmp
Outputs: <name>-hybrid-logo.img   (new logos in original BMP layout + DTB hash fixed)
         <name>-hybrid-dtbfix.img (original logos, only DTB hash fixed)
Uso: python3 -I mklogo.py [--force]
"""
import sys, struct, hashlib, os
B = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [B, B + '/autoflash']
import bootimg, rsce
L = B + '/../07-Logo/'
FORCE = '--force' in sys.argv


def bmp_rows(b):
    """Decode uncompressed 24-bit BMP -> (w, h, list of top-down rows)."""
    _, _, _, _, off, hs, w, h, _, bpp, comp = struct.unpack_from('<2sIHHIIiiHHI', b, 0)
    assert bpp == 24 and comp == 0, (bpp, comp)
    stride = (w * 3 + 3) & ~3
    H = abs(h)
    rows = [b[off + i * stride: off + i * stride + w * 3] for i in range(H)]
    if h > 0:
        rows.reverse()  # bottom-up -> top-down
    return w, H, rows


def relayout(orig, new):
    """New pixels in the ORIGINAL file layout: original header/trailer bytes verbatim, only pixels replaced."""
    _, _, _, _, off, _, w, h, _, bpp, _ = struct.unpack_from('<2sIHHIIiiHHI', orig, 0)
    bfsize = struct.unpack_from('<I', orig, 2)[0]
    nw, nh, rows = bmp_rows(new)
    assert (nw, nh) == (w, abs(h)) and bpp == 24
    stride = (w * 3 + 3) & ~3
    if h > 0:
        rows = rows[::-1]
    pix = b''.join(r + b'\0' * (stride - len(r)) for r in rows)
    assert off + len(pix) == bfsize
    out = orig[:off] + pix + orig[bfsize:]
    assert len(out) == len(orig)
    assert bmp_rows(out)[2] == bmp_rows(new)[2]  # pixel-exact vs source logo
    return out


def idof(k, r, s, ro, dt, hv):
    # Same scheme hybrid.py used to produce the inputs: only the SIZES of recovery_dtbo/dtb are hashed.
    # Identical to AOSP mkbootimg when those sections are empty (boot); reproduces both input ids.
    sh = hashlib.sha1()
    for b in (k, r, s):
        sh.update(b); sh.update(struct.pack('<I', len(b)))
    if hv >= 1: sh.update(struct.pack('<I', len(ro)))
    if hv >= 2: sh.update(struct.pack('<I', len(dt)))
    return sh.digest().ljust(32, b'\0')


def diff_ranges(a, b, base=0, gap=512):
    rng = []; C = 1 << 16
    for o in range(0, len(a), C):
        if a[o:o + C] != b[o:o + C]:
            for j in range(o, min(o + C, len(a))):
                if a[j] != b[j]:
                    if rng and rng[-1][1] >= j - gap: rng[-1][1] = j
                    else: rng.append([j, j])
    return [(x - base, y - base) for x, y in rng]


new_logo = open(L + 'logo_v2.bmp', 'rb').read()
new_logok = open(L + 'logo_kernel_v2.bmp', 'rb').read()

for name, lim in (('boot', 0x20000 * 512), ('recovery', 0x30000 * 512)):
    src = B + '/%s-hybrid.img' % name
    d, k, r, s, ro, pg, hv = bootimg.rd(src); dt = bootimg.rd.dtb
    pad = lambda b: b + b'\0' * ((-len(b)) % pg)
    assert idof(k, r, s, ro, dt, hv) == d[576:608], 'orig id mismatch'
    assert d[:pg] + pad(k) + pad(r) + pad(s) + pad(ro) + pad(dt) == d
    s_off = pg + len(pad(k)) + len(pad(r))
    R0 = rsce.parse(s)
    ol = {e['name']: e['data'] for e in R0['entries']}
    for variant in ('logo', 'dtbfix'):
        out = B + '/%s-hybrid-%s.img' % (name, variant)
        R = rsce.parse(s)
        rsce.replace(R, 'rk-kernel.dtb', ol['rk-kernel.dtb'])  # same bytes, fresh SHA-1
        if variant == 'logo':
            rsce.replace(R, 'logo.bmp', relayout(ol['logo.bmp'], new_logo))
            rsce.replace(R, 'logo_kernel.bmp', relayout(ol['logo_kernel.bmp'], new_logok))
        ns = rsce.build(R)
        h = bytearray(d[:pg]); struct.pack_into('<I', h, 24, len(ns)); h[576:608] = idof(k, r, ns, ro, dt, hv)
        img = bytes(h) + pad(k) + pad(r) + pad(ns) + pad(ro) + pad(dt)
        assert len(img) <= lim
        if os.path.exists(out) and not FORCE: sys.exit('exists: %s (use --force)' % out)
        open(out, 'wb').write(img)
        # verify from disk
        d2, k2, r2, s2, ro2, pg2, hv2 = bootimg.rd(out); dt2 = bootimg.rd.dtb
        assert (k2, r2, ro2, dt2, pg2, hv2) == (k, r, ro, dt, pg, hv)
        assert idof(k2, r2, s2, ro2, dt2, hv2) == d2[576:608]
        A = R0['entries']; N = rsce.parse(s2)['entries']
        assert [(a['name'], a['offset']) for a in A] == [(n['name'], n['offset']) for n in N]
        for n in N:
            assert n['hash'][:20] == hashlib.sha1(n['data']).digest() and n['hash_size'] == 20, n['name']
        changed = [a['name'] for a, n in zip(A, N) if a['data'] != n['data']]
        rehashed = [a['name'] for a, n in zip(A, N) if a['hash'] != n['hash']]
        print('==', out)
        print('   size %d (%.1f%% of %d MiB)  md5 %s' % (len(img), 100 * len(img) / lim, lim >> 20, hashlib.md5(img).hexdigest()))
        print('   entry data changed:', changed, '| entry hash changed:', rehashed)
        print('   header diff:', diff_ranges(d[:pg], d2[:pg]), 'second diff (rel. to second):',
              diff_ranges(d[s_off:s_off + len(s)], d2[s_off:s_off + len(s2)]),
              'other sections diff:', d[pg:s_off] != d2[pg:s_off] or d[s_off + len(pad(s)):] != d2[s_off + len(pad(s)):])
