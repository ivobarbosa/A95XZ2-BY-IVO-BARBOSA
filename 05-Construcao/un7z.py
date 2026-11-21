"""Minimal 7z extractor (LZMA/LZMA2, optional BCJ none) using only the stdlib.
Usage: python3 -I un7z.py <archive.7z> <out_dir> [--list]
"""
import lzma, struct, sys, os, zlib

def rd_num(b, i):
    first = b[i]; i += 1
    mask = 0x80; val = 0
    for n in range(8):
        if first & mask == 0:
            hi = first & (mask - 1)
            return val | (hi << (8 * n)), i
        val |= b[i] << (8 * n); i += 1
        mask >>= 1
    return val, i

def rd_bits(b, i, n):
    all_def = b[i]; i += 1
    if all_def: return [True] * n, i
    out = []; byte = 0; m = 0
    for _ in range(n):
        if m == 0: byte = b[i]; i += 1; m = 0x80
        out.append(bool(byte & m)); m >>= 1
    return out, i

def parse_pack_info(b, i):
    pack_pos, i = rd_num(b, i); n, i = rd_num(b, i)
    sizes = []
    while True:
        t = b[i]; i += 1
        if t == 0: break
        if t == 9:
            for _ in range(n):
                s, i = rd_num(b, i); sizes.append(s)
        elif t == 10:
            d, i = rd_bits(b, i, n); i += 4 * sum(d)
        else: raise ValueError('pack prop %d' % t)
    return pack_pos, sizes, i

def parse_folder(b, i):
    nc, i = rd_num(b, i); coders = []
    for _ in range(nc):
        flag = b[i]; i += 1
        cid = b[i:i + (flag & 0xF)]; i += flag & 0xF
        nin = nout = 1
        if flag & 0x10:
            nin, i = rd_num(b, i); nout, i = rd_num(b, i)
        props = b''
        if flag & 0x20:
            ps, i = rd_num(b, i); props = b[i:i + ps]; i += ps
        coders.append((cid, props, nin, nout))
    tot_out = sum(c[3] for c in coders); tot_in = sum(c[2] for c in coders)
    bonds = []
    for _ in range(tot_out - 1):
        a, i = rd_num(b, i); c, i = rd_num(b, i); bonds.append((a, c))
    npacked = tot_in - len(bonds)
    if npacked > 1:
        for _ in range(npacked): _, i = rd_num(b, i)
    return {'coders': coders, 'bonds': bonds}, i

def parse_unpack_info(b, i):
    assert b[i] == 0x0B; i += 1
    nf, i = rd_num(b, i); assert b[i] == 0; i += 1
    folders = []
    for _ in range(nf):
        f, i = parse_folder(b, i); folders.append(f)
    assert b[i] == 0x0C; i += 1
    for f in folders:
        f['unpack_sizes'] = []
        for _ in range(sum(c[3] for c in f['coders'])):
            s, i = rd_num(b, i); f['unpack_sizes'].append(s)
    while True:
        t = b[i]; i += 1
        if t == 0: break
        if t == 0x0A:
            d, i = rd_bits(b, i, nf)
            for f, has in zip(folders, d):
                if has: f['crc'] = struct.unpack_from('<I', b, i)[0]; i += 4
        else: raise ValueError('unpack prop %d' % t)
    return folders, i

def parse_substreams(b, i, folders):
    nums = [1] * len(folders); sizes = []
    t = b[i]; i += 1
    if t == 0x0D:
        for k in range(len(folders)): nums[k], i = rd_num(b, i)
        t = b[i]; i += 1
    if t == 0x09:
        for k, f in enumerate(folders):
            tot = f['unpack_sizes'][-1]; acc = 0
            for _ in range(nums[k] - 1):
                s, i = rd_num(b, i); sizes.append(s); acc += s
            if nums[k]: sizes.append(tot - acc)
        t = b[i]; i += 1
    else:
        for k, f in enumerate(folders):
            if nums[k] == 1: sizes.append(f['unpack_sizes'][-1])
    while t != 0:
        if t == 0x0A:
            n = sum(nums); d, i = rd_bits(b, i, n); i += 4 * sum(d)
        t = b[i]; i += 1
    return nums, sizes, i

def parse_streams(b, i):
    pack_pos, psizes, folders, nums, ssizes = 0, [], [], None, None
    while True:
        t = b[i]; i += 1
        if t == 0: break
        if t == 0x06: pack_pos, psizes, i = parse_pack_info(b, i)
        elif t == 0x07: folders, i = parse_unpack_info(b, i)
        elif t == 0x08: nums, ssizes, i = parse_substreams(b, i, folders)
        else: raise ValueError('streams prop %d' % t)
    if nums is None:
        nums = [1] * len(folders); ssizes = [f['unpack_sizes'][-1] for f in folders]
    return {'pack_pos': pack_pos, 'pack_sizes': psizes, 'folders': folders, 'nums': nums, 'sizes': ssizes}, i

