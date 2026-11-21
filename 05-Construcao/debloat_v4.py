"""super v4 a partir do super-hybrid-v3.img (so a particao system muda):
  - /system/bin/vfdsrv           <- vfdsrv-v4.sh (no lugar, mesmo tamanho: padding '#   ...\\n'):
                                    visor por GPIO (desliga o driver fd628), "boot" ate haver hora,
                                    A95X Z2 Home como ecra inicial, root do ADB no Magisk
  - /system/media/bootanimation.zip <- nova animacao ("by Ivo Barbosa" em Segoe UI normal; mesmo tamanho)
  - remove /system/app/YouTube (ha o SmartTube), /system/app/MsLauncher_v1 e /system/app/SimpleAllApp
    (launchers antigos da HK1) e /system/preinstall/TVLauncher_1.6.2.apk
  - acrescenta /system/app/A95XZ2Home/A95XZ2Home.apk (launcher proprio, app de sistema: existe desde o 1.o
    arranque; actualizacoes futuras instalam-se por cima em /data com a mesma assinatura)
Mesmo metodo e verificacoes do debloat_v3.py (debugfs, e2fsck antes/depois, patches no sparse, releitura).
Uso: python3 -I debloat_v4.py <super-hybrid-v3.img> <super-hybrid-v4.img> <workdir>
"""
import os, sys, io, zipfile, hashlib, shutil, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import lp, unsparse
from build_v3 import Sparse, write_patched, BS
from ext4r import Ext4
from debloat_v3 import run, fsck, free_blocks, copy_range, file_blocks, expand, axml_package, apk_packages, T2009

FW = os.path.normpath(os.path.join(HERE, '..'))
REMOVE = ['/system/app/YouTube', '/system/app/MsLauncher_v1', '/system/app/SimpleAllApp',
          '/system/preinstall/TVLauncher_1.6.2.apk']
GONE = ['com.google.android.youtube.tv', 'com.hisight.mslauncher', 'com.hkw.simplelauncher', 'com.tvlauncher']
LAUNCHER_SRC = os.path.join(FW, '08-Launcher/A95XZ2-Home.apk')
LAUNCHER_DIR, LAUNCHER_DST = '/system/app/A95XZ2Home', '/system/app/A95XZ2Home/A95XZ2Home.apk'
HOSTS_SRC, HOSTS_DST = os.path.join(HERE, 'hosts-a95xz2'), '/system/etc/hosts'   # mkhosts.py
ADAWAY_SRC = os.path.join(FW, '03-Firmware/apps-adaway/AdAway-6.1.4.apk')
ADAWAY_SHA = '09f8e1528a53e5ffad59e57a174e90d4e10c5092bf4f6a60ab6594f046614417'   # = GitHub AdAway v6.1.4
ADAWAY_DST = '/system/preinstall/AdAway-6.1.4.apk'
SELINUX_SYSTEM_FILE = b'u:object_r:system_file:s0\0'


def vfd_payload(size):
    s = open(os.path.join(HERE, 'vfdsrv-v4.sh'), 'rb').read()
    assert s.startswith(b'#!/system/bin/sh\n') and b'\r' not in s and len(s) + 2 <= size
    return s + b'#' + b' ' * (size - len(s) - 2) + b'\n'


def write_same_size(img, path, new):
    fs = Ext4(img); old = fs.data(fs.lookup(path))
    assert len(new) == len(old), (path, len(new), len(old))
    blks = file_blocks(img, path)
    assert len(blks) == (len(old) + BS - 1) // BS, path
    with open(img, 'r+b') as f:
        for k, b in enumerate(blks):
            f.seek(b * BS); f.write(new[k * BS:(k + 1) * BS])
    assert Ext4(img).data(Ext4(img).lookup(path)) == new, path
    return old


def stat(img, path):
    return run(['debugfs', '-R', 'stat "%s"' % path, img])


def copy_into(src_img, raw, off):
    with open(src_img, 'rb') as g, open(raw, 'r+b') as r:
        r.seek(off)
        while True:
            c = g.read(1 << 24)
            if not c: break
            r.write(c)


