"""Gera bootanimation.zip (STORED) 1920x1080 a partir de um BMP 24-bit, com fade-in.
Usage: python3 -I mkbootanim.py <logo.bmp> <out.zip> <tamanho_exato_bytes>
part0: 10 frames de fade-in (toca 1x); part1: frame final em ciclo.
O zip e preenchido com 'pad.bin' (STORED) ate ao tamanho exato pedido.
So stdlib (sem Pillow).
"""
import struct, sys, zlib, zipfile, io

W, H, FRAMES = 1920, 1080, 10
DT = (2026, 1, 1, 0, 0, 0)

def read_bmp(path):
    d = open(path, 'rb').read()
    assert d[:2] == b'BM'
    off = struct.unpack_from('<I', d, 10)[0]
    w, h, planes, bpp, comp = struct.unpack_from('<iiHHI', d, 18)
    assert bpp == 24 and comp == 0, (bpp, comp)
    stride = (w * 3 + 3) & ~3
    rows = []
    for y in range(abs(h)):
        sy = (abs(h) - 1 - y) if h > 0 else y
        r = d[off + sy * stride: off + sy * stride + w * 3]
        rgb = bytearray(len(r)); rgb[0::3] = r[2::3]; rgb[1::3] = r[1::3]; rgb[2::3] = r[0::3]  # BGR->RGB
        rows.append(bytes(rgb))
    return w, abs(h), rows

def scale_center(w, h, rows):
    """Escala (bilinear) para caber em WxH mantendo o aspeto e centra em fundo preto."""
    s = min(W / w, H / h); nw, nh = int(round(w * s)), int(round(h * s))
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    xs = []
    for x in range(nw):
        fx = min(max((x + 0.5) / s - 0.5, 0), w - 1); ix = min(int(fx), w - 2); xs.append((ix * 3, int((fx - ix) * 256)))
    out = []
    black = bytes(W * 3)
    for y in range(H):
        if y < y0 or y >= y0 + nh: out.append(black); continue
        fy = min(max((y - y0 + 0.5) / s - 0.5, 0), h - 1); iy = min(int(fy), h - 2); wy = int((fy - iy) * 256)
        a, b = rows[iy], rows[iy + 1]
        row = bytearray(W * 3); p = x0 * 3
        for ix3, wx in xs:
            for c in range(3):
                t = (a[ix3 + c] * (256 - wx) + a[ix3 + 3 + c] * wx)
                u = (b[ix3 + c] * (256 - wx) + b[ix3 + 3 + c] * wx)
                row[p] = (t * (256 - wy) + u * wy) >> 16; p += 1
        out.append(bytes(row))
    return out

def png(rows):
    raw = b''.join(b'\0' + r for r in rows)
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))

def build(entries, pad):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_STORED) as z:
        for n, d in entries + ([('pad.bin', b'\0' * pad)] if pad is not None else []):
            zi = zipfile.ZipInfo(n, DT); zi.compress_type = zipfile.ZIP_STORED; zi.external_attr = 0o644 << 16
            z.writestr(zi, d)
    return bio.getvalue()

def main():
    src, dst, target = sys.argv[1], sys.argv[2], int(sys.argv[3])
    w, h, rows = read_bmp(src)
    full = scale_center(w, h, rows)
    entries = [('desc.txt', b'%d %d 10\np 1 0 part0\np 0 0 part1\n' % (W, H))]
    for k in range(FRAMES):
        a = (k + 1) * 256 // FRAMES
        lut = bytes((v * a) >> 8 for v in range(256))
        entries.append(('part0/%03d.png' % k, png([r.translate(lut) for r in full])))
    entries.append(('part1/000.png', png(full)))
    base = len(build(entries, 0))
    data = build(entries, target - base)
    assert len(data) == target, (len(data), target)
    open(dst, 'wb').write(data)
    z = zipfile.ZipFile(dst)
    assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
    assert z.testzip() is None
    print('ok', dst, len(data), 'conteudo util', base, 'entradas', len(z.namelist()))

if __name__ == '__main__':
    main()
