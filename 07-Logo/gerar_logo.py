#!/usr/bin/env python3
"""Gera o logo de arranque A95X Z2 (BMP 24/8-bit + PNG) em Python puro.

Sem dependencias externas: le as fontes TrueType (glyf) do Windows,
rasteriza com anti-aliasing e escreve BMP/PNG com struct + zlib.
"""
import math, os, struct, sys, zlib

W, H = 1280, 720  # resolucao base do desenho (as outras saidas escalam a partir desta)
OUT = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = ["/mnt/c/Windows/Fonts", "/usr/share/fonts/truetype"]


# ---------------------------------------------------------------- TrueType
class Font:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        d = self.d
        n = struct.unpack(">H", d[4:6])[0]
        self.t = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            self.t[tag.decode()] = (off, ln)
        h = self.t["head"][0]
        self.upem = struct.unpack(">H", d[h + 18:h + 20])[0]
        self.locfmt = struct.unpack(">h", d[h + 50:h + 52])[0]
        m = self.t["maxp"][0]
        self.ng = struct.unpack(">H", d[m + 4:m + 6])[0]
        hh = self.t["hhea"][0]
        self.nhm = struct.unpack(">H", d[hh + 34:hh + 36])[0]
        self._cmap()

    def _cmap(self):
        d = self.d
        c = self.t["cmap"][0]
        n = struct.unpack(">H", d[c + 2:c + 4])[0]
        sub = None
        for i in range(n):
            pid, eid, off = struct.unpack(">HHI", d[c + 4 + 8 * i: c + 12 + 8 * i])
            if pid == 3 and eid == 1:
                sub = c + off
        assert sub is not None and struct.unpack(">H", d[sub:sub + 2])[0] == 4
        segx2 = struct.unpack(">H", d[sub + 6:sub + 8])[0]
        seg = segx2 // 2
        ends = struct.unpack(">%dH" % seg, d[sub + 14: sub + 14 + segx2])
        st = sub + 16 + segx2
        starts = struct.unpack(">%dH" % seg, d[st: st + segx2])
        deltas = struct.unpack(">%dh" % seg, d[st + segx2: st + 2 * segx2])
        ro = st + 2 * segx2
        roffs = struct.unpack(">%dH" % seg, d[ro: ro + segx2])
        self.cm = (ends, starts, deltas, roffs, ro)

    def gid(self, ch):
        code = ord(ch)
        ends, starts, deltas, roffs, ro = self.cm
        for i, e in enumerate(ends):
            if code <= e:
                if code < starts[i]:
                    return 0
                if roffs[i] == 0:
                    return (code + deltas[i]) & 0xFFFF
                a = ro + 2 * i + roffs[i] + 2 * (code - starts[i])
                g = struct.unpack(">H", self.d[a:a + 2])[0]
                return (g + deltas[i]) & 0xFFFF if g else 0
        return 0

    def advance(self, g):
        hm = self.t["hmtx"][0]
        i = min(g, self.nhm - 1)
        return struct.unpack(">H", self.d[hm + 4 * i: hm + 4 * i + 2])[0]

    def _loc(self, g):
        lo = self.t["loca"][0]
        if self.locfmt == 0:
            a, b = struct.unpack(">HH", self.d[lo + 2 * g: lo + 2 * g + 4])
            return a * 2, b * 2
        return struct.unpack(">II", self.d[lo + 4 * g: lo + 4 * g + 8])

    def contours(self, g):
        """Lista de contornos; cada contorno = lista de pontos (x, y, on)."""
        d = self.d
        a, b = self._loc(g)
        if a == b:
            return []
        p = self.t["glyf"][0] + a
        nc = struct.unpack(">h", d[p:p + 2])[0]
        if nc < 0:
            return self._composite(p + 10)
        ends = struct.unpack(">%dH" % nc, d[p + 10: p + 10 + 2 * nc])
        npts = ends[-1] + 1
        q = p + 10 + 2 * nc
        il = struct.unpack(">H", d[q:q + 2])[0]
        q += 2 + il
        flags = []
        while len(flags) < npts:
            f = d[q]; q += 1
            flags.append(f)
            if f & 8:
                r = d[q]; q += 1
                flags.extend([f] * r)
        xs, ys = [], []
        v = 0
        for f in flags:
            if f & 2:
                dx = d[q]; q += 1
                v += dx if f & 16 else -dx
            elif not f & 16:
                v += struct.unpack(">h", d[q:q + 2])[0]; q += 2
            xs.append(v)
        v = 0
        for f in flags:
            if f & 4:
                dy = d[q]; q += 1
                v += dy if f & 32 else -dy
            elif not f & 32:
                v += struct.unpack(">h", d[q:q + 2])[0]; q += 2
            ys.append(v)
        out, s = [], 0
        for e in ends:
            out.append([(xs[i], ys[i], flags[i] & 1) for i in range(s, e + 1)])
            s = e + 1
        return out

    def _composite(self, q):
        d = self.d
        out = []
        while True:
            fl, gi = struct.unpack(">HH", d[q:q + 4]); q += 4
            if fl & 1:
                dx, dy = struct.unpack(">hh", d[q:q + 4]); q += 4
            else:
                dx, dy = struct.unpack(">bb", d[q:q + 2]); q += 2
            if fl & 8:
                q += 2
            elif fl & 0x40:
                q += 4
            elif fl & 0x80:
                q += 8
            for c in self.contours(gi):
                out.append([(x + dx, y + dy, on) for x, y, on in c])
            if not fl & 0x20:
                break
        return out