def free_ranges(img):
    """Blocos livres do ext4 (numeros de bloco do fs), a partir do dumpe2fs."""
    out = run(['dumpe2fs', img])
    assert 'Block size:               4096' in out
    rng = []
    for l in out.splitlines():
        # linhas de grupo: "  Free blocks: 123-456, 789" (o resumo do superbloco nao tem indentacao)
        if not l.startswith('  Free blocks: '):
            continue
        for part in l[len('  Free blocks: '):].split(','):
            part = part.strip()
            if not part: continue
            a, _, b = part.partition('-')
            rng.append((int(a), int(b or a)))
    return rng


def write_compact(hdr, raw, dst, dc):
    """Sparse novo a partir do raw: DONT_CARE onde dc[k], FILL(0) para blocos a zeros, RAW o resto."""
    magic, maj, mnr, fhs, chs, bsz, tblk, tchunk, crc = struct.unpack('<IHHHHIIII', hdr)
    Z = bytes(BS)
    o = open(dst, 'wb'); o.write(struct.pack('<IHHHHIIII', magic, maj, mnr, 28, 12, BS, tblk, 0, 0))
    n = 0; cur = None; cnt = 0; buf = []
    def flush():
        nonlocal n, cur, cnt, buf
        if not cnt: return
        if cur == 'dc': o.write(struct.pack('<HHII', 0xCAC3, 0, cnt, 12))
        elif cur == 'z': o.write(struct.pack('<HHII', 0xCAC2, 0, cnt, 16) + b'\0\0\0\0')
        else:
            o.write(struct.pack('<HHII', 0xCAC1, 0, cnt, 12 + cnt * BS)); o.write(b''.join(buf))
        n += 1; cnt = 0; buf = []
    with open(raw, 'rb') as f:
        k = 0
        while True:
            chunk = f.read(1024 * BS)
            if not chunk: break
            for j in range(0, len(chunk), BS):
                b = chunk[j:j + BS]
                t = 'dc' if dc[k] else ('z' if b == Z else 'r')
                if t != cur or (t == 'r' and cnt >= 16384):
                    flush(); cur = t
                cnt += 1
                if t == 'r': buf.append(b)
                k += 1
    flush()
    assert k == tblk
    o.seek(20); o.write(struct.pack('<I', n)); o.close()
    return n


