"""Constroi super-hybrid-v3.img a partir do super ORIGINAL HK1 (sparse), com patches in-place:
  - /system/bin/vfdsrv            -> vfdsrv-v3.sh (mesmo tamanho, padding '#   ...\\n')
  - /system/media/bootanimation.zip -> bootanimation-a95xz2-v2.zip (mesmo tamanho)
  - ro.product.{system,vendor,product,odm}.model=HK1 Max -> A95X Z2
  - vendor/build.prop: persist.sys.bootvideo.enable=true -> false (+ linha showtime vira comentario)
Usage: python3 -I build_v3.py <super_orig.img sparse> <super_orig.raw> <out.img> [--verify <workdir>]
"""
import struct, sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ext4r import Ext4
from superinfo import lp, unsparse

HERE = os.path.dirname(os.path.abspath(__file__))
BS = 4096

class PartExt4(Ext4):
    """ext4 dentro do super raw, no offset da particao."""
    def rd(self, off, n): self.f.seek(self.base + off); return self.f.read(n)

def _init(self, raw, base):
    self.base = base; self.f = open(raw, 'rb'); sb = self.rd(1024, 1024)
    self.bs = 1024 << struct.unpack_from('<I', sb, 24)[0]
    self.ipg = struct.unpack_from('<I', sb, 40)[0]; self.isz = struct.unpack_from('<H', sb, 88)[0]
    inc = struct.unpack_from('<I', sb, 96)[0]; self.ro_compat = struct.unpack_from('<I', sb, 100)[0]
    self.desc_sz = max(32, struct.unpack_from('<H', sb, 254)[0] if inc & 0x80 else 32)
    self.gdt = (1 if self.bs > 1024 else 2) * self.bs
PartExt4.__init__ = _init

def raw_extents(fs, ino):
    """Lista (offset_logico, offset_no_fs, comprimento) dos blocos do ficheiro."""
    i = fs.inode(ino); out = []
    for lblk, ln, pblk in sorted(fs.extents(i[40:100])):
        out.append((lblk * BS, pblk * BS, ln * BS))
    return out

def all_block_owners(fs):
    """Mapa bloco->inode para todos os ficheiros/dirs (deteta blocos partilhados)."""
    own = {}; seen = set()
    stack = [2]
    while stack:
        d = stack.pop()
        for n, x, ft in fs.listdir(d):
            if n in ('.', '..') or x in seen: continue
            seen.add(x)
            i = fs.inode(x); flags = struct.unpack_from('<I', i, 32)[0]
            if flags & 0x80000:
                for lblk, ln, pblk in fs.extents(i[40:100]):
                    for b in range(pblk, pblk + ln): own.setdefault(b, set()).add(x)
            if ft == 2: stack.append(x)
    return own

def model_patch(data, key):
    old = b'\n' + key + b'=HK1 Max\n'; new = b'\n' + key + b'=A95X Z2\n'
    assert data.count(old) == 1, (key, data.count(old))
    return data.replace(old, new)

def bootvideo_patch(data):
    old = b'persist.sys.bootvideo.enable=true\npersist.sys.bootvideo.showtime=-2\n'
    new = b'persist.sys.bootvideo.enable=false\n# bootvideo desativado (A95X Z2)\n'
    assert len(old) == len(new) and data.count(old) == 1
    return data.replace(old, new)

def vfd_payload(size):
    s = open(os.path.join(HERE, 'vfdsrv-v3.sh'), 'rb').read()
    assert s.startswith(b'#!/system/bin/sh\n') and b'\r' not in s and len(s) + 2 <= size
    return s + b'#' + b' ' * (size - len(s) - 2) + b'\n'

