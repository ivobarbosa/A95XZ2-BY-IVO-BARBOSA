#!/usr/bin/env python3
"""Gera o icone e o banner do launcher a partir do logotipo de arranque (BMP 24 bits).

Uso: python3 mkicons.py <logo_v2_1080.bmp> <pasta res>
Sem dependencias (so biblioteca padrao): le o BMP, reduz por media de blocos e grava PNG.
"""
import struct, sys, zlib, os


def read_bmp(path):
    d = open(path, 'rb').read()
    off, = struct.unpack_from('<I', d, 10)
    w, h, _, bpp = struct.unpack_from('<iiHH', d, 18)
    assert bpp == 24, 'esperado BMP de 24 bits'
    top_down = h < 0
    h = abs(h)
    stride = (w * 3 + 3) & ~3
    rows = []
    for y in range(h):
        sy = y if top_down else h - 1 - y
        r = d[off + sy * stride: off + sy * stride + w * 3]
        rows.append([(r[x * 3 + 2], r[x * 3 + 1], r[x * 3]) for x in range(w)])
    return w, h, rows


def downscale(rows, x0, y0, w, h, f):
    out = []
    for oy in range(h // f):
        line = []
        for ox in range(w // f):
            s = [0, 0, 0]
            for yy in range(f):
                row = rows[y0 + oy * f + yy]
                for xx in range(f):
                    p = row[x0 + ox * f + xx]
                    s[0] += p[0]; s[1] += p[1]; s[2] += p[2]
            n = f * f
            line.append((s[0] // n, s[1] // n, s[2] // n))
        out.append(line)
    return out


def write_png(path, px):
    h, w = len(px), len(px[0])
    raw = b''.join(b'\0' + bytes(c for p in row for c in p) for row in px)

    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def main():
    src, res = sys.argv[1], sys.argv[2]
    w, h, rows = read_bmp(src)
    assert (w, h) == (1920, 1080), (w, h)
    os.makedirs(os.path.join(res, 'drawable-hdpi'), exist_ok=True)
    # banner 320x180 (16:9, ecra inteiro reduzido 6x)
    write_png(os.path.join(res, 'drawable-hdpi', 'banner.png'), downscale(rows, 0, 0, 1920, 1080, 6))
    # icone 144x144 (hdpi = 96 dp): quadrado central 1080x1080 reduzido 7.5x -> usa 1050 / 7 = 150
    write_png(os.path.join(res, 'drawable-hdpi', 'icon.png'), downscale(rows, 435, 15, 1050, 1050, 7))
    print('icon.png e banner.png gerados em', res)


if __name__ == '__main__':
    main()
