"""Minimal read-only ext4 reader (extents + linear dirs).
Usage: python3 -I ext4r.py <img> ls <path> | cat <path> | find <substr> | grep <bytes-regex> <dir>
"""
import struct, sys, re

class Ext4:
    def __init__(self, path):
        self.f = open(path, 'rb'); self.f.seek(1024); sb = self.f.read(1024)
        self.bs = 1024 << struct.unpack_from('<I', sb, 24)[0]
        self.ipg = struct.unpack_from('<I', sb, 40)[0]
        self.isz = struct.unpack_from('<H', sb, 88)[0]
        feat_incompat = struct.unpack_from('<I', sb, 96)[0]
        self.desc_sz = struct.unpack_from('<H', sb, 254)[0] if feat_incompat & 0x80 else 32
        if self.desc_sz < 32: self.desc_sz = 32
        self.gdt = (1 if self.bs > 1024 else 2) * self.bs
    def rd(self, off, n): self.f.seek(off); return self.f.read(n)
    def inode(self, ino):
        g, idx = divmod(ino - 1, self.ipg)
        d = self.rd(self.gdt + g * self.desc_sz, self.desc_sz)
        itab = struct.unpack_from('<I', d, 8)[0]
        if self.desc_sz >= 64: itab |= struct.unpack_from('<I', d, 0x28)[0] << 32
        return self.rd(itab * self.bs + idx * self.isz, self.isz)
    def extents(self, node):
        magic, ent, mx, depth = struct.unpack_from('<HHHH', node, 0)
        assert magic == 0xF30A
        out = []
        for k in range(ent):
            e = node[12 + 12 * k: 24 + 12 * k]
            if depth == 0:
                lblk, ln, hi, lo = struct.unpack('<IHHI', e)
                if ln > 32768: ln -= 32768
                out.append((lblk, ln, (hi << 32) | lo))
            else:
                lblk, lo, hi = struct.unpack('<IIH', e[:10])
                out += self.extents(self.rd(((hi << 32) | lo) * self.bs, self.bs))
        return out
    def data(self, ino):
        i = self.inode(ino); mode = struct.unpack_from('<H', i, 0)[0]
        size = struct.unpack_from('<I', i, 4)[0] | (struct.unpack_from('<I', i, 108)[0] << 32)
        flags = struct.unpack_from('<I', i, 32)[0]
        if (mode & 0xF000) == 0xA000 and size < 60: return i[40:40 + size]
        if flags & 0x10000000: return i[40:40 + size]  # inline data
        assert flags & 0x80000, 'no extents'
        buf = bytearray()
        for lblk, ln, pblk in sorted(self.extents(i[40:100])):
            if len(buf) < lblk * self.bs: buf += b'\0' * (lblk * self.bs - len(buf))
            buf += self.rd(pblk * self.bs, ln * self.bs)
        return bytes(buf[:size])
    def mode(self, ino): return struct.unpack_from('<H', self.inode(ino), 0)[0]
    def listdir(self, ino):
        d = self.data(ino); i = 0; out = []
        while i < len(d):
            ino2, rl, nl, ft = struct.unpack_from('<IHBB', d, i)
            if rl == 0: break
            if ino2: out.append((d[i + 8:i + 8 + nl].decode(errors='replace'), ino2, ft))
            i += rl
        return out
    def lookup(self, path):
        ino = 2
        for part in [p for p in path.split('/') if p]:
            m = dict((n, x) for n, x, _ in self.listdir(ino))
            ino = m[part]
        return ino
    def walk(self, ino=2, prefix=''):
        for n, x, ft in self.listdir(ino):
            if n in ('.', '..'): continue
            p = prefix + '/' + n; yield p, x, ft
            if ft == 2: yield from self.walk(x, p)

def main():
    fs = Ext4(sys.argv[1]); cmd = sys.argv[2]
    if cmd == 'ls':
        for n, x, ft in fs.listdir(fs.lookup(sys.argv[3])): print(ft, n)
    elif cmd == 'cat': sys.stdout.buffer.write(fs.data(fs.lookup(sys.argv[3])))
    elif cmd == 'find':
        for p, x, ft in fs.walk():
            if re.search(sys.argv[3], p, re.I): print(p)
    elif cmd == 'grep':
        rx = re.compile(sys.argv[3].encode(), re.I); base = sys.argv[4] if len(sys.argv) > 4 else '/'
        for p, x, ft in fs.walk(fs.lookup(base), base.rstrip('/')):
            if ft != 1: continue
            try: d = fs.data(x)
            except Exception: continue
            if rx.search(d): print(p)

if __name__ == '__main__':
    main()
