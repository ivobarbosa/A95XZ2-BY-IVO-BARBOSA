"""Gerador minimo de codigos QR (modo byte, nivel de correcao M, versoes 1-6), so com a biblioteca padrao.
Segue a norma ISO/IEC 18004 (mesma logica do gerador de referencia de Project Nayuki).
Uso: python3 -I mkqr.py <texto> <saida.png> [escala]
"""
import sys, zlib, struct

# versao -> (codewords de correcao por bloco, numero de blocos) para o nivel M
ECC_M = {1: (10, 1), 2: (16, 1), 3: (26, 1), 4: (18, 2), 5: (24, 2), 6: (16, 4)}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34]}


def raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        na = ver // 7 + 2
        r -= (25 * na - 10) * na - 55
        if ver >= 7: r -= 36
    return r


def data_codewords(ver):
    ec, nb = ECC_M[ver]
    return raw_modules(ver) // 8 - ec * nb


# ---- Reed-Solomon sobre GF(256), polinomio 0x11D
def gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def rs_divisor(degree):
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = gf_mul(res[j], root)
            if j + 1 < degree: res[j] ^= res[j + 1]
        root = gf_mul(root, 0x02)
    return res


def rs_remainder(data, divisor):
    res = [0] * len(divisor)
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i, coef in enumerate(divisor):
            res[i] ^= gf_mul(coef, factor)
    return res


def encode(text):
    data = text.encode('utf-8')
    for ver in range(1, 7):
        cap = data_codewords(ver) * 8
        need = 4 + 8 + 8 * len(data)          # modo + contador (8 bits ate v9) + dados
        if need <= cap: break
    else:
        raise ValueError('texto demasiado longo')
    bits = []
    def app(val, n):
        for i in range(n - 1, -1, -1): bits.append((val >> i) & 1)
    app(0b0100, 4); app(len(data), 8)
    for b in data: app(b, 8)
    app(0, min(4, cap - len(bits)))
    app(0, (-len(bits)) % 8)
    pad = 0xEC
    while len(bits) < cap:
        app(pad, 8); pad ^= 0xEC ^ 0x11
    dcw = [int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    # blocos + correcao, intercalados
    ec, nb = ECC_M[ver]
    raw = raw_modules(ver) // 8
    nshort = nb - raw % nb
    short_len = raw // nb
    div = rs_divisor(ec)
    blocks = []; k = 0
    for i in range(nb):
        dl = short_len - ec + (0 if i < nshort else 1)
        d = dcw[k:k + dl]; k += dl
        e = rs_remainder(d, div)
        if i < nshort: d = d + [None]
        blocks.append(d + e)
    final = []
    for i in range(len(blocks[0])):
        for j, b in enumerate(blocks):
            if i != short_len - ec or j >= nshort:
                if b[i] is not None: final.append(b[i])
    assert len(final) == raw
    return ver, final


def build(ver, cw, mask):
    n = ver * 4 + 17
    m = [[False] * n for _ in range(n)]
    f = [[False] * n for _ in range(n)]   # modulo de funcao (nao recebe dados)
    def setf(x, y, v): m[y][x] = v; f[y][x] = True
    for i in range(n):
        setf(6, i, i % 2 == 0); setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                d = max(abs(dx), abs(dy)); x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n: setf(x, y, d not in (2, 4))
    al = ALIGN[ver]
    for i in al:
        for j in al:
            if (i == 6 and j == 6) or (i == 6 and j == al[-1]) or (i == al[-1] and j == 6): continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(i + dx, j + dy, max(abs(dx), abs(dy)) != 1)
    def format_bits(msk):
        data = (0 << 3) | msk                 # nivel M = 00
        rem = data
        for _ in range(10): rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        return ((data << 10) | rem) ^ 0x5412
    def draw_format(msk):
        b = format_bits(msk)
        g = lambda i: (b >> i) & 1 == 1
        for i in range(6): setf(8, i, g(i))
        setf(8, 7, g(6)); setf(8, 8, g(7)); setf(7, 8, g(8))
        for i in range(9, 15): setf(14 - i, 8, g(i))
        for i in range(8): setf(n - 1 - i, 8, g(i))
        for i in range(8, 15): setf(8, n - 15 + i, g(i))
        setf(8, n - 8, True)                  # modulo escuro fixo
    draw_format(0)
    # dados em ziguezague
    i = 0; total = len(cw) * 8
    right = n - 1
    while right >= 1:
        if right == 6: right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = n - 1 - vert if upward else vert
                if not f[y][x] and i < total:
                    m[y][x] = (cw[i >> 3] >> (7 - (i & 7))) & 1 == 1
                    i += 1
        right -= 2
    assert i == total
    masks = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]
    for y in range(n):
        for x in range(n):
            if not f[y][x] and masks[mask](x, y): m[y][x] = not m[y][x]
    draw_format(mask)
    return m


def penalty(m):
    n = len(m); p = 0
    for rows in (m, [list(c) for c in zip(*m)]):
        for row in rows:
            run = 1
            for k in range(1, n):
                if row[k] == row[k - 1]:
                    run += 1
                else:
                    if run >= 5: p += run - 2
                    run = 1
            if run >= 5: p += run - 2
            s = ''.join('1' if v else '0' for v in row)
            p += 40 * (s.count('10111010000') + s.count('00001011101'))
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]: p += 3
    dark = sum(map(sum, m)); total = n * n
    p += (abs(dark * 20 - total * 10) + total - 1) // total * 10 - 10 if dark * 20 != total * 10 else 0
    return p


def png(m, path, scale, border=2, dark=(0x0B, 0x0F, 0x17), light=(255, 255, 255)):
    n = len(m); size = (n + 2 * border) * scale
    raw = bytearray()
    for py in range(size):
        raw.append(0)
        y = py // scale - border
        for px in range(size):
            x = px // scale - border
            on = 0 <= x < n and 0 <= y < n and m[y][x]
            raw += bytes(dark if on else light)
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    out = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)) \
        + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b'')
    open(path, 'wb').write(out)


if __name__ == '__main__':
    text, out = sys.argv[1], sys.argv[2]
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    ver, cw = encode(text)
    best = min(range(8), key=lambda k: penalty(build(ver, cw, k)))
    m = build(ver, cw, best)
    png(m, out, scale)
    print('versao %d, mascara %d, %dx%d modulos -> %s' % (ver, best, len(m), len(m), out))
