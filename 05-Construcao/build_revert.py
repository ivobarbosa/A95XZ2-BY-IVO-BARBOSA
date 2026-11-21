"""Build revert-android9.img: a Rockchip RKFW update image that restores the original
A95X Z2 Android 9 partition table (GPT via parameter) and its 13 essential partitions
from backup-20261120. Format copied from the HK1 Max RKFW (header, loader, RKAF layout).
Usage: python3 -I build_revert.py <backup_dir> <hk1_rkfw.img> <hk1_unpacked_dir> <out.img>
"""
import struct, sys, os, hashlib, time

T = []
for i in range(256):
    c = i << 24
    for _ in range(8):
        c = ((c << 1) ^ 0x04c10db7) if c & 0x80000000 else (c << 1)
    T.append(c & 0xFFFFFFFF)

def rkcrc_bytes(b, crc=0):
    for x in b:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ T[(crc >> 24) ^ x]
    return crc

# original A95X Z2 GPT (sectors), read from backup-20261120/emmc_inicio_16MB.img
LAYOUT = [  # name, start, size
    ('uboot', 0x4000, 0x2000), ('trust', 0x6000, 0x2000), ('misc', 0x8000, 0x2000),
    ('baseparameter', 0xa000, 0x800), ('resource', 0xa800, 0x8000), ('kernel', 0x12800, 0x10000),
    ('dtb', 0x22800, 0x2000), ('dtbo', 0x24800, 0x2000), ('logo', 0x26800, 0x8000),
    ('vbmeta', 0x2e800, 0x800), ('boot', 0x2f000, 0x10000), ('recovery', 0x3f000, 0x20000),
    ('backup', 0x5f000, 0x8000), ('cache', 0x67000, 0x80000), ('system', 0xe7000, 0x400000),
    ('metadata', 0x4e7000, 0x8000), ('vendor', 0x4ef000, 0x60000), ('oem', 0x54f000, 0x20000),
    ('frp', 0x56f000, 0x400), ('security', 0x56f400, 0x1000),
]
USERDATA_START = 0x570400
SYSTEM_UUID = 'af01642c-9b84-11e8-9b2a-234eb5e198a0'
IN_IMAGE = ['uboot', 'trust', 'misc', 'baseparameter', 'resource', 'dtbo', 'vbmeta', 'boot',
            'recovery', 'system', 'metadata', 'vendor', 'oem']  # 13 + package-file, bootloader, parameter = 16 (max)

def parameter_bytes():
    parts = ','.join('0x%08x@0x%08x(%s)' % (sz, st, n) for n, st, sz in LAYOUT)
    text = ('FIRMWARE_VER:9.0\nMACHINE_MODEL:RK3328\nMACHINE_ID:007\nMANUFACTURER:Rockchip\n'
            'MAGIC: 0x5041524B\nATAG: 0x00200800\nMACHINE: 3328\nCHECK_MASK: 0x80\nPWR_HLD: 0,0,A,0,1\n'
            'TYPE: GPT\nCMDLINE:mtdparts=rk29xxnand:%s,-@0x%08x(userdata:grow)\nuuid:system=%s\n'
            % (parts, USERDATA_START, SYSTEM_UUID)).encode()
    return b'PARM' + struct.pack('<I', len(text)) + text + struct.pack('<I', rkcrc_bytes(text))

def main():
    bdir, hk1, hk1u, out = sys.argv[1:5]
    with open(hk1, 'rb') as f:
        head = bytearray(f.read(0x66))
    assert head[:4] == b'RKFW'
    loader = open(os.path.join(hk1u, 'MiniLoaderAll.bin'), 'rb').read()
    lo, ll = struct.unpack_from('<II', head, 0x19)
    assert lo == 0x66 and ll == len(loader)
    param = parameter_bytes()
    pkg = ('# NAME\tRelative path\npackage-file\tpackage-file\nbootloader\tImage/MiniLoaderAll.bin\n'
           'parameter\tImage/parameter.txt\n' + ''.join('%s\tImage/%s.img\n' % (n, n) for n in IN_IMAGE)).encode()
    sizes = dict((n, sz) for n, st, sz in LAYOUT); starts = dict((n, st) for n, st, sz in LAYOUT)
    items = [('package-file', 'package-file', 0, 0xFFFFFFFF, pkg, None),
             ('bootloader', 'Image/MiniLoaderAll.bin', 0, 0xFFFFFFFF, loader, None),
             ('parameter', 'Image/parameter.txt', 0x4000, 0, param, None)]
    for n in IN_IMAGE:
        p = os.path.join(bdir, n + '.img')
        assert os.path.getsize(p) == sizes[n] * 512, (n, os.path.getsize(p))
        items.append((n, 'Image/%s.img' % n, sizes[n], starts[n], None, p))
    assert len(items) <= 16
    # layout inside RKAF
    pos = 0x800; table = []
    for name, fn, nsize, naddr, data, path in items:
        size = len(data) if data is not None else os.path.getsize(path)
        padded = (size + 0x7FF) // 0x800
        table.append((name, fn, nsize, pos, naddr, padded, size, data, path))
        pos += padded * 0x800
    end = table[-1][3] + table[-1][6]
    rkaf_len = (end + 0x1FF) // 0x200 * 0x200
    hdr = bytearray(0x800)
    hdr[0:4] = b'RKAF'; struct.pack_into('<I', hdr, 4, rkaf_len)
    hdr[8:8 + 6] = b'RK3328'; hdr[0x2A:0x2A + 3] = b'007'; hdr[0x48:0x48 + 8] = b'Rockchip'
    struct.pack_into('<II', hdr, 0x80, 0, 0x09000000); struct.pack_into('<I', hdr, 0x88, len(table))
    for k, (name, fn, nsize, p, naddr, padded, size, data, path) in enumerate(table):
        o = 0x8C + k * 112
        hdr[o:o + len(name)] = name.encode(); hdr[o + 32:o + 32 + len(fn)] = fn.encode()
        struct.pack_into('<IIIII', hdr, o + 92, nsize, p, naddr, padded, size)
    # RKFW header: same as HK1 except version 9.0.0, date now, image length
    struct.pack_into('<I', head, 6, 0x09000000)
    t = time.localtime(); struct.pack_into('<HBBBBB', head, 0x0E, t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
    struct.pack_into('<I', head, 0x25, rkaf_len + 4)
    md5 = hashlib.md5(); crc = 0
    with open(out, 'wb') as o:
        def w(b, in_rkaf=True):
            nonlocal crc
            o.write(b); md5.update(b)
            if in_rkaf: crc = rkcrc_bytes(b, crc)
        w(bytes(head), False); w(loader, False)
        w(bytes(hdr)); cur = 0x800
        for name, fn, nsize, p, naddr, padded, size, data, path in table:
            if cur < p: w(b'\0' * (p - cur)); cur = p
            if data is not None:
                w(data); cur += len(data)
            else:
                with open(path, 'rb') as s:
                    while True:
                        c = s.read(1 << 22)
                        if not c: break
                        w(c); cur += len(c)
            print('  +', name, size, flush=True)
        if cur < rkaf_len: w(b'\0' * (rkaf_len - cur))
        w(struct.pack('<I', crc), False)
        digest = md5.hexdigest().encode(); o.write(digest)
    print('RKAF len=%d crc=%08x md5=%s' % (rkaf_len, crc, digest.decode()))
    print('CONCLUIDO')

if __name__ == '__main__':
    main()
