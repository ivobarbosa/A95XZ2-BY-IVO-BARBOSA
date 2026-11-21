"""Replace /system/bin/vfdsrv contents (same size, in place) inside a sparse super.img.
Usage: python3 -I patch_super.py <super.img sparse> <out super-hybrid.img> <script.sh> <system_extent_offset> <first_block> <file_size>
"""
import struct, sys, shutil

def main():
    src, dst, script, sys_off, blk, fsize = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4], 0), int(sys.argv[5]), int(sys.argv[6])
    data = open(script, 'rb').read()
    assert data.startswith(b'#!/system/bin/sh\n')
    assert len(data) + 2 <= fsize, 'script too big'
    pad = fsize - len(data) - 2
    payload = data + b'#' + b' ' * pad + b'\n'
    assert len(payload) == fsize
    raw_off = sys_off + blk * 4096
    shutil.copyfile(src, dst)
    f = open(dst, 'r+b'); h = f.read(28)
    magic, maj, mnr, fhs, chs, bsz, tblk, tchunk, crc = struct.unpack('<IHHHHIIII', h)
    assert magic == 0xED26FF3A and bsz == 4096
    pos = fhs; out_blk = 0; written = 0
    for _ in range(tchunk):
        f.seek(pos); ct, _r, csz, tsz = struct.unpack('<HHII', f.read(chs))
        start = out_blk * bsz; end = start + csz * bsz
        if start <= raw_off < end:
            assert ct == 0xCAC1, 'target not in RAW chunk (type %#x)' % ct
            assert raw_off + fsize <= end, 'payload crosses chunk boundary'
            f.seek(pos + chs + (raw_off - start)); old = f.read(4)
            assert old == b'\x7fELF', 'unexpected original bytes %r' % old
            f.seek(pos + chs + (raw_off - start)); f.write(payload); written = 1
            print('patched chunk at file offset %#x, raw offset %#x' % (pos + chs + (raw_off - start), raw_off))
            break
        pos += tsz; out_blk += csz
    assert written
    if crc: print('warning: image has CRC (%#x), not updated' % crc)

if __name__ == '__main__':
    main()
