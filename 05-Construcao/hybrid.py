"""Build a hybrid HK1 Max boot.img whose DTB carries the A95X Z2 IR keymap (0xDF00)
and the A95X Z2 board DDR de-skew values. In-place patching only (sizes preserved).
Usage: python3 -I hybrid.py <box_dtb> <hk1_boot.img> <out_dir>
"""
import struct, sys, os, hashlib

def fdt_props(blob):
    """Return {path: {name: (value_offset, length)}} for an FDT blob."""
    magic, tot, off_struct, off_strings = struct.unpack_from('>IIII', blob, 0)
    assert magic == 0xd00dfeed
    out = {}; stack = []; i = off_struct
    while True:
        tok = struct.unpack_from('>I', blob, i)[0]; i += 4
        if tok == 1:
            end = blob.index(b'\0', i); name = blob[i:end].decode(); i = (end + 4) & ~3
            stack.append(name); path = '/' + '/'.join(s for s in stack if s)
            out.setdefault(path if path != '/' else '/', {})
        elif tok == 2: stack.pop()
        elif tok == 3:
            ln, nameoff = struct.unpack_from('>II', blob, i); i += 8
            e = blob.index(b'\0', off_strings + nameoff); pname = blob[off_strings + nameoff:e].decode()
            path = '/' + '/'.join(s for s in stack if s)
            out.setdefault(path, {})[pname] = (i, ln); i = (i + ln + 3) & ~3
        elif tok == 4: continue
        elif tok == 9: break
        else: raise ValueError('bad token %d at %d' % (tok, i))
    return out

def get(blob, props, path, name):
    o, l = props[path][name]; return blob[o:o + l]

def main():
    box_dtb = open(sys.argv[1], 'rb').read()
    boot = bytearray(open(sys.argv[2], 'rb').read())
    out = sys.argv[3]; os.makedirs(out, exist_ok=True)
    ks, ka, rs, ra, ss, sa, ta, ps, hv = struct.unpack_from('<9I', boot, 8)
    pg = lambda n: (n + ps - 1) // ps * ps
    k_off = ps; r_off = k_off + pg(ks); s_off = r_off + pg(rs)
    second = bytearray(boot[s_off:s_off + ss])
    # locate rk-kernel.dtb inside RSCE
    i = second.find(b'ENTR'); assert second[i + 4:i + 17] == b'rk-kernel.dtb'
    doff, dsz = struct.unpack_from('<II', second, i + 260); doff *= 512
    hk = bytearray(second[doff:doff + dsz])
    pb = fdt_props(box_dtb); ph = fdt_props(bytes(hk))
    report = []
    # 1) IR: replace HK1 ir_key2 (0xff00) with box ir_key2 (0xdf00)
    src = '/pwm@ff1b0030/ir_key2'; dst = '/pwm@ff1b0030/ir_key2'
    buc = get(box_dtb, pb, src, 'rockchip,usercode'); btab = get(box_dtb, pb, src, 'rockchip,key_table')
    o, l = ph[dst]['rockchip,usercode']; old = bytes(hk[o:o + l]); hk[o:o + l] = buc
    report.append('IR %s usercode %s -> %s' % (dst, old.hex(), buc.hex()))
    o, l = ph[dst]['rockchip,key_table']
    assert len(btab) <= l and len(btab) % 8 == 0 and l % 8 == 0, (len(btab), l)
    pad = btab + btab[-8:] * ((l - len(btab)) // 8)  # repeat last pair to keep size
    hk[o:o + l] = pad
    report.append('IR key_table %d pares (box) gravados em %d pares (HK1, %d repetidos)' % (len(btab) // 8, l // 8, (l - len(btab)) // 8))
    # 2) DDR de-skew from the box board
    n = 0
    for name, (bo, bl) in pb['/ddr_timing'].items():
        if 'de-skew' not in name or name not in ph['/ddr_timing']: continue
        ho, hl = ph['/ddr_timing'][name]
        if hl != bl: continue
        if hk[ho:ho + hl] != box_dtb[bo:bo + bl]:
            hk[ho:ho + hl] = box_dtb[bo:bo + bl]; n += 1
    report.append('DDR de-skew: %d valores copiados da placa A95X Z2' % n)
    # 3) Front display: stop the HK1 2-wire fd628 driver from grabbing GPIO 85/86
    #    (A95X Z2 uses a 3-wire SM1628 driven from userspace by vfdsrv.sh)
    if '/fd628_dev' in ph and 'compatible' in ph['/fd628_dev']:
        o, l = ph['/fd628_dev']['compatible']
        if bytes(hk[o:o + l]) == b'fd628_dev\0':
            hk[o:o + l] = b'fd628_off\0'
            report.append('VFD: driver fd628 desligado (compatible fd628_dev -> fd628_off)')
    # verify
    ph2 = fdt_props(bytes(hk))
    assert get(bytes(hk), ph2, dst, 'rockchip,usercode') == buc
    open(os.path.join(out, 'rk-kernel-hybrid.dtb'), 'wb').write(hk)
    second[doff:doff + dsz] = hk
    boot[s_off:s_off + ss] = second
    # recompute mkbootimg id (sha1) for header v2
    sha = hashlib.sha1()
    sha.update(boot[k_off:k_off + ks]); sha.update(struct.pack('<I', ks))
    sha.update(boot[r_off:r_off + rs]); sha.update(struct.pack('<I', rs))
    sha.update(boot[s_off:s_off + ss]); sha.update(struct.pack('<I', ss))
    if hv >= 1:
        rdsz = struct.unpack_from('<I', boot, 1632)[0]; sha.update(struct.pack('<I', rdsz))
    if hv >= 2:
        dsz2 = struct.unpack_from('<I', boot, 1648)[0]; sha.update(struct.pack('<I', dsz2))
    new_id = sha.digest()
    boot[576:576 + 20] = new_id; boot[596:608] = b'\0' * 12
    open(os.path.join(out, 'boot-hybrid.img'), 'wb').write(boot)
    report.append('boot.img id novo %s' % new_id.hex())
    print('\n'.join(report))

if __name__ == '__main__':
    main()