def flatten(contour, steps=10):
    """Converte contorno quadratico TrueType em poligono."""
    pts = contour
    n = len(pts)
    # encontrar um ponto 'on' para comecar
    k = next((i for i, p in enumerate(pts) if p[2]), None)
    if k is None:
        x0 = (pts[0][0] + pts[1][0]) / 2; y0 = (pts[0][1] + pts[1][1]) / 2
        pts = [(x0, y0, 1)] + pts[1:] + [pts[0]]
        n = len(pts); k = 0
    seq = pts[k:] + pts[:k]
    poly = [(seq[0][0], seq[0][1])]
    cur = (seq[0][0], seq[0][1])
    ctrl = None
    for x, y, on in seq[1:] + [seq[0]]:
        if on:
            if ctrl is None:
                poly.append((x, y))
            else:
                poly += quad(cur, ctrl, (x, y), steps)
                ctrl = None
            cur = (x, y)
        else:
            if ctrl is not None:
                mid = ((ctrl[0] + x) / 2, (ctrl[1] + y) / 2)
                poly += quad(cur, ctrl, mid, steps)
                cur = mid
            ctrl = (x, y)
    return poly


def quad(p0, c, p1, steps):
    r = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        r.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
                  u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))
    return r


# ---------------------------------------------------------- rasterizacao
def raster(polys, w, h, sub=8):
    """Cobertura anti-aliased (0..1) por pixel, regra nonzero, exacta em x."""
    edges = []
    for poly in polys:
        for i in range(len(poly)):
            x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % len(poly)]
            if y0 == y1:
                continue
            dirn = 1 if y1 > y0 else -1
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            edges.append((y0, y1, x0, (x1 - x0) / (y1 - y0), dirn))
    cov = [[0.0] * w for _ in range(h)]
    if not edges:
        return cov
    ymin = max(0, int(min(e[0] for e in edges)))
    ymax = min(h - 1, int(max(e[1] for e in edges)) + 1)
    for py in range(ymin, ymax + 1):
        row = cov[py]
        for s in range(sub):
            sy = py + (s + 0.5) / sub
            xs = []
            for y0, y1, x0, k, dn in edges:
                if y0 <= sy < y1:
                    xs.append((x0 + (sy - y0) * k, dn))
            if not xs:
                continue
            xs.sort()
            wind = 0
            for i in range(len(xs) - 1):
                wind += xs[i][1]
                if wind != 0:
                    add_span(row, xs[i][0], xs[i + 1][0], 1.0 / sub, w)
    return cov


