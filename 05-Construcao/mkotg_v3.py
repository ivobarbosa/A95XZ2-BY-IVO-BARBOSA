"""Build boot-v3.img / recovery-v3.img: rk-kernel.dtb (RSCE 'second') with usb@ff580000 dr_mode "host" -> "otg".
Inputs (read-only): boot-hybrid-logo1080-magisk.img (Magisk 31.1), recovery-hybrid-logo1080.img
Change: property value "host\\0" (len 5) -> "otg\\0\\0" (len stays 5, so the FDT layout/size is unchanged).
  Linux of_property_read_string() only requires a NUL within the length (strnlen(val, len) < len), and
  usb_get_dr_mode() does match_string() on "otg" -> USB_DR_MODE_OTG. U-Boot fdt_getprop/strcmp also sees "otg".
RSCE entry hash (SHA-1) updated by rsce.replace; RSCE size unchanged -> second_size, padding and (recovery)
recovery_dtbo_offset unchanged (re-asserted). Header id recomputed with the scheme the input already uses
(SHA-1 over kernel/ramdisk/second + sizes; Magisk's id is reproduced by the same scheme).
Uso: python3 -I mkotg_v3.py [--force]
"""
import sys, struct, hashlib, os
B = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [B, B + '/autoflash']
import bootimg, rsce
FORCE = '--force' in sys.argv
NODE, PROP, OLD, NEW = 'usb@ff580000', 'dr_mode', b'host\0', b'otg\0\0'


def fdt_props(b):
    """Minimal FDT v17 walker -> [(path, name, value, value_offset, len_field_offset)]."""
    magic, tot, offs, offstr = struct.unpack_from('>4I', b, 0)
    assert magic == 0xd00dfeed and tot == len(b), 'bad FDT'
    o, path, out = offs, [], []
    while True:
        tok = struct.unpack_from('>I', b, o)[0]; o += 4
        if tok == 1:
            e = b.index(b'\0', o); path.append(b[o:e].decode()); o = (e + 4) & ~3
        elif tok == 2:
            path.pop()
        elif tok == 3:
            ln, no = struct.unpack_from('>II', b, o)
            name = b[offstr + no:b.index(b'\0', offstr + no)].decode()
            out.append(('/'.join(path) or '/', name, b[o + 8:o + 8 + ln], o + 8, o)); o = (o + 8 + ln + 3) & ~3
        elif tok == 4:
            pass
        elif tok == 9:
            return out
        else:
            raise ValueError('FDT token %d' % tok)


def patch_dtb(dtb):
    hits = [p for p in fdt_props(dtb) if p[0].split('/')[-1] == NODE and p[1] == PROP]
    assert len(hits) == 1, hits
    _, _, val, vo, lo = hits[0]
    assert val == OLD, val
    out = bytearray(dtb); out[vo:vo + len(NEW)] = NEW
    return bytes(out)


def idof(k, r, s, ro, dt, hv):
    sh = hashlib.sha1()
    for b in (k, r, s):
        sh.update(b); sh.update(struct.pack('<I', len(b)))
    if hv >= 1: sh.update(struct.pack('<I', len(ro)))
    if hv >= 2: sh.update(struct.pack('<I', len(dt)))
    return sh.digest().ljust(32, b'\0')


for src, dst, lim in (('boot-hybrid-logo1080-magisk.img', 'boot-v3.img', 0x20000 * 512),
                      ('recovery-hybrid-logo1080.img', 'recovery-v3.img', 0x30000 * 512)):
    d, k, r, s, ro, pg, hv = bootimg.rd(B + '/' + src); dt = bootimg.rd.dtb
    pad = lambda b: b + b'\0' * ((-len(b)) % pg)
    assert idof(k, r, s, ro, dt, hv) == d[576:608], 'input id scheme not reproduced: ' + src
    assert d[:pg] + pad(k) + pad(r) + pad(s) + pad(ro) + pad(dt) == d, 'unexpected layout'
    R0 = rsce.parse(s); assert rsce.build(R0) == s
    odtb = [e for e in R0['entries'] if e['name'] == 'rk-kernel.dtb'][0]['data']
    ndtb = patch_dtb(odtb)
    R = rsce.parse(s); rsce.replace(R, 'rk-kernel.dtb', ndtb); ns = rsce.build(R)
    assert len(ns) == len(s)
    h = bytearray(d[:pg])
    struct.pack_into('<I', h, 24, len(ns))
    if hv >= 1 and ro:
        struct.pack_into('<Q', h, 1636, pg + len(pad(k)) + len(pad(r)) + len(pad(ns)))
    h[576:608] = idof(k, r, ns, ro, dt, hv)
    img = bytes(h) + pad(k) + pad(r) + pad(ns) + pad(ro) + pad(dt)
    assert len(img) == len(d) and len(img) <= lim
    out = B + '/' + dst
    if os.path.exists(out) and not FORCE: sys.exit('exists: %s (use --force)' % out)
    open(out, 'wb').write(img)

    # ---- verify from disk
    d2, k2, r2, s2, ro2, pg2, hv2 = bootimg.rd(out); dt2 = bootimg.rd.dtb
    assert (k2, r2, ro2, dt2, pg2, hv2) == (k, r, ro, dt, pg, hv), 'kernel/ramdisk/dtbo/dtb changed'
    assert idof(k2, r2, s2, ro2, dt2, hv2) == d2[576:608]
    hd = sorted(set(i // 4 * 4 for i in range(pg) if d[i] != d2[i]))
    A, N = R0['entries'], rsce.parse(s2)['entries']
    for a, n in zip(A, N):
        assert n['hash'][:n['hash_size']] == hashlib.sha1(n['data']).digest()[:n['hash_size']], n['name']
        assert n['offset'] == a['offset'] and n['name'] == a['name']
        if n['name'] != 'rk-kernel.dtb':
            assert n['data'] == a['data'] and n['hash'] == a['hash'], n['name']
    nd = [n for n in N if n['name'] == 'rk-kernel.dtb'][0]['data']
    P0, P1 = fdt_props(odtb), fdt_props(nd)
    diff = [(a[0], a[1], a[2], b[2]) for a, b in zip(P0, P1) if a[:2] != b[:2] or a[2] != b[2]]
    assert len(P0) == len(P1) and diff == [('/' + NODE, PROP, OLD, NEW)], diff
    bd = [i for i in range(len(odtb)) if odtb[i] != nd[i]]
    lenf = [p for p in P1 if p[0] == '/' + NODE and p[1] == PROP][0]
    assert struct.unpack_from('>I', nd, lenf[4])[0] == 5
    # what Linux of_property_read_string + usb_get_dr_mode would read
    v = lenf[2]; assert v.index(b'\0') < len(v) and v[:v.index(b'\0')] == b'otg'
    print('==', dst, '<-', src)
    print('   size %d (%.1f%% of %d MiB)  md5 %s' % (len(img), 100 * len(img) / lim, lim >> 20, hashlib.md5(img).hexdigest()))
    print('   kernel/ramdisk/recovery_dtbo identical; header words changed at %s (id)' % hd)
    print('   DTB bytes changed at %s; props diff: %s; FDT len field = 5; RSCE hashes ok (%d entries)' % (
        [hex(i) for i in bd], diff, len(N)))