def main():
    src, dst, work = sys.argv[1:4]
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, 'v3.raw')
    if os.path.exists(raw): os.remove(raw)
    unsparse(src, raw)
    parts = {n: (e[0][2] * 512, e[0][0] * 512) for n, a, e in lp(raw)}
    off, size = parts['system']
    s = os.path.join(work, 'system.img'); copy_range(raw, off, size, s); shutil.copyfile(s, s + '.orig')
    f0, b0 = fsck(s), free_blocks(s)
    print('system antes : %s | livres %d blocos' % (f0, b0), flush=True)
    pk0 = apk_packages(s)
    for p in GONE: assert p in pk0.values(), 'nao encontrado: ' + p

    # 1) ficheiros substituidos no lugar (mesmo inode, modo, dono e contexto SELinux)
    st0 = {p: stat(s, p) for p in ('/system/bin/vfdsrv', '/system/media/bootanimation.zip')}
    fs = Ext4(s)
    vold = fs.data(fs.lookup('/system/bin/vfdsrv'))
    vnew = vfd_payload(len(vold))
    write_same_size(s, '/system/bin/vfdsrv', vnew)
    znew = open(os.path.join(HERE, 'bootanimation-a95xz2-v2.zip'), 'rb').read()
    zipfile.ZipFile(io.BytesIO(znew)).testzip()
    zold = write_same_size(s, '/system/media/bootanimation.zip', znew)
    assert zold != znew, 'bootanimation igual a v3 (nao foi regenerada?)'
    print('no lugar: /system/bin/vfdsrv (vfdsrv-v4, %d bytes) e /system/media/bootanimation.zip (%d bytes)'
          % (len(vnew), len(znew)))

    # 2) remocoes
    cmds, files = expand(s, REMOVE)
    cf = os.path.join(work, 'debugfs-rm.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, s])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and not l.startswith(('rm ', 'rmdir '))]
    assert not errs, errs
    print('removidos: %d ficheiros (%s)' % (len(files), ', '.join(REMOVE)))

    # 3) launcher como app de sistema
    data = open(LAUNCHER_SRC, 'rb').read()
    assert axml_package(zipfile.ZipFile(io.BytesIO(data)).read('AndroidManifest.xml')) == 'pt.a95xz2.launcher'
    local = os.path.join(work, 'A95XZ2Home.apk'); open(local, 'wb').write(data)
    sel = os.path.join(work, 'selinux.bin'); open(sel, 'wb').write(SELINUX_SYSTEM_FILE)
    hosts = open(HOSTS_SRC, 'rb').read()
    assert b'doubleclick.net' in hosts and b'\n127.0.0.1 localhost\n' in hosts
    st_h = stat(s, HOSTS_DST)
    assert 'Mode:  0644' in st_h and 'User:     0   Group:     0' in st_h and 'system_file:s0' in st_h, st_h
    ada = open(ADAWAY_SRC, 'rb').read()
    assert hashlib.sha256(ada).hexdigest() == ADAWAY_SHA
    assert axml_package(zipfile.ZipFile(io.BytesIO(ada)).read('AndroidManifest.xml')) == 'org.adaway'
    lh = os.path.join(work, 'hosts'); open(lh, 'wb').write(hosts)
    la = os.path.join(work, 'AdAway.apk'); open(la, 'wb').write(ada)
    cmds = ['rm "%s"' % HOSTS_DST, 'write "%s" "%s"' % (lh, HOSTS_DST), 'write "%s" "%s"' % (la, ADAWAY_DST)]
    for dstp in (HOSTS_DST, ADAWAY_DST):
        for fld, val in (('mode', '0100644'), ('uid', '0'), ('gid', '0'), ('links_count', '1'),
                         ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
            cmds.append('set_inode_field "%s" %s %s' % (dstp, fld, val))
        cmds.append('ea_set -f "%s" "%s" security.selinux' % (os.path.join(work, 'selinux.bin'), dstp))
    cmds += ['mkdir "%s"' % LAUNCHER_DIR]
    for fld, val in (('mode', '040755'), ('uid', '0'), ('gid', '0'), ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
        cmds.append('set_inode_field "%s" %s %s' % (LAUNCHER_DIR, fld, val))
    cmds.append('ea_set -f "%s" "%s" security.selinux' % (sel, LAUNCHER_DIR))
    cmds.append('write "%s" "%s"' % (local, LAUNCHER_DST))
    for fld, val in (('mode', '0100644'), ('uid', '0'), ('gid', '0'), ('links_count', '1'),
                     ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
        cmds.append('set_inode_field "%s" %s %s' % (LAUNCHER_DST, fld, val))
    cmds.append('ea_set -f "%s" "%s" security.selinux' % (sel, LAUNCHER_DST))
    cf = os.path.join(work, 'debugfs-add.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, s])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and
            not l.startswith(('mkdir ', 'write ', 'rm ', 'set_inode_field ', 'ea_set ', 'Allocated inode'))]
    assert not errs, errs
    print('+ %s (%d bytes, sha256 %s)' % (LAUNCHER_DST, len(data), hashlib.sha256(data).hexdigest()))

    f1, b1 = fsck(s), free_blocks(s)
    print('system depois: %s | livres %d blocos (%+d = %+.1f MiB)' % (f1, b1, b1 - b0, (b1 - b0) * BS / 2**20), flush=True)

    # ---- super final: v3.raw com a system modificada; blocos livres de TODAS as particoes -> DONT_CARE
    copy_into(s, raw, off)
    tblk = os.path.getsize(raw) // BS
    dc = bytearray(tblk)                       # 1 = bloco "nao interessa" (nao e gravado)
    inside = bytearray(tblk)
    for n, (po, psz) in parts.items():
        inside[po // BS:(po + psz) // BS] = b'\1' * (psz // BS)
        img = s if n == 'system' else os.path.join(work, n + '.img')
        if n != 'system':
            copy_range(raw, po, psz, img)
            print('%-8s %s' % (n, fsck(img)))
        nfree = 0
        for x, y in free_ranges(img):
            dc[po // BS + x:po // BS + y + 1] = b'\1' * (y - x + 1); nfree += y - x + 1
        assert nfree == free_blocks(img), (n, nfree, free_blocks(img))
        print('%-8s blocos livres -> DONT_CARE: %d (%.1f MiB)' % (n, nfree, nfree * BS / 2**20), flush=True)
        if n != 'system': os.remove(img)
    for cs, ce, ct, fo, ex in Sparse(src).chunks:   # fora das particoes: manter os DONT_CARE originais
        if ct == 0xCAC3:
            for k in range(cs // BS, ce // BS):
                if not inside[k]: dc[k] = 1
    n = write_compact(Sparse(src).hdr, raw, dst, dc)
    print('escrito', dst, os.path.getsize(dst), 'bytes (%.2f GiB),' % (os.path.getsize(dst) / 2**30), n, 'chunks', flush=True)

    # ---- verificacao a partir do ficheiro escrito
    nraw = os.path.join(work, 'v4.raw')
    if os.path.exists(nraw): os.remove(nraw)
    unsparse(dst, nraw)
    assert os.path.getsize(nraw) == os.path.getsize(raw)
    with open(raw, 'rb') as A, open(nraw, 'rb') as B:
        k = 0; M = 1024
        while True:
            x = A.read(M * BS); y = B.read(M * BS)
            if not x: break
            if x != y:
                for j in range(len(x) // BS):
                    if not dc[k + j]:
                        assert x[j * BS:(j + 1) * BS] == y[j * BS:(j + 1) * BS], 'diferenca no bloco %d' % (k + j)
            k += len(x) // BS
    for n, (po, psz) in parts.items():
        if n == 'system': continue
        img = os.path.join(work, n + '.check.img'); copy_range(nraw, po, psz, img)
        print('  %-8s e2fsck -fn (do ficheiro escrito): %s' % (n, fsck(img))); os.remove(img)
    print('verificacao: v4.raw == super final em todos os blocos usados (os livres sao DONT_CARE)')
    chk = os.path.join(work, 'system.check.img'); copy_range(nraw, off, size, chk)
    print('  e2fsck -fn:', fsck(chk))
    fs = Ext4(chk)
    assert fs.data(fs.lookup('/system/bin/vfdsrv')) == vnew
    assert fs.data(fs.lookup('/system/media/bootanimation.zip')) == znew
    assert fs.data(fs.lookup(LAUNCHER_DST)) == data
    assert fs.data(fs.lookup(HOSTS_DST)) == hosts and fs.data(fs.lookup(ADAWAY_DST)) == ada
    for p in (HOSTS_DST, ADAWAY_DST):
        st = stat(chk, p)
        assert 'Mode:  0644' in st and 'User:     0   Group:     0' in st and 'system_file:s0' in st, (p, st)
    print('  hosts: %d dominios bloqueados; AdAway 6.1.4 em /system/preinstall' % hosts.count(b'\n0.0.0.0 '))
    for p, before in st0.items():   # modo/dono/contexto iguais aos da v3
        after = stat(chk, p)
        for key in ('Mode:', 'User:', 'security.selinux'):
            l0 = [l for l in before.splitlines() if key in l]; l1 = [l for l in after.splitlines() if key in l]
            assert l0 == l1, (p, key, l0, l1)
    for p in (LAUNCHER_DIR, LAUNCHER_DST):
        st = stat(chk, p)
        assert 'User:     0   Group:     0' in st and 'system_file:s0' in st, st
    assert 'Mode:  0755' in stat(chk, LAUNCHER_DIR) and 'Mode:  0644' in stat(chk, LAUNCHER_DST)
    for p in REMOVE:
        try: fs.lookup(p); raise SystemExit('ainda existe: ' + p)
        except SystemExit: raise
        except Exception: pass
    pk1 = apk_packages(chk)
    still = sorted(set(pk1.values()) & set(GONE)); assert not still, still
    assert pk1.get(LAUNCHER_DST) == 'pt.a95xz2.launcher'
    print('  pacotes ausentes: %s' % ', '.join(GONE))
    print('  /system/preinstall = %s' % sorted(x for x, _, _ in fs.listdir(fs.lookup('/system/preinstall')) if x not in ('.', '..')))
    print('  APKs na system: %d (antes %d)' % (len(pk1), len(pk0)))
    for f in (raw, nraw, chk, s + '.orig', local, lh, la): os.remove(f)
    print('SUPER v4 OK')


if __name__ == '__main__':
    main()