def add_span(row, a, b, wgt, w):
    if b <= a:
        return
    a = max(a, 0.0); b = min(b, float(w))
    if b <= a:
        return
    ia, ib = int(a), int(b)
    if ia == ib:
        row[ia] += (b - a) * wgt
        return
    row[ia] += (ia + 1 - a) * wgt
    for x in range(ia + 1, ib):
        row[x] += wgt
    if ib < w:
        row[ib] += (b - ib) * wgt


def text_polys(font, text, px, x, baseline, tracking=0.0):
    """Poligonos do texto em coordenadas de ecra. px = altura em pixels do em."""
    sc = px / font.upem
    polys = []
    pen = x
    for ch in text:
        g = font.gid(ch)
        for c in font.contours(g):
            polys.append([(pen + gx * sc, baseline - gy * sc) for gx, gy in flatten(c)])
        pen += font.advance(g) * sc + tracking
    return polys, pen - tracking - x


def bbox(polys):
    xs = [p[0] for pl in polys for p in pl]; ys = [p[1] for pl in polys for p in pl]
    return min(xs), min(ys), max(xs), max(ys)


def shift(polys, dx, dy):
    return [[(x + dx, y + dy) for x, y in pl] for pl in polys]


# ---------------------------------------------------------------- imagem
def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def hexc(s):
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def find_font(names):
    for n in names:
        for d in FONT_DIRS:
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower() == n.lower():
                        return os.path.join(root, f)
    return None


