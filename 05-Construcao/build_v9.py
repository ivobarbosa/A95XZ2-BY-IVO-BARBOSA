"""v9 a partir do super-hybrid-v8.img: overlay das Definicoes 1.1 (133 textos) e release 9.
  - product: /overlay/A95XZ2SettingsOverlay.apk (RRO estatica: traduz o menu "More Settings" das Definicoes da TV)
  - system : /system/priv-app/A95XZ2Updater/A95XZ2Updater.apk <- updater 1.5 ; /system/etc/a95xz2-release <- 8
Uso: python3 -I build_v9.py <super-hybrid-v8.img> <updater.apk> <overlay.apk> <workdir>
"""
import os, sys, io, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import lp, unsparse
from build_v3 import Sparse, BS
from ext4r import Ext4
from debloat_v3 import run, fsck, free_blocks, copy_range, axml_package, T2009
from debloat_v4 import write_same_size, stat, free_ranges, write_compact, copy_into
from build_v5 import dc_from_sparse
from build_v7 import replace_file, attrs

VERSION = 9
UPDATER = '/system/priv-app/A95XZ2Updater/A95XZ2Updater.apk'
OV_DIR, OV_DST = '/overlay', '/overlay/A95XZ2SettingsOverlay.apk'   # dentro da particao product (/product)


def add_tree(img, work, ref, entries):
    """Cria pastas/ficheiros novos com dono/contexto iguais aos de 'ref' (um caminho existente na mesma particao)."""
    mode, uid, gid, ctx, _ = attrs(img, ref)
    sel = os.path.join(work, 'sel_add'); open(sel, 'wb').write(ctx.encode() + b'\0')
    cmds = []
    for path, data in entries:
        if data is None:
            cmds += ['mkdir "%s"' % path]
            m = '040755'
        else:
            local = os.path.join(work, 'add_' + os.path.basename(path)); open(local, 'wb').write(data)
            cmds += ['write "%s" "%s"' % (local, path)]
            m = '0100644'
        for fld, val in (('mode', m), ('uid', uid), ('gid', gid), ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
            cmds.append('set_inode_field "%s" %s %s' % (path, fld, val))
        if data is not None:
            cmds.append('set_inode_field "%s" links_count 1' % path)
        cmds.append('ea_set -f "%s" "%s" security.selinux' % (sel, path))
    cf = os.path.join(work, 'dbg-add.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, img])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and
            not l.startswith(('mkdir ', 'write ', 'set_inode_field ', 'ea_set ', 'Allocated inode'))]
    assert not errs, errs
    fs = Ext4(img)
    for path, data in entries:
        if data is not None: assert fs.data(fs.lookup(path)) == data, path
        a = attrs(img, path); assert a[1:4] == (uid, gid, ctx), (path, a[:4])


def main():
    src, uapk, oapk, work = sys.argv[1:5]
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, 'v9.raw')
    if os.path.exists(raw): os.remove(raw)
    unsparse(src, raw)
    tblk = os.path.getsize(raw) // BS
    parts = {n: (e[0][2] * 512, e[0][0] * 512) for n, a, e in lp(raw)}

    so, ss = parts['system']
    s = os.path.join(work, 'system.img'); copy_range(raw, so, ss, s)
    print('system v8:', fsck(s), flush=True)
    data = open(uapk, 'rb').read()
    assert axml_package(zipfile.ZipFile(io.BytesIO(data)).read('AndroidManifest.xml')) == 'pt.a95xz2.updater'
    replace_file(s, UPDATER, data, work)
    write_same_size(s, '/system/etc/a95xz2-release', ('version=%d\nname=v%d\n' % (VERSION, VERSION)).encode())
    print('system v9:', fsck(s), flush=True)
    copy_into(s, raw, so)

    po, ps = parts['product']
    p = os.path.join(work, 'product.img'); copy_range(raw, po, ps, p)
    print('product antes:', fsck(p), flush=True)
    ov = open(oapk, 'rb').read()
    assert axml_package(zipfile.ZipFile(io.BytesIO(ov)).read('AndroidManifest.xml')) == 'pt.a95xz2.overlay.tvsettings'
    replace_file(p, OV_DST, ov, work)
    print('product depois:', fsck(p), flush=True)
    copy_into(p, raw, po)

    dc = bytearray(tblk); inside = bytearray(tblk)
    for n, (o, sz) in parts.items():
        inside[o // BS:(o + sz) // BS] = b'\1' * (sz // BS)
        img = {'system': s, 'product': p}.get(n) or os.path.join(work, n + '.img')
        if n not in ('system', 'product'): copy_range(raw, o, sz, img)
        nfree = 0
        for x, y in free_ranges(img):
            dc[o // BS + x:o // BS + y + 1] = b'\1' * (y - x + 1); nfree += y - x + 1
        assert nfree == free_blocks(img), n
        if n not in ('system', 'product'): os.remove(img)
    dcp = dc_from_sparse(src, tblk)
    for k in range(tblk):
        if dcp[k] and not inside[k]: dc[k] = 1
    dst = os.path.join(HERE, 'super-hybrid-v9.img')
    n = write_compact(Sparse(src).hdr, raw, dst, dc)
    print('escrito', dst, os.path.getsize(dst), 'bytes,', n, 'chunks')
    for f in (raw, s, p): os.remove(f)
    print('V9 OK')


if __name__ == '__main__':
    main()
