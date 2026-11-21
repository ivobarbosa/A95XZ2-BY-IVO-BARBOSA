#!/usr/bin/env python3
"""bootanimation v2 (animada) para a A95X Z2 - 1920x1080, so stdlib (sem Pillow/numpy).

Uso:  python3 mkbootanim_v2.py [tamanho_exato_bytes]   (por omissao 27972528)

Saidas:
  05-Construcao/bootanimation-a95xz2-v2.zip   (desc.txt + part0 intro + part1 ciclo, tudo STORED,
                                               preenchido com pad.bin ate ao tamanho exato)
  07-Logo/animacao-preview.gif                (640x360, intro + 3 ciclos, encoder GIF/LZW proprio)
  07-Logo/animacao-frames.png                 (folha de contacto: 8 frames-chave a 480x270)

Sequencia (part0, ~3 s, toca 1x):
  0.00-0.50 s  fundo radial escuro aparece (fade a partir do preto)
  0.25-1.05 s  "A95X" aparece e sobe 36 px (ease-out)
  0.75-1.35 s  "Z2" aparece; o brilho ciano->violeta "floresce" (pico ~1.1 s) e assenta ate 2.3 s
  1.35-2.05 s  a linha de destaque desenha-se do centro para fora, com faiscas nas pontas
  1.90-2.60 s  "ANDROID 10 · 2026" aparece e sobe 14 px
  2.20-2.85 s  "by Ivo Barbosa" aparece e sobe 10 px
Ciclo (part1, 2 s, sem costura): pulso suave do brilho do "Z2" + reflexo de luz que percorre a linha.
O ultimo frame da intro == estado do frame 0 do ciclo == logo estatico (gerar_logo.py, variante B).
"""
import importlib.util, io, math, multiprocessing as mp, os, struct, sys, zipfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGO_DIR = os.path.join(ROOT, "07-Logo")
OUT_ZIP = os.path.join(HERE, "bootanimation-a95xz2-v2.zip")
OUT_GIF = os.path.join(LOGO_DIR, "animacao-preview.gif")
OUT_SHEET = os.path.join(LOGO_DIR, "animacao-frames.png")
TARGET = 27972528
DT = (2026, 1, 1, 0, 0, 0)

W, H = 1920, 1080
S = W / 1280.0
FPS = 18   # 20 fps (100 frames) excedia o tamanho em ~1 MB
INTRO_S, LOOP_S = 3.0, 2.0
N0, N1 = int(round(INTRO_S * FPS)), int(round(LOOP_S * FPS))
SUB1, SUB2 = "ANDROID 10  ·  2026", "by Ivo Barbosa"

spec = importlib.util.spec_from_file_location("gerar_logo", os.path.join(LOGO_DIR, "gerar_logo.py"))
GL = importlib.util.module_from_spec(spec); spec.loader.exec_module(GL)
hexc, lerp = GL.hexc, GL.lerp
CYAN, VIOLET, WHITE = hexc("#00C2FF"), hexc("#7B61FF"), hexc("#F2F5F8")
MID = lerp(CYAN, VIOLET, 0.5)
C_SUB1, C_SUB2 = hexc("#8C97A8"), hexc("#8C97A8")
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


# ------------------------------------------------------------------ easing / timeline
def clamp(v, a=0.0, b=1.0): return a if v < a else b if v > b else v
def ph(t, a, b): return clamp((t - a) / (b - a))
def smooth(u): return u * u * (3 - 2 * u)
def out3(u): return 1 - (1 - u) ** 3


def intro_state(t):
    u = ph(t, 0.85, 2.3)
    bell = math.sin(math.pi * u ** 0.55) ** 2           # sobe depressa, desce devagar; 0 nas pontas
    return dict(bg=smooth(ph(t, 0.0, 0.5)),
                aA=smooth(ph(t, 0.25, 1.0)), aOff=36 * (1 - out3(ph(t, 0.25, 1.05))),
                zA=smooth(ph(t, 0.75, 1.35)),
                gI=smooth(ph(t, 0.75, 1.2)) + 1.8 * bell, halo=0.55 * bell,
                hw=None if t >= 2.05 else (LW / 2 + 24) * out3(ph(t, 1.35, 2.05)),
                spark=math.sin(math.pi * ph(t, 1.35, 2.15)),
                s1A=smooth(ph(t, 1.9, 2.5)), s1Off=14 * (1 - out3(ph(t, 1.9, 2.6))),
                s2A=smooth(ph(t, 2.2, 2.8)), s2Off=10 * (1 - out3(ph(t, 2.2, 2.85))),
                sweepX=0.0, sweepI=0.0)


