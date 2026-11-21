"""Rockchip resource image (RSCE) parse/list/replace/rebuild. stdlib only.

Layout (block = 512 bytes):
  header  : "RSCE" | u16 rsce_version | u16 index_tbl_version | u8 header_size(blocks)
            | u8 tbl_offset(blocks) | u8 tbl_entry_size(blocks) | pad | u32 tbl_entry_num @12 (LE)
  entries : at tbl_offset*512, each tbl_entry_size*512 bytes:
            "ENTR" | char path[220] | u8 hash[32] | u32 hash_size | u32 data_offset(blocks)
            | u32 data_size(bytes) | zero pad
            hash = SHA-1 of the entry data (hash_size 20). Unchanged entries keep their stored
            hash verbatim (byte-identical rebuild); replaced entries get a fresh SHA-1.
  data    : each entry's data at data_offset*512, padded to 512.

Uso:
  python3 -I rsce.py list <resource.img>
  python3 -I rsce.py replace <in.img> <out.img> name=file [name=file ...]
"""
import struct, sys, hashlib

BLK = 512
HDR_FMT = '<4sHHBBBxI'  # 16 bytes: u32 entry_num is naturally aligned at offset 12
ENT_FMT = '<4s220s32sIII'  # 268 bytes


def parse(b):
    magic, ver, tver, hsz, toff, tesz, num = struct.unpack_from(HDR_FMT, b, 0)
    if magic != b'RSCE':
        raise ValueError('not RSCE: %r' % magic)
    ents = []
    for i in range(num):
        o = (toff + i * tesz) * BLK
        tag, path, hsh, hsz_, doff, dsz = struct.unpack_from(ENT_FMT, b, o)
        if tag != b'ENTR':
            raise ValueError('bad entry tag at %d: %r' % (o, tag))
        name = path.split(b'\0', 1)[0].decode()
        ents.append({'name': name, 'offset': doff, 'size': dsz, 'hash': hsh, 'hash_size': hsz_,
                     'data': b[doff * BLK:doff * BLK + dsz]})
    return {'version': ver, 'tbl_version': tver, 'header_size': hsz,
            'tbl_offset': toff, 'tbl_entry_size': tesz, 'entries': ents,
            'raw_len': len(b)}


def _pad(b):
    return b + b'\0' * ((-len(b)) % BLK)


def build(r):
    """Rebuild: header, table, then data laid out sequentially in entry order (512-aligned).
    This is the layout produced by Rockchip resource_tool."""
    hsz, toff, tesz = r['header_size'], r['tbl_offset'], r['tbl_entry_size']
    ents = r['entries']
    hdr = bytearray(hsz * BLK)
    struct.pack_into(HDR_FMT, hdr, 0, b'RSCE', r['version'], r['tbl_version'], hsz, toff, tesz, len(ents))
    tbl_end = (toff + tesz * len(ents)) * BLK
    out = bytearray(max(len(hdr), tbl_end))
    out[:len(hdr)] = hdr
    pos = len(out) // BLK
    data = bytearray()
    for i, e in enumerate(ents):
        ent = bytearray(tesz * BLK)
        nm = e['name'].encode()
        if len(nm) >= 220:
            raise ValueError('name too long: %s' % e['name'])
        struct.pack_into(ENT_FMT, ent, 0, b'ENTR', nm, e.get('hash', b''), e.get('hash_size', 0), pos, len(e['data']))
        o = (toff + i * tesz) * BLK
        out[o:o + len(ent)] = ent
        d = _pad(e['data'])
        data += d
        pos += len(d) // BLK
    return bytes(out + data)


def replace(r, name, data):
    hits = [e for e in r['entries'] if e['name'] == name]
    if len(hits) != 1:
        raise KeyError('%s: %d matches' % (name, len(hits)))
    hits[0]['data'] = data
    hits[0]['hash'] = hashlib.sha1(data).digest()
    hits[0]['hash_size'] = 20


def listing(r):
    out = []
    for e in r['entries']:
        ok = e['hash'][:e['hash_size']] == hashlib.sha1(e['data']).digest()[:e['hash_size']] if e['hash_size'] else None
        out.append('%-18s off=%-6d size=%-8d sha1=%s hash_ok=%s' % (e['name'], e['offset'], len(e['data']),
                                                                 hashlib.sha1(e['data']).hexdigest(), ok))
    return out


if __name__ == '__main__':
    cmd = sys.argv[1]
    b = open(sys.argv[2], 'rb').read()
    r = parse(b)
    if cmd == 'list':
        print('\n'.join(listing(r)))
        print('rebuild identical:', build(r) == b)
    elif cmd == 'replace':
        for a in sys.argv[4:]:
            n, f = a.split('=', 1)
            replace(r, n, open(f, 'rb').read())
        open(sys.argv[3], 'wb').write(build(r))