def filters_for(folder):
    cs = folder['coders']
    if len(cs) != 1: raise ValueError('unsupported coder chain %r' % [c[0].hex() for c in cs])
    cid, props = cs[0][0], cs[0][1]
    if cid == b'\x21':
        d = props[0]; dsz = (2 | (d & 1)) << (d // 2 + 11)
        return [{'id': lzma.FILTER_LZMA2, 'dict_size': dsz}]
    if cid == b'\x03\x01\x01':
        p = props[0]; lc = p % 9; p //= 9; lp = p % 5; pb = p // 5
        return [{'id': lzma.FILTER_LZMA1, 'lc': lc, 'lp': lp, 'pb': pb,
                 'dict_size': struct.unpack('<I', props[1:5])[0]}]
    if cid == b'\x00': return None
    raise ValueError('unsupported coder %s' % cid.hex())

def decode_folder_stream(f, fh, offset, packsize, out_size, sink):
    flt = filters_for(f)
    fh.seek(offset); left = packsize; produced = 0
    dec = None if flt is None else lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=flt)
    crc = 0
    while left > 0 and produced < out_size:
        chunk = fh.read(min(1 << 22, left)); left -= len(chunk)
        data = chunk if dec is None else dec.decompress(chunk)
        data = data[:out_size - produced]; produced += len(data)
        crc = zlib.crc32(data, crc); sink(data)
    if dec is not None:
        while produced < out_size and not dec.eof:
            data = dec.decompress(b'', 1 << 22)
            if not data: break
            data = data[:out_size - produced]; produced += len(data)
            crc = zlib.crc32(data, crc); sink(data)
    return produced, crc

def main():
    path, out = sys.argv[1], sys.argv[2]; listonly = '--list' in sys.argv
    fh = open(path, 'rb'); sig = fh.read(32)
    assert sig[:6] == b"7z\xbc\xaf'\x1c", 'not 7z'
    nh_off, nh_size = struct.unpack_from('<QQ', sig, 12)
    fh.seek(32 + nh_off); hdr = fh.read(nh_size)
    if hdr[0] == 0x17:
        s, _ = parse_streams(hdr, 1); f = s['folders'][0]
        buf = []
        decode_folder_stream(f, fh, 32 + s['pack_pos'], s['pack_sizes'][0], f['unpack_sizes'][-1], buf.append)
        hdr = b''.join(buf)
    assert hdr[0] == 0x01, 'header type %x' % hdr[0]
    i = 1; streams = None; names = []; empty = []
    while True:
        t = hdr[i]; i += 1
        if t == 0: break
        if t == 0x04: streams, i = parse_streams(hdr, i)
        elif t == 0x05:
            nfiles, i = rd_num(hdr, i)
            while True:
                pt = hdr[i]; i += 1
                if pt == 0: break
                sz, i = rd_num(hdr, i); body = hdr[i:i + sz]; i += sz
                if pt == 0x11:
                    names = body[1:].decode('utf-16-le').split('\0')[:nfiles]
                elif pt == 0x0E:
                    empty, _ = rd_bits(b'\x00' + body if body[0] != 1 else body, 0, nfiles) if False else ([], 0)
                    bits = []; byte = 0; m = 0; j = 0
                    for _ in range(nfiles):
                        if m == 0: byte = body[j]; j += 1; m = 0x80
                        bits.append(bool(byte & m)); m >>= 1
                    empty = bits
        else: raise ValueError('header prop %d' % t)
    if not empty: empty = [False] * len(names)
    real = [n for n, e in zip(names, empty) if not e]
    sizes = streams['sizes']
    for n, s in zip(real, sizes): print('%14d  %s' % (s, n))
    if listonly: return
    os.makedirs(out, exist_ok=True)
    off = 32 + streams['pack_pos']; fi = 0
    for k, f in enumerate(streams['folders']):
        ps = streams['pack_sizes'][k]; n = streams['nums'][k]
        targets = real[fi:fi + n]; tsizes = sizes[fi:fi + n]; fi += n
        state = {'idx': 0, 'left': tsizes[0] if tsizes else 0, 'fp': None}
        def open_next():
            name = os.path.basename(targets[state['idx']].replace('\\', '/'))
            state['fp'] = open(os.path.join(out, name), 'wb'); print('->', name, flush=True)
        if targets: open_next()
        def sink(data):
            while data:
                take = data[:state['left']]; state['fp'].write(take)
                state['left'] -= len(take); data = data[len(take):]
                if state['left'] == 0:
                    state['fp'].close(); state['idx'] += 1
                    if state['idx'] < len(targets):
                        state['left'] = tsizes[state['idx']]; open_next()
        produced, crc = decode_folder_stream(f, fh, off, ps, f['unpack_sizes'][-1], sink)
        ok = ('crc' not in f) or (crc == f['crc'])
        print('folder %d: %d bytes, CRC %s' % (k, produced, 'OK' if ok else 'FALHOU'), flush=True)
        off += ps

if __name__ == '__main__':
    main()