def build(sub1, sub2, W=W, H=H):
    """Desenha o logo em W x H. Todas as medidas sao relativas a 1280x720 e escalam por S."""
    S = W / 1280.0
    bold = find_font(["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"])
    light = find_font(["segoeuisl.ttf", "segoeuil.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    if not bold or not light:
        sys.exit("Fonte TrueType nao encontrada")
    print("Fontes:", bold, "|", light)
    fb, fl = Font(bold), Font(light)

    # Fundo: gradiente radial escuro (#16202C no centro -> #06080B nas margens)
    c_in, c_out = hexc("#16202C"), hexc("#06080B")
    img = [[None] * W for _ in range(H)]
    cx, cy = W / 2, H / 2 - 20 * S
    rmax = math.hypot(W / 2, H / 2)
    for y in range(H):
        r_ = img[y]
        for x in range(W):
            t = min(1.0, math.hypot((x - cx) * 0.85, (y - cy) * 1.25) / rmax)
            t = t * t * (3 - 2 * t)
            r_[x] = list(lerp(c_in, c_out, t))

    def blend(cov, colorfn):
        for y in range(H):
            row = cov[y]
            if not any(row):
                continue
            ir = img[y]
            for x in range(W):
                a = row[x]
                if a <= 0:
                    continue
                a = min(1.0, a)
                c = colorfn(x, y)
                p = ir[x]
                for i in range(3):
                    p[i] = p[i] * (1 - a) + c[i] * a

    # Wordmark "A95X" (branco) + "Z2" (gradiente ciano -> violeta)
    size = 170 * S
    p1, w1 = text_polys(fb, "A95X", size, 0, 0, tracking=2 * S)
    gap = size * 0.22
    p2, w2 = text_polys(fb, "Z2", size, 0, 0, tracking=2 * S)
    allp = p1 + shift(p2, w1 + gap, 0)
    x0, y0, x1, y1 = bbox(allp)
    tw, th = x1 - x0, y1 - y0
    ox = (W - tw) / 2 - x0
    oy = (H / 2 - 40 * S) - (y0 + th / 2)
    p1s = shift(p1, ox, oy)
    p2s = shift(p2, ox + w1 + gap, oy)
    z_x0, _, z_x1, _ = bbox(p2s)

    cyan, violet = hexc("#00C2FF"), hexc("#7B61FF")
    white = hexc("#F2F5F8")

    def grad_z(x, y):
        return lerp(cyan, violet, max(0.0, min(1.0, (x - z_x0) / (z_x1 - z_x0))))

    # brilho suave por tras do "Z2"
    gx, gy = (z_x0 + z_x1) / 2, oy - th / 2 - y0 * 0  # aprox. centro
    _, wy0, _, wy1 = bbox(allp)
    gy = (wy0 + wy1) / 2 + oy
    for y in range(H):
        ir = img[y]
        for x in range(W):
            dd = math.hypot((x - gx) / (260 * S), (y - gy) / (150 * S))
            if dd < 1:
                a = (1 - dd) ** 2 * 0.10
                c = lerp(cyan, violet, 0.5)
                p = ir[x]
                for i in range(3):
                    p[i] = p[i] * (1 - a) + c[i] * a

    blend(raster(p1s, W, H), lambda x, y: white)
    blend(raster(p2s, W, H), grad_z)

    # Linha de destaque (gradiente, com pontas a desvanecer)
    ly = int(oy + y1 + 38 * S)
    lw = int(round(420 * S))
    nl = int(round(4 * S))  # espessura: 4 px a 720p, 6 px a 1080p
    lrows = [(ly + i, 0.35 if i in (0, nl - 1) else 1.0) for i in range(nl)]
    lx0 = int(W / 2 - lw / 2)
    for x in range(lx0, lx0 + lw):
        t = (x - lx0) / lw
        fade = min(1.0, t / 0.18, (1 - t) / 0.18)
        c = lerp(cyan, violet, t)
        for yy, a in lrows:
            a *= fade
            p = img[yy][x]
            for i in range(3):
                p[i] = p[i] * (1 - a) + c[i] * a

    # Subtitulo
    sp, _ = text_polys(fl, sub1, 30 * S, 0, 0, tracking=7 * S)
    sx0, sy0, sx1, sy1 = bbox(sp)
    sps = shift(sp, (W - (sx1 - sx0)) / 2 - sx0, ly + 44 * S - sy0)
    blend(raster(sps, W, H), lambda x, y: hexc("#8C97A8"))
    sub_bottom = ly + 44 * S + (sy1 - sy0)

    # Segunda linha, mais pequena e mais discreta
    # (21/11/2026) peso normal, 24 px e cor do subtitulo: em Semilight a 20 px os tracos tinham
    # 1-2 px e na TV pareciam serrilhados.
    fr = Font(find_font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]))
    sp2, _ = text_polys(fr, sub2, 24 * S, 0, 0, tracking=2.5 * S)
    tx0, ty0, tx1, ty1 = bbox(sp2)
    sps2 = shift(sp2, (W - (tx1 - tx0)) / 2 - tx0, sub_bottom + 20 * S - ty0)
    blend(raster(sps2, W, H), lambda x, y: hexc("#8C97A8"))

    # Arredondar com dither ordenado leve (evita bandas no gradiente)
    bayer = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
    pix = []
    for y in range(H):
        row = []
        for x in range(W):
            dv = (bayer[y & 3][x & 3] + 0.5) / 16 - 0.5
            row.append(tuple(max(0, min(255, int(v + 0.5 + dv))) for v in img[y][x]))
        pix.append(row)
    return pix


# ---------------------------------------------------------------- escrita
def write_bmp24(path, pix):
    h, w = len(pix), len(pix[0])
    stride = (w * 3 + 3) & ~3
    data = bytearray()
    for y in range(h - 1, -1, -1):  # bottom-up
        row = bytearray()
        for r, g, b in pix[y]:
            row += bytes((b, g, r))
        row += b"\0" * (stride - w * 3)
        data += row
    hdr = struct.pack("<2sIHHI", b"BM", 54 + len(data), 0, 0, 54)
    dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    open(path, "wb").write(hdr + dib + data)