def loop_state(p):
    pulse = 0.5 - 0.5 * math.cos(2 * math.pi * p)
    u = ph(p, 0.10, 0.75)
    return dict(bg=1.0, aA=1.0, aOff=0.0, zA=1.0, gI=1.0 + 0.7 * pulse, halo=0.30 * pulse,
                hw=None, spark=0.0, s1A=1.0, s1Off=0.0, s2A=1.0, s2Off=0.0,
                sweepX=LX0 - 90 + u * (LW + 180), sweepI=math.sin(math.pi * u) if 0 < u < 1 else 0.0)


# ------------------------------------------------------------------ layout (igual a gerar_logo.build)
def setup():
    global LW, LX0, LY, NL, BX0, BX1, BY0, BY1, BW, BG, BGROW, GLOW, HALO, COV, ZCOL, LCOL, LFADE, DV, LCX
    bold = GL.find_font(["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"])
    light = GL.find_font(["segoeuisl.ttf", "segoeuil.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    if not bold or not light:
        sys.exit("Fonte TrueType nao encontrada")
    print("Fontes:", bold, "|", light)
    fb, fl = GL.Font(bold), GL.Font(light)
    tp, bbox, shift = GL.text_polys, GL.bbox, GL.shift

    size = 170 * S
    p1, w1 = tp(fb, "A95X", size, 0, 0, tracking=2 * S)
    gap = size * 0.22
    p2, _ = tp(fb, "Z2", size, 0, 0, tracking=2 * S)
    allp = p1 + shift(p2, w1 + gap, 0)
    x0, y0, x1, y1 = bbox(allp)
    tw, th = x1 - x0, y1 - y0
    ox = (W - tw) / 2 - x0
    oy = (H / 2 - 40 * S) - (y0 + th / 2)
    p1s, p2s = shift(p1, ox, oy), shift(p2, ox + w1 + gap, oy)
    zx0, _, zx1, _ = bbox(p2s)
    gx, gy = (zx0 + zx1) / 2, (y0 + y1) / 2 + oy
    grx, gry = 260 * S, 150 * S

    LY = int(oy + y1 + 38 * S); LW = int(round(420 * S)); NL = int(round(4 * S))
    LX0 = int(W / 2 - LW / 2); LCX = LX0 + LW / 2

    sp, _ = tp(fl, SUB1, 30 * S, 0, 0, tracking=7 * S)
    sx0, sy0, sx1, sy1 = bbox(sp)
    sps = shift(sp, (W - (sx1 - sx0)) / 2 - sx0, LY + 44 * S - sy0)
    sub_bottom = LY + 44 * S + (sy1 - sy0)
    # igual ao logotipo (21/11/2026): Segoe UI normal, 24 px, mesma cor do subtitulo
    fr = GL.Font(GL.find_font(["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]))
    sp2, _ = tp(fr, SUB2, 24 * S, 0, 0, tracking=2.5 * S)
    tx0, ty0, tx1, ty1 = bbox(sp2)
    sps2 = shift(sp2, (W - (tx1 - tx0)) / 2 - tx0, sub_bottom + 20 * S - ty0)

    # caixa dinamica (tudo o que muda); fora dela o frame e so fundo
    BX0 = int(min(gx - grx, bbox(p1s)[0], LX0 - 120)) - 4
    BX1 = int(max(gx + grx, LX0 + LW + 120)) + 4
    BY0 = int(min(gy - gry, y0 + oy)) - 4
    BY1 = int(max(gy + gry, bbox(sps2)[3] + 12, LY + NL + 20)) + 4
    BX0, BY0, BX1, BY1 = max(0, BX0), max(0, BY0), min(W, BX1), min(H, BY1)
    BW = BX1 - BX0
    print("caixa dinamica", BX0, BY0, BX1, BY1)

    # fundo radial (float) + linhas ja arredondadas (com dither) a 100%
    c_in, c_out = hexc("#16202C"), hexc("#06080B")
    cx, cy = W / 2, H / 2 - 20 * S
    rmax = math.hypot(W / 2, H / 2)
    DV = [[(BAYER[y][x & 3] + 0.5) / 16 - 0.5 + 0.5 for x in range(W)] for y in range(4)]
    BG, BGROW = [], []
    for y in range(H):
        row = []
        for x in range(W):
            t = min(1.0, math.hypot((x - cx) * 0.85, (y - cy) * 1.25) / rmax)
            t = t * t * (3 - 2 * t)
            row.append(lerp(c_in, c_out, t))
        BG.append(row)
        dv = DV[y & 3]
        BGROW.append(bytes(min(255, int(c[i] + dv[x])) for x, c in enumerate(row) for i in range(3)))

    def crop(cov):
        return [[min(1.0, v) for v in cov[y][BX0:BX1]] for y in range(BY0, BY1)]

    COV = {"A": crop(GL.raster(p1s, W, H)), "Z": crop(GL.raster(p2s, W, H)),
           "S1": crop(GL.raster(sps, W, H)), "S2": crop(GL.raster(sps2, W, H))}
    GLOW = []
    for y in range(BY0, BY1):
        r = []
        for x in range(BX0, BX1):
            dd = math.hypot((x - gx) / grx, (y - gy) / gry)
            r.append((1 - dd) ** 2 * 0.10 if dd < 1 else 0.0)
        GLOW.append(r)
    ZCOL = [lerp(CYAN, VIOLET, clamp((x - zx0) / (zx1 - zx0))) for x in range(BX0, BX1)]
    LCOL = [lerp(CYAN, VIOLET, clamp((x - LX0) / LW)) for x in range(BX0, BX1)]
    LFADE = [(min(1.0, ((x - LX0) / LW) / 0.18, (1 - (x - LX0) / LW) / 0.18) if LX0 <= x < LX0 + LW else 0.0)
             for x in range(BX0, BX1)]
    HALO = blur(COV["Z"], int(16 * S), 3)
    m = max(max(r) for r in HALO) or 1.0
    HALO = [[v / m for v in r] for r in HALO]


def blur(img, rad, passes):
    """Box blur separavel (n passagens ~ gaussiano)."""
    h, w = len(img), len(img[0])
    a = [r[:] for r in img]
    k = 2 * rad + 1
    for _ in range(passes):
        for y in range(h):                       # horizontal
            r = a[y]; acc = [0.0] * (w + 1)
            for x in range(w): acc[x + 1] = acc[x] + r[x]
            a[y] = [(acc[min(w, x + rad + 1)] - acc[max(0, x - rad)]) / k for x in range(w)]
        for x in range(w):                       # vertical
            col = [a[y][x] for y in range(h)]; acc = [0.0] * (h + 1)
            for y in range(h): acc[y + 1] = acc[y] + col[y]
            for y in range(h): a[y][x] = (acc[min(h, y + rad + 1)] - acc[max(0, y - rad)]) / k
    return a


# ------------------------------------------------------------------ render de um frame
def cov_row(layer, ry, off, alpha):
    """Linha ry (relativa a caixa) da camada deslocada 'off' px para baixo, x alpha."""
    L = COV[layer]
    if alpha <= 0: return None
    f = ry - off
    i = math.floor(f); w = f - i
    a = L[i] if 0 <= i < len(L) else None
    b = L[i + 1] if 0 <= i + 1 < len(L) else None
    if a is None and b is None: return None
    if w < 1e-6 or b is None:
        return [v * alpha * (1 - w) for v in a] if a is not None else None
    if a is None: return [v * alpha * w for v in b]
    return [(u * (1 - w) + v * w) * alpha for u, v in zip(a, b)]


def scaled_row(y, k, x0=0, x1=W):
    bg, dv = BG[y], DV[y & 3]
    return bytes(min(255, int(bg[x][i] * k + dv[x])) for x in range(x0, x1) for i in range(3))


def render(st):
    k = st["bg"]
    rows = []
    for y in range(H):
        if not BY0 <= y < BY1:
            rows.append(BGROW[y] if k >= 1 else scaled_row(y, k)); continue
        ry = y - BY0
        if k >= 1:
            left, right = BGROW[y][:BX0 * 3], BGROW[y][BX1 * 3:]
        else:
            left, right = scaled_row(y, k, 0, BX0), scaled_row(y, k, BX1, W)
        rows.append(left + box_row(st, y, ry) + right)
    return rows


def box_row(st, y, ry):
    k = st["bg"]
    bg = BG[y][BX0:BX1]; dv = DV[y & 3][BX0:BX1]
    glow, halo = GLOW[ry], HALO[ry]
    gI, hI = st["gI"], st["halo"]
    cA = cov_row("A", ry, st["aOff"], st["aA"])
    cZ = cov_row("Z", ry, 0.0, st["zA"])
    c1 = cov_row("S1", ry, st["s1Off"], st["s1A"])
    c2 = cov_row("S2", ry, st["s2Off"], st["s2A"])
    line = line_row(st, y)
    out = bytearray(BW * 3)
    mr, mg, mb = MID
    wr, wg, wb = WHITE
    for i in range(BW):
        r, g, b = bg[i]
        if k < 1: r *= k; g *= k; b *= k
        a = glow[i] * gI
        if a > 0: r += (mr - r) * a; g += (mg - g) * a; b += (mb - b) * a
        if hI > 0:
            a = halo[i] * hI
            if a > 0.001:
                c = ZCOL[i]; r += (c[0] - r) * a; g += (c[1] - g) * a; b += (c[2] - b) * a
        if cA:
            a = cA[i]
            if a > 0: r += (wr - r) * a; g += (wg - g) * a; b += (wb - b) * a
        if cZ:
            a = cZ[i]
            if a > 0: c = ZCOL[i]; r += (c[0] - r) * a; g += (c[1] - g) * a; b += (c[2] - b) * a
        if line:
            a, c = line[i]
            if a > 0: r += (c[0] - r) * a; g += (c[1] - g) * a; b += (c[2] - b) * a
        for cv, col in ((c1, C_SUB1), (c2, C_SUB2)):
            if cv:
                a = cv[i]
                if a > 0: r += (col[0] - r) * a; g += (col[1] - g) * a; b += (col[2] - b) * a
        d = dv[i]; j = 3 * i
        out[j] = min(255, max(0, int(r + d)))
        out[j + 1] = min(255, max(0, int(g + d)))
        out[j + 2] = min(255, max(0, int(b + d)))
    return bytes(out)


def line_row(st, y):
    """Lista (alpha, cor) por pixel da caixa para a linha de destaque + faiscas/reflexo; None se vazio."""
    dy = y - LY
    on_line = 0 <= dy < NL
    vd = 0 if on_line else (dy if dy < 0 else dy - NL + 1)       # distancia vertical a linha
    if abs(vd) > 22: return None
    base = (0.35 if dy in (0, NL - 1) else 1.0) if on_line else 0.0
    hw, spark, sx, sI = st["hw"], st["spark"], st["sweepX"], st["sweepI"]
    if base == 0 and spark <= 0.01 and sI <= 0.01: return None
    gv = math.exp(-(vd / 4.5) ** 2)
    res = []
    for i in range(BW):
        x = BX0 + i + 0.5
        lc = LCOL[i]
        a = base * LFADE[i]
        if hw is not None:
            d = abs(x - LCX)
            a *= clamp((hw - d) / 6 + 0.5) * clamp(hw / 8)
            if spark > 0.01:                                   # faiscas nas pontas a desenhar
                s = spark * math.exp(-((d - hw) / 16) ** 2) * gv
                if s > 0.002:
                    c = lerp(lc, WHITE, 0.65 * min(1, s * 1.5))
                    a2 = min(1.0, s * 0.9)
                    a, lc = a + a2 * (1 - a), lerp(c, lc, a / (a + a2)) if a + a2 > 0 else c
        if sI > 0.01:                                          # reflexo de luz ao longo da linha
            s = sI * math.exp(-((x - sx) / 46) ** 2) * max(LFADE[i], 0.25 if LX0 - 40 < x < LX0 + LW + 40 else 0)
            if s > 0.002:
                if on_line:
                    lc = lerp(lc, WHITE, 0.75 * s); a = a + (1 - a) * 0.6 * s
                else:
                    a2 = 0.45 * s * gv; c = lerp(lc, WHITE, 0.5)
                    if a2 > a: lc = c
                    a = a + a2 * (1 - a)
        res.append((a, lc))
    return res


# ------------------------------------------------------------------ PNG / downscale
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def png_rgb(rows, w, h):
    raw = b"".join(b"\x01" + sub_filter(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def sub_filter(r):
    """Filtro PNG 'Sub' (tipo 1): bom para gradientes com dither."""
    a = r[:3] + bytes((r[i] - r[i - 3]) & 255 for i in range(3, len(r)))
    return a


def downscale(rows, f):
    """Media f x f (1920x1080 -> 1920/f x 1080/f)."""
    out = []
    n = f * f
    for y in range(0, len(rows), f):
        s = list(rows[y])
        for k in range(1, f):
            s = list(map(int.__add__, s, rows[y + k]))
        cols = []
        for c in range(3):
            acc = s[c::3 * f]
            for k in range(1, f):
                acc = list(map(int.__add__, acc, s[3 * k + c::3 * f]))
            cols.append(acc)
        r = bytearray(len(cols[0]) * 3)
        for c in range(3):
            r[c::3] = bytes((v + n // 2) // n for v in cols[c])
        out.append(bytes(r))
    return out


def work(job):
    idx, st, want_sheet = job
    rows = render(st)
    return idx, png_rgb(rows, W, H), downscale(rows, 3), (downscale(rows, 4) if want_sheet else None)


# ------------------------------------------------------------------ GIF (LZW proprio)
def lzw(indices, min_code=8):
    clear, eoi = 1 << min_code, (1 << min_code) + 1
    out = bytearray(); bitbuf = 0; nbits = 0
    def emit(code, size):
        nonlocal bitbuf, nbits
        bitbuf |= code << nbits; nbits += size
        while nbits >= 8:
            out.append(bitbuf & 255); bitbuf >>= 8; nbits -= 8
    size = min_code + 1
    table = {}; nxt = eoi + 1
    emit(clear, size)
    prefix = indices[0]
    for c in indices[1:]:
        key = (prefix << 8) | c
        v = table.get(key)
        if v is not None:
            prefix = v; continue
        emit(prefix, size)
        if nxt < 4096:
            table[key] = nxt; nxt += 1
            if nxt > (1 << size) and size < 12: size += 1
        else:
            emit(clear, size); table = {}; nxt = eoi + 1; size = min_code + 1
        prefix = c
    emit(prefix, size); emit(eoi, size)
    if nbits: out.append(bitbuf & 255)
    return bytes(out)


def write_gif(path, frames, w, h, delay_cs):
    """frames: lista de listas de linhas RGB (bytes). Paleta global 256 (median cut) + frames por diferenca."""
    counts = {}
    for fr in frames[::3] + [frames[-1]]:
        for r in fr:
            for j in range(0, len(r), 3):
                key = (r[j] & 0xFC, r[j + 1] & 0xFC, r[j + 2] & 0xFC)
                counts[key] = counts.get(key, 0) + 1
    pal = GL.median_cut(counts, 256)
    cache = {}
    def idx(c):
        i = cache.get(c)
        if i is None:
            i = min(range(256), key=lambda k: (pal[k][0] - c[0]) ** 2 * 3 + (pal[k][1] - c[1]) ** 2 * 4 + (pal[k][2] - c[2]) ** 2 * 2)
            cache[c] = i
        return i
    out = bytearray(b"GIF89a" + struct.pack("<HHBBB", w, h, 0xF7, 0, 0))
    out += b"".join(bytes(c) for c in pal)
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    prev = None
    for fr in frames:
        ind = [bytes(idx((r[j], r[j + 1], r[j + 2])) for j in range(0, len(r), 3)) for r in fr]
        if prev is None:
            x0, y0, x1, y1 = 0, 0, w, h
        else:
            ys = [y for y in range(h) if ind[y] != prev[y]]
            if not ys:
                x0, y0, x1, y1 = 0, 0, 1, 1
            else:
                y0, y1 = ys[0], ys[-1] + 1
                x0, x1 = w, 0
                for y in ys:
                    a, b = ind[y], prev[y]
                    l = next(i for i in range(w) if a[i] != b[i])
                    rr = next(i for i in range(w - 1, -1, -1) if a[i] != b[i])
                    x0, x1 = min(x0, l), max(x1, rr + 1)
        prev = ind
        data = b"".join(ind[y][x0:x1] for y in range(y0, y1))
        out += b"\x21\xF9\x04" + struct.pack("<BHBB", 0x04, delay_cs, 0, 0)      # disposal: deixar
        out += b"\x2C" + struct.pack("<HHHHB", x0, y0, x1 - x0, y1 - y0, 0)
        enc = lzw(data); out.append(8)
        for i in range(0, len(enc), 255):
            blk = enc[i:i + 255]; out.append(len(blk)); out += blk
        out.append(0)
    out.append(0x3B)
    open(path, "wb").write(out)
    return len(out)


# ------------------------------------------------------------------ zip
def build_zip(entries, pad):
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_STORED) as z:
        for n, d in entries + ([("pad.bin", b"\0" * pad)] if pad is not None else []):
            zi = zipfile.ZipInfo(n, DT); zi.compress_type = zipfile.ZIP_STORED; zi.external_attr = 0o644 << 16
            z.writestr(zi, d)
    return bio.getvalue()


def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else TARGET
    setup()
    states = [intro_state(k / FPS) for k in range(N0)] + [loop_state(k / N1) for k in range(N1)]
    # frames-chave para a folha de contacto (tempo em s; ciclo depois de 3.0)
    key_t = [0.25, 0.6, 1.0, 1.25, 1.6, 2.0, 2.9, 3.0 + 0.85]
    key_idx = [min(len(states) - 1, int(round(t * FPS))) for t in key_t]
    jobs = [(i, st, i in key_idx) for i, st in enumerate(states)]
    res = [None] * len(states)
    with mp.get_context("fork").Pool(os.cpu_count()) as pool:
        for n, r in enumerate(pool.imap_unordered(work, jobs)):
            res[r[0]] = r
            if n % 10 == 0: print("  frames %d/%d" % (n + 1, len(states)), flush=True)

    entries = [("desc.txt", b"%d %d %d\np 1 0 part0\np 0 0 part1\n" % (W, H, FPS))]
    for i in range(N0): entries.append(("part0/%03d.png" % i, res[i][1]))
    for i in range(N1): entries.append(("part1/%03d.png" % i, res[N0 + i][1]))
    base = len(build_zip(entries, 0))
    if base > target:
        sys.exit("ERRO: conteudo %d > alvo %d (reduzir FPS ou frames)" % (base, target))
    data = build_zip(entries, target - base)
    assert len(data) == target
    open(OUT_ZIP, "wb").write(data)
    print("zip", OUT_ZIP, len(data), "conteudo util", base)

    # folha de contacto 4x2 de 480x270 com margens
    sw, sh, gap = 480, 270, 12
    SW, SH = 4 * sw + 5 * gap, 2 * sh + 3 * gap
    sheet = [bytearray(b"\x10\x13\x18" * SW) for _ in range(SH)]
    for n, i in enumerate(key_idx):
        cx, cy = gap + (n % 4) * (sw + gap), gap + (n // 4) * (sh + gap)
        for y, r in enumerate(res[i][3]):
            sheet[cy + y][cx * 3:(cx + sw) * 3] = r
    open(OUT_SHEET, "wb").write(png_rgb([bytes(r) for r in sheet], SW, SH))
    print("folha", OUT_SHEET, "frames", key_idx, "tempos", key_t)

    gif_frames = [res[i][2] for i in range(N0)] + [res[N0 + i][2] for i in range(N1)] * 3
    n = write_gif(OUT_GIF, gif_frames, 640, 360, int(round(100 / FPS)))
    print("gif", OUT_GIF, n, "bytes", len(gif_frames), "frames")


if __name__ == "__main__":
    main()
