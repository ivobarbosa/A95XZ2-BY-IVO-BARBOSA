"""v7 a partir do super-hybrid-v6.img (so a particao system muda) + delta v6 -> v7 (via mkdelta.py).

Alteracoes:
  - /system/build.prop: comenta "ro.adb.secure =0" da HK1 (o prop.default tem =1 -> ADB com autorizacao no ecra);
    acrescenta pm.dexopt.install=speed e pm.dexopt.bg-dexopt=speed (apps compiladas por inteiro: mais rapidas)
  - /system/bin/vfdsrv <- vfdsrv-v7.sh (ADB por rede ja nao e forcado; root para updater e launcher; animacoes 0)
  - /system/app/A95XZ2Home/A95XZ2Home.apk <- launcher 1.6 ; /system/priv-app/A95XZ2Updater/... <- updater 1.4
  - /system/etc/a95xz2-release <- version=7
Uso: python3 -I build_v7.py <super-hybrid-v6.img> <launcher.apk> <updater.apk> <workdir>
"""
import os, sys, io, zipfile, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import lp, unsparse
from build_v3 import Sparse, BS
from ext4r import Ext4
from debloat_v3 import run, fsck, free_blocks, copy_range, axml_package, T2009
from debloat_v4 import write_same_size, stat, free_ranges, write_compact, copy_into
from build_v5 import dc_from_sparse

VERSION = 7
LAUNCHER = '/system/app/A95XZ2Home/A95XZ2Home.apk'
UPDATER = '/system/priv-app/A95XZ2Updater/A95XZ2Updater.apk'


def attrs(img, path):
    st = stat(img, path)
    mode = re.search(r'Mode:\s+(\d+)', st).group(1)
    uid = re.search(r'User:\s+(\d+)', st).group(1)
    gid = re.search(r'Group:\s+(\d+)', st).group(1)
    ctx = re.search(r'security\.selinux \(\d+\) = "([^"\\]+)', st).group(1)
    return mode, uid, gid, ctx, st


def replace_file(img, path, data, work):
    """rm + write com o mesmo modo, dono e contexto SELinux do original."""
    mode, uid, gid, ctx, st0 = attrs(img, path)
    local = os.path.join(work, 'new_' + os.path.basename(path)); open(local, 'wb').write(data)
    sel = os.path.join(work, 'sel_' + os.path.basename(path)); open(sel, 'wb').write(ctx.encode() + b'\0')
    cmds = ['rm "%s"' % path, 'write "%s" "%s"' % (local, path)]
    for fld, val in (('mode', '0100' + mode[-3:]), ('uid', uid), ('gid', gid), ('links_count', '1'),
                     ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
        cmds.append('set_inode_field "%s" %s %s' % (path, fld, val))
    cmds.append('ea_set -f "%s" "%s" security.selinux' % (sel, path))
    cf = os.path.join(work, 'dbg.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, img])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and
            not l.startswith(('write ', 'rm ', 'set_inode_field ', 'ea_set ', 'Allocated inode'))]
    assert not errs, errs
    fs = Ext4(img); assert fs.data(fs.lookup(path)) == data, path
    m2, u2, g2, c2, _ = attrs(img, path)
    assert (m2, u2, g2, c2) == (mode, uid, gid, ctx), (path, m2, u2, g2, c2)
    for f in (local, sel): os.remove(f)


def vfd_payload(size):
    s = open(os.path.join(HERE, 'vfdsrv-v7.sh'), 'rb').read()
    assert s.startswith(b'#!/system/bin/sh\n') and b'\r' not in s and len(s) + 2 <= size
    return s + b'#' + b' ' * (size - len(s) - 2) + b'\n'


def main():
    src, lapk, uapk, work = sys.argv[1:5]
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, 'v7.raw')
    if os.path.exists(raw): os.remove(raw)
    unsparse(src, raw)
    tblk = os.path.getsize(raw) // BS
    parts = {n: (e[0][2] * 512, e[0][0] * 512) for n, a, e in lp(raw)}
    off, size = parts['system']
    s = os.path.join(work, 'system.img'); copy_range(raw, off, size, s)
    print('system v6:', fsck(s), flush=True)

    fs = Ext4(s)
    bp = fs.data(fs.lookup('/system/build.prop')).decode()
    assert bp.count('\nro.adb.secure =0\n') == 1
    bp = bp.replace('\nro.adb.secure =0\n', '\n# A95X Z2 v7: ADB com autorizacao (a HK1 tinha ro.adb.secure =0)\n#ro.adb.secure =0\n')
    assert 'pm.dexopt.install' not in bp and 'pm.dexopt.bg-dexopt' not in bp
    bp = bp.rstrip('\n') + '\n# A95X Z2 v7: apps compiladas por inteiro (mais rapidas neste CPU)\npm.dexopt.install=speed\npm.dexopt.bg-dexopt=speed\n'
    replace_file(s, '/system/build.prop', bp.encode(), work)

    old = fs.data(fs.lookup('/system/bin/vfdsrv'))
    write_same_size(s, '/system/bin/vfdsrv', vfd_payload(len(old)))
    for path, apk, pkg in ((LAUNCHER, lapk, 'pt.a95xz2.launcher'), (UPDATER, uapk, 'pt.a95xz2.updater')):
        data = open(apk, 'rb').read()
        assert axml_package(zipfile.ZipFile(io.BytesIO(data)).read('AndroidManifest.xml')) == pkg
        replace_file(s, path, data, work)
    write_same_size(s, '/system/etc/a95xz2-release', ('version=%d\nname=v%d\n' % (VERSION, VERSION)).encode())
    print('system v7:', fsck(s), flush=True)
    fs = Ext4(s)
    assert b'\nro.adb.secure' not in fs.data(fs.lookup('/system/build.prop'))
    assert b'pm.dexopt.bg-dexopt=speed' in fs.data(fs.lookup('/system/build.prop'))

    copy_into(s, raw, off)
    dc = bytearray(tblk); inside = bytearray(tblk)
    for n, (po, psz) in parts.items():
        inside[po // BS:(po + psz) // BS] = b'\1' * (psz // BS)
        img = s if n == 'system' else os.path.join(work, n + '.img')
        if n != 'system': copy_range(raw, po, psz, img)
        nfree = 0
        for x, y in free_ranges(img):
            dc[po // BS + x:po // BS + y + 1] = b'\1' * (y - x + 1); nfree += y - x + 1
        assert nfree == free_blocks(img), n
        if n != 'system': os.remove(img)
    dc6 = dc_from_sparse(src, tblk)
    for k in range(tblk):
        if dc6[k] and not inside[k]: dc[k] = 1
    dst = os.path.join(HERE, 'super-hybrid-v7.img')
    n = write_compact(Sparse(src).hdr, raw, dst, dc)
    print('escrito', dst, os.path.getsize(dst), 'bytes,', n, 'chunks')
    for f in (raw, s): os.remove(f)
    print('V7 OK')


if __name__ == '__main__':
    main()