def plan(raw):
    parts = {n: e[0][2] * 512 for n, a, e in lp(raw)}
    for n, a, e in lp(raw): assert len(e) == 1, n
    zipnew = open(os.path.join(HERE, 'bootanimation-a95xz2-v2.zip'), 'rb').read()
    todo = {
        'system': [('/system/bin/vfdsrv', 'vfd'), ('/system/media/bootanimation.zip', 'zip'),
                   ('/system/build.prop', b'ro.product.system.model')],
        'vendor': [('/build.prop', b'ro.product.vendor.model'), ('/build.prop', 'bootvideo')],
        'product': [('/build.prop', b'ro.product.product.model')],
        'odm': [('/etc/build.prop', b'ro.product.odm.model')],
    }
    files = []  # (part, path, base, extents, old, new)
    for part, items in todo.items():
        fs = PartExt4(raw, parts[part])
        assert not fs.ro_compat & 0x4000, part + ' usa shared_blocks'
        cur = {}
        for path, kind in items:
            ino = fs.lookup(path)
            if path not in cur: cur[path] = (ino, fs.data(ino))
            ino, d = cur[path]
            if kind == 'vfd': assert d[:4] == b'\x7fELF'; nd = vfd_payload(len(d))
            elif kind == 'zip': assert len(zipnew) == len(d), (len(zipnew), len(d)); nd = zipnew
            elif kind == 'bootvideo': nd = bootvideo_patch(d)
            else: nd = model_patch(d, kind)
            assert len(nd) == len(d)
            cur[path] = (ino, nd)
        own = all_block_owners(fs)
        for path, (ino, nd) in cur.items():
            ext = raw_extents(fs, ino)
            for lo, po, ln in ext:
                for b in range(po // BS, (po + ln) // BS):
                    assert own.get(b) == {ino}, '%s:%s bloco %d partilhado com %s' % (part, path, b, own.get(b))
            files.append((part, path, parts[part], ext, fs.data(ino), nd))
    return files

class Sparse:
    def __init__(self, path):
        self.f = open(path, 'rb'); self.hdr = self.f.read(28)
        magic, maj, mnr, self.fhs, self.chs, bsz, self.tblk, tchunk, self.crc = struct.unpack('<IHHHHIIII', self.hdr)
        assert magic == 0xED26FF3A and bsz == BS and self.chs == 12
        self.chunks = []; pos = self.fhs; blk = 0   # (ini_raw, fim_raw, tipo, offset_dados, extra)
        for _ in range(tchunk):
            self.f.seek(pos); ct, _r, csz, tsz = struct.unpack('<HHII', self.f.read(self.chs))
            extra = self.f.read(4) if ct in (0xCAC2, 0xCAC4) else None
            self.chunks.append((blk * BS, (blk + csz) * BS, ct, pos + self.chs, extra)); pos += tsz; blk += csz
    def read(self, raw_off, n):
        buf = bytearray(n)
        for s, e, ct, fo, extra in self.chunks:
            if e <= raw_off or s >= raw_off + n or ct == 0xCAC4: continue
            a, b = max(s, raw_off), min(e, raw_off + n)
            if ct == 0xCAC1: self.f.seek(fo + a - s); buf[a - raw_off:b - raw_off] = self.f.read(b - a)
            elif ct == 0xCAC2: buf[a - raw_off:b - raw_off] = (extra * ((b - a) // 4 + 2))[(a - s) % 4:][:b - a]
        return bytes(buf)

def write_patched(sp, dst, patches):
    """Reescreve o sparse: chunks intactos copiados tal e qual; chunks FILL/DONT_CARE tocados
    sao divididos e os blocos tocados passam a RAW. Devolve n. de chunks."""
    touched = set()
    for off, d in patches:
        touched.update(range(off // BS, (off + len(d) + BS - 1) // BS))
    def apply(raw_s, buf):
        for off, d in patches:
            a, b = max(off, raw_s), min(off + len(d), raw_s + len(buf))
            if a < b: buf[a - raw_s:b - raw_s] = d[a - off:b - off]
    o = open(dst, 'wb'); o.write(sp.hdr); o.write(b'\0' * (sp.fhs - 28)); n = 0
    def emit(ct, nblk, payload):
        nonlocal n; o.write(struct.pack('<HHII', ct, 0, nblk, 12 + len(payload))); o.write(payload); n += 1
    for s, e, ct, fo, extra in sp.chunks:
        b0, b1 = s // BS, e // BS
        hit = any(b in touched for b in range(b0, b1)) if ct != 0xCAC4 else False
        if ct == 0xCAC1:
            o.write(struct.pack('<HHII', ct, 0, b1 - b0, 12 + e - s)); n += 1
            if hit:
                buf = bytearray(sp.read(s, e - s)); apply(s, buf); o.write(buf)
            else:
                sp.f.seek(fo); left = e - s
                while left: c = sp.f.read(min(left, 1 << 22)); o.write(c); left -= len(c)
        elif ct == 0xCAC4 or not hit:
            emit(ct, b1 - b0, extra or b'')
        else:  # FILL / DONT_CARE tocado: dividir em corridas
            runs = []; b = b0
            while b < b1:
                t = b in touched; c = b
                while c < b1 and (c in touched) == t: c += 1
                runs.append((t, b, c)); b = c
            for t, x, y in runs:
                if t:
                    buf = bytearray(sp.read(x * BS, (y - x) * BS)); apply(x * BS, buf); emit(0xCAC1, y - x, bytes(buf))
                else:
                    emit(ct, y - x, extra or b'')
    o.seek(20); o.write(struct.pack('<I', n)); o.close()
    return n

def segments(base, ext, data):
    for lo, po, ln in ext:
        yield base + po, data[lo:lo + ln]  # ultimo bloco: so os bytes do ficheiro (cauda do bloco intacta)

def main():
    src, raw, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    files = plan(raw)
    sp = Sparse(src)
    assert sp.crc == 0, 'imagem com CRC global'
    ranges = []; patches = []
    for part, path, base, ext, old, new in files:
        for off, chunk in segments(base, ext, old):
            assert sp.read(off, len(chunk)) == chunk, 'conteudo original nao bate: %s %s' % (part, path)
        for off, chunk in segments(base, ext, new):
            patches.append((off, chunk)); ranges.append((off, off + len(chunk)))
        print('patch %-8s %-34s %9d bytes  extents=%s  md5 %s -> %s' % (part, path, len(new),
              [(hex(base + po), ln // BS) for lo, po, ln in ext], hashlib.md5(old).hexdigest()[:8], hashlib.md5(new).hexdigest()[:8]))
    n = write_patched(sp, dst, patches)
    print('escrito', dst, os.path.getsize(dst), 'bytes,', n, 'chunks (original %d)' % len(sp.chunks))
    if '--verify' in sys.argv:
        work = sys.argv[sys.argv.index('--verify') + 1]; os.makedirs(work, exist_ok=True)
        nraw = os.path.join(work, 'super-v3.raw')
        if os.path.exists(nraw): os.remove(nraw)
        unsparse(dst, nraw)
        # 1) todas as diferencas dentro das zonas previstas
        a, b = open(raw, 'rb'), open(nraw, 'rb'); off = 0; ndiff = 0; outside = 0; M = 1 << 22
        while True:
            x, y = a.read(M), b.read(M)
            if not x and not y: break
            if x != y:
                for k in range(0, len(x), BS):
                    if x[k:k + BS] != y[k:k + BS]:
                        for j in range(BS):
                            if x[k + j] != y[k + j]:
                                ndiff += 1; p = off + k + j
                                if not any(s <= p < e for s, e in ranges): outside += 1
            off += len(x)
        print('verificacao: bytes diferentes=%d, fora das zonas previstas=%d, tamanho raw igual=%s' % (ndiff, outside, os.path.getsize(raw) == os.path.getsize(nraw)))
        assert outside == 0
        # 2) reler cada ficheiro alterado da imagem nova com ext4r e comparar
        for part, path, base, ext, old, new in files:
            got = PartExt4(nraw, base).data(PartExt4(nraw, base).lookup(path))
            print('  reler %-8s %-34s %s' % (part, path, 'OK' if got == new else 'FALHOU'))
            assert got == new
        os.remove(nraw)
        print('VERIFICACAO OK')

if __name__ == '__main__':
    main()