def median_cut(colors, n=256):
    """colors: dict (r,g,b)->contagem. Devolve paleta."""
    boxes = [list(colors.items())]
    while len(boxes) < n:
        best, bi, ch = -1, -1, 0
        for i, bx in enumerate(boxes):
            if len(bx) < 2:
                continue
            for c in range(3):
                vals = [k[c] for k, _ in bx]
                rng = (max(vals) - min(vals)) * math.log(1 + sum(v for _, v in bx))
                if rng > best:
                    best, bi, ch = rng, i, c
        if bi < 0:
            break
        bx = sorted(boxes.pop(bi), key=lambda kv: kv[0][ch])
        tot = sum(v for _, v in bx); acc = 0; cut = 1
        for j, (_, v) in enumerate(bx):
            acc += v
            if acc >= tot / 2:
                cut = max(1, min(len(bx) - 1, j + 1)); break
        boxes += [bx[:cut], bx[cut:]]
    pal = []
    for bx in boxes:
        t = sum(v for _, v in bx)
        pal.append(tuple(int(sum(k[i] * v for k, v in bx) / t + 0.5) for i in range(3)))
    while len(pal) < n:
        pal.append((0, 0, 0))
    return pal


def write_bmp8(path, pix):
    h, w = len(pix), len(pix[0])
    counts = {}
    for row in pix:
        for c in row:
            counts[c] = counts.get(c, 0) + 1
    pal = median_cut(counts)
    cache = {}

    def idx(c):
        i = cache.get(c)
        if i is None:
            i = min(range(256), key=lambda k: (pal[k][0] - c[0]) ** 2 * 3 + (pal[k][1] - c[1]) ** 2 * 4 + (pal[k][2] - c[2]) ** 2 * 2)
            cache[c] = i
        return i

    stride = (w + 3) & ~3
    data = bytearray()
    for y in range(h - 1, -1, -1):
        data += bytes(idx(c) for c in pix[y]) + b"\0" * (stride - w)
    paldata = b"".join(bytes((b, g, r, 0)) for r, g, b in pal)
    off = 54 + len(paldata)
    hdr = struct.pack("<2sIHHI", b"BM", off + len(data), 0, 0, off)
    dib = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 8, 0, len(data), 2835, 2835, 256, 256)
    open(path, "wb").write(hdr + dib + paldata + data)
    return len(counts)


def write_png(path, pix):
    h, w = len(pix), len(pix[0])
    raw = bytearray()
    for row in pix:
        raw.append(0)
        for c in row:
            raw += bytes(c)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


if __name__ == "__main__":
    # Uso: python3 gerar_logo.py            -> tudo (A e B a 1280x720 + B a 1920x1080)
    #      python3 gerar_logo.py 720|1080   -> so essa resolucao
    sel = sys.argv[1:] or ["720", "1080"]
    VARIANTES = [
        ("", "ANDROID TV", "Firmware personalizado  \u00b7  by Ivo Barbosa"),   # variante A
        ("_v2", "ANDROID 10  \u00b7  2026", "by Ivo Barbosa"),                  # variante B
    ]
    if "720" in sel:
        for suf, s1, s2 in VARIANTES:
            pix = build(s1, s2)
            write_bmp24(os.path.join(OUT, "logo%s.bmp" % suf), pix)
            write_bmp24(os.path.join(OUT, "logo_kernel%s.bmp" % suf), pix)
            nc = write_bmp8(os.path.join(OUT, "logo_8bit%s.bmp" % suf), pix)
            write_png(os.path.join(OUT, "preview%s.png" % suf), pix)
            print("Variante %s: cores unicas 24-bit: %d" % (suf or "A", nc))
    if "1080" in sel:
        # Variante B em 1920x1080 (resolucao nativa do ecra): o U-Boot/kernel nao tem de
        # escalar nem centrar -> ocupa o ecra todo. BMP 24-bit normal (bottom-up, cabecalho 40 B).
        _, s1, s2 = VARIANTES[1]
        pix = build(s1, s2, 1920, 1080)
        write_bmp24(os.path.join(OUT, "logo_v2_1080.bmp"), pix)
        write_png(os.path.join(OUT, "preview_v2_1080.png"), pix)
        print("Variante B 1920x1080: logo_v2_1080.bmp + preview_v2_1080.png")
    print("OK")
