"""Afinacoes do super v3 por debugfs, a partir do super ja patchado por build_v3.py:
  - remove apps pre-instaladas (system/product) e os dados antigos do Nova/Kodi;
  - deixa de anunciar descodificadores VP9/AV1 (XML de codecs: vendor + apex swcodec) -> apps escolhem AVC;
  - persist.sys.timezone (vendor/build.prop) America/New_York -> Europe/Lisbon;
  - acrescenta SmartTube, TV Launcher e a app Magisk 31.1 em /system/preinstall (instalados pelo preinstall.sh da HK1 no 1.o arranque,
    como apps normais atualizaveis).

Fluxo (sem tocar no aparelho):
  1. unsparse <stage1.img> -> <work>/stage1.raw; copia as particoes LP system/vendor/product/odm para ficheiros
  2. e2fsck -fn em todas (tem de estar limpo)
  3. patches in-place (mesmo tamanho, mesmo inode/xattr/blocos): preinstall.sh, xbmc_copy_folder.sh, XML de codecs,
     vendor/build.prop (XML: preenchido com espacos no fim; scripts/props: linha '#   ...')
  4. debugfs -w: rm de cada ficheiro (pos-ordem) + rmdir das pastas das apps; depois write dos APKs novos em
     /system/preinstall com modo 0644, uid/gid 0, datas 2009-01-01 e security.selinux=u:object_r:system_file:s0
  5. e2fsck -fn outra vez (tem de estar limpo); conta blocos livres antes/depois
  6. blocos diferentes -> patches no sparse stage1 (build_v3.write_patched), mesmo layout LP/extents
  7. verificacao: unsparse do resultado == stage1.raw com as particoes modificadas; e2fsck -fn; caminhos ausentes;
     nenhum .apk restante com os pacotes removidos (AndroidManifest)
Precisa de debugfs/e2fsck (e2fsprogs). Uso:
  python3 -I debloat_v3.py <stage1_sparse.img> <out_sparse.img> <workdir>
"""
import os, sys, struct, subprocess, hashlib, io, zipfile, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import lp, unsparse
from build_v3 import Sparse, write_patched, BS
from ext4r import Ext4

REMOVE = {  # particao -> pastas/ficheiros a remover (caminhos dentro do ext4)
    'system': ['/system/app/Firefox', '/system/app/PinyinIME', '/system/app/ProductTest',
               '/system/app/RKDeviceTest', '/system/app/RKUpdateService', '/system/app/SmartYouTube',
               '/system/priv-app/StressTest', '/system/priv-app/SystemFota', '/system/priv-app/Velvet',
               '/system/preinstall/*',                      # apps antigas da HK1 (a pasta fica e recebe ADD)
               '/system/etc/org.courville.nova.tar.gz',     # dados do Nova extraidos para /data/data
               '/system/media/org.xbmc.kodi.tar.gz'],       # dados do Kodi antigo extraidos para /sdcard
    'product': ['/app/Camera2'],
}
PACKAGES = '''com.liskovsoft.videomanager com.mobdro.android com.cybermedia.cyberflx com.apkpure.aegon com.tubitv
com.disney.disneyplus com.netflix.mediaclient com.cghs.stresstest com.rockchip.devicetest com.dtinfo.tools com.example.a
com.android.camera2 com.android.inputmethod.pinyin com.google.android.googlequicksearchbox android.rockchip.update.service
org.mozilla.tv.firefox org.xbmc.kodi org.courville.nova com.lonelycatgames.Xplore com.ionitech.airscreen
com.amazon.avod.thirdpartyclient'''.split()
FW = os.path.normpath(os.path.join(HERE, '..'))
ADD = [  # (destino em system, origem, sha256 esperado ou None, pacote esperado)
    ('/system/preinstall/SmartTube_stable_32.80.apk',
     os.path.join(FW, '03-Firmware/apps-smarttube/SmartTube_stable_32.80_arm64-v8a.apk'),
     'c1e1dfdf51aeadf7dc90a27ee2e28bd885dad6a4991d4b8084045a4e3a8f7ad4', 'org.smarttube.stable'),
    ('/system/preinstall/TVLauncher_1.6.2.apk',
     os.path.join(FW, '04-Backups/backup-apps-20261120/com.tvlauncher/apk/base.apk'), None, 'com.tvlauncher'),
    ('/system/preinstall/Magisk-v31.1.apk',   # app do Magisk (o boot-v3 ja tem o patch Magisk 31.1)
     os.path.join(FW, '03-Firmware/Magisk-v31.1.apk'),
     '89cefac0a318afa39fb3880c45c87b036c05bc1ebf02a7a715b7f8d7c26ac6e7', 'com.topjohnwu.magisk'),
]
SELINUX_SYSTEM_FILE = b'u:object_r:system_file:s0\0'
T2009 = '20090101000000'
CODECS = [  # (particao, ficheiro, descodificadores a retirar)
    ('vendor', '/etc/media_codecs.xml', ['OMX.rk.video_decoder.vp9', 'OMX.rk.video_decoder.vp9.secure']),
    ('vendor', '/etc/media_codecs_google_video.xml', ['OMX.google.vp9.decoder']),
    ('vendor', '/etc/media_codecs_performance.xml', ['OMX.rk.video_decoder.vp9', 'OMX.google.vp9.decoder']),
    ('system', '/system/apex/com.android.media.swcodec/etc/media_codecs.xml',
     ['c2.android.vp9.decoder', 'c2.android.av1.decoder']),
]


def run(cmd, ok=(0,)):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode not in ok:
        raise SystemExit('falhou (%d): %s\n%s%s' % (r.returncode, ' '.join(cmd), r.stdout, r.stderr))
    return r.stdout + r.stderr


def fsck(img):
    out = run(['e2fsck', '-fn', img])
    last = [l for l in out.splitlines() if 'files' in l and 'blocks' in l][-1]
    return last


def free_blocks(img):
    out = run(['dumpe2fs', '-h', img])
    return int([l for l in out.splitlines() if l.startswith('Free blocks:')][0].split()[-1])


def copy_range(src, off, n, dst):
    with open(src, 'rb') as f, open(dst, 'wb') as o:
        f.seek(off); left = n
        while left:
            c = f.read(min(left, 1 << 24)); o.write(c); left -= len(c)


def file_blocks(img, path):
    out = run(['debugfs', '-R', 'blocks %s' % path, img])
    return [int(x) for x in out.split() if x.isdigit()]


def patch_same_size(img, path, fn, xml=False):
    fs = Ext4(img); ino = fs.lookup(path); old = fs.data(ino)
    new = fn(old.decode())
    new = new.encode()
    assert len(new) + 2 <= len(old), (path, len(new), len(old))
    if xml:   # espacos depois do elemento raiz sao XML valido
        new = new + b' ' * (len(old) - len(new) - 1) + b'\n'
    else:
        new = new + b'#' + b' ' * (len(old) - len(new) - 2) + b'\n'
    assert len(new) == len(old)
    blks = file_blocks(img, path)
    assert len(blks) == (len(old) + BS - 1) // BS
    with open(img, 'r+b') as f:
        for k, b in enumerate(blks):
            f.seek(b * BS); f.write(new[k * BS:(k + 1) * BS])
    assert Ext4(img).data(Ext4(img).lookup(path)) == new
    return old, new


def preinstall_fix(t):
    gone = set(PACKAGES)
    out = []; skip = False
    for line in t.splitlines(True):
        if line.startswith('# for nova video'):
            skip = True; continue
        if skip:
            if line.strip() == 'fi':
                skip = False
            continue
        w = line.split()
        if len(w) >= 3 and w[0] in ('pm', 'appops') and any(x in gone for x in w):
            continue
        out.append(line)
    t2 = ''.join(l for l in out if l.strip() not in ('# for camera2', '#for xplore'))
    t2 = t2.replace('#!/system/bin/sh\n', '#!/system/bin/sh\n# A95X Z2: apps antigas da HK1 removidas; '
                    '/system/preinstall = SmartTube, TV Launcher, Magisk.\n', 1)
    assert 'nova' not in t2 and 'kodi' not in t2 and 'mobdro' not in t2 and 'find $PKGS' in t2
    return t2


def xbmc_fix(t):
    t = ''.join(l for l in t.splitlines(True) if not l.startswith('#busybox'))  # comentarios mortos
    old = '\ntar -zxf $PKGS -C /sdcard/Android/data/\n'
    assert t.count(old) == 1
    return t.replace(old, '\n# A95X Z2: Kodi antigo e o tar.gz removidos da imagem\n'
                          '[ -e $PKGS ] && tar -zxf $PKGS -C /sdcard/Android/data/\n')


import re
import xml.etree.ElementTree as ET


def codec_names(text):
    return [e.get('name') for e in ET.fromstring(text.strip().encode()).iter('MediaCodec')]


def codecs_fix(drop):
    def fn(t):
        before = codec_names(t)
        for name in drop:
            pat = re.compile(r'[ \t]*<MediaCodec name="%s"(?:[^>]*?/>|[^>]*>.*?</MediaCodec>)[ \t]*\r?\n'
                             % re.escape(name), re.S)
            assert len(pat.findall(t)) == 1, (name, len(pat.findall(t)))
            t = pat.sub('', t, 1)
        after = codec_names(t)
        assert after == [n for n in before if n not in drop], (before, after)
        return t
    return fn


def tz_fix(t):
    old = '\npersist.sys.timezone=America/New_York\n'
    assert t.count(old) == 1
    return t.replace(old, '\npersist.sys.timezone=Europe/Lisbon\n')


def expand(img, paths):
    """Lista de comandos debugfs (rm ficheiros/links, rmdir pastas) em pos-ordem."""
    fs = Ext4(img); cmds = []; files = []
    def rec(p, ino):
        for n, x, ft in fs.listdir(ino):
            if n in ('.', '..'): continue
            q = p + '/' + n
            if ft == 2: rec(q, x); cmds.append('rmdir "%s"' % q)
            else: cmds.append('rm "%s"' % q); files.append(q)
    for p in paths:
        if p.endswith('/*'):
            rec(p[:-2], fs.lookup(p[:-2]))
        else:
            ino = fs.lookup(p)
            if fs.mode(ino) & 0xF000 == 0x4000:
                rec(p, ino); cmds.append('rmdir "%s"' % p)
            else:
                cmds.append('rm "%s"' % p); files.append(p)
    return cmds, files


def axml_package(b):
    o = 8; strings = None
    while o < len(b):
        t, hs, sz = struct.unpack_from('<HHI', b, o)
        if t == 1:
            sc, stc, flags, sst, ssty = struct.unpack_from('<IIIII', b, o + 8)
            utf8 = flags & 0x100; offs = struct.unpack_from('<%dI' % sc, b, o + 28); base = o + sst; strings = []
            for so in offs:
                p = base + so
                if utf8:
                    p += 2 if b[p] & 0x80 else 1
                    n = b[p]
                    if n & 0x80: n = ((n & 0x7f) << 8) | b[p + 1]; p += 2
                    else: p += 1
                    strings.append(b[p:p + n].decode('utf8', 'replace'))
                else:
                    n = struct.unpack_from('<H', b, p)[0]; p += 2
                    if n & 0x8000: n = ((n & 0x7fff) << 16) | struct.unpack_from('<H', b, p)[0]; p += 2
                    strings.append(b[p:p + 2 * n].decode('utf-16le', 'replace'))
        elif t == 0x102:
            if strings[struct.unpack_from('<I', b, o + 20)[0]] == 'manifest':
                ast, asz, ac = struct.unpack_from('<HHH', b, o + 24)
                for k in range(ac):
                    ns, nm, raw = struct.unpack_from('<III', b, o + 16 + ast + k * asz)
                    if strings[nm] == 'package': return strings[raw]
            return None
        o += sz


def apk_packages(img):
    fs = Ext4(img); out = {}
    for path, ino, ft in fs.walk():
        if ft == 1 and path.lower().endswith('.apk'):
            out[path] = axml_package(zipfile.ZipFile(io.BytesIO(fs.data(ino))).read('AndroidManifest.xml'))
    return out


def main():
    src, dst, work = sys.argv[1:4]
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, 'stage1.raw')
    if os.path.exists(raw): os.remove(raw)
    unsparse(src, raw)
    parts = {n: (e[0][2] * 512, e[0][0] * 512) for n, a, e in lp(raw)}
    imgs, before = {}, {}
    for n, (off, size) in parts.items():
        imgs[n] = os.path.join(work, n + '.img'); copy_range(raw, off, size, imgs[n])
        shutil.copyfile(imgs[n], imgs[n] + '.orig')
        before[n] = (fsck(imgs[n]), free_blocks(imgs[n]))
        print('%-8s antes : %s | livres %d blocos' % (n, before[n][0], before[n][1]), flush=True)
    pk0 = {n: apk_packages(imgs[n]) for n in imgs}
    found = {p: '%s:%s' % (n, path) for n in pk0 for path, p in pk0[n].items() if p in PACKAGES}
    missing = [p for p in PACKAGES if p not in found]
    assert not missing, 'pacotes nao encontrados: %s' % missing
    for p in PACKAGES: print('  encontrado %-42s %s' % (p, found[p]))

    s = imgs['system']
    o1, n1 = patch_same_size(s, '/system/bin/preinstall.sh', preinstall_fix)
    o2, n2 = patch_same_size(s, '/system/bin/xbmc_copy_folder.sh', xbmc_fix)
    print('patch in-place /system/bin/preinstall.sh (%d bytes) e /system/bin/xbmc_copy_folder.sh (%d bytes)' % (len(n1), len(n2)))
    edited = {('system', '/system/bin/preinstall.sh'): n1, ('system', '/system/bin/xbmc_copy_folder.sh'): n2}
    for part, path, drop in CODECS:
        o, n = patch_same_size(imgs[part], path, codecs_fix(drop), xml=True)
        edited[(part, path)] = n
        print('patch in-place %s:%s  -%s (%d -> %d bytes de conteudo)' % (part, path, drop, len(o), len(n.rstrip())))
    o, n = patch_same_size(imgs['vendor'], '/build.prop', tz_fix)
    edited[('vendor', '/build.prop')] = n
    print('patch in-place vendor:/build.prop  persist.sys.timezone=Europe/Lisbon')
    allfiles = []
    for n, paths in REMOVE.items():
        cmds, files = expand(imgs[n], paths)
        allfiles += [(n, f) for f in files]
        cf = os.path.join(work, 'debugfs-%s.cmd' % n)
        open(cf, 'w').write('\n'.join(cmds) + '\n')
        out = run(['debugfs', '-w', '-f', cf, imgs[n]])
        errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and not l.startswith(('rm ', 'rmdir '))]
        assert not errs, errs
        print('%-8s debugfs: %d comandos (%d ficheiros)' % (n, len(cmds), len(files)), flush=True)
    cmds = []
    for dstp, srcp, sha, pkg in ADD:
        data = open(srcp, 'rb').read()
        if sha: assert hashlib.sha256(data).hexdigest() == sha, srcp
        got = axml_package(zipfile.ZipFile(io.BytesIO(data)).read('AndroidManifest.xml'))
        assert got == pkg, (srcp, got)
        local = os.path.join(work, os.path.basename(dstp)); open(local, 'wb').write(data)
        cmds += ['write "%s" "%s"' % (local, dstp)]
        for fld, val in (('mode', '0100644'), ('uid', '0'), ('gid', '0'), ('links_count', '1'),
                         ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
            cmds.append('set_inode_field "%s" %s %s' % (dstp, fld, val))
        cmds.append('ea_set -f "%s" "%s" security.selinux' % (os.path.join(work, 'selinux.bin'), dstp))
    open(os.path.join(work, 'selinux.bin'), 'wb').write(SELINUX_SYSTEM_FILE)
    cf = os.path.join(work, 'debugfs-system-add.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, imgs['system']])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and not l.startswith(('write ', 'set_inode_field ', 'ea_set ', 'Allocated inode'))]
    assert not errs, errs
    for dstp, srcp, sha, pkg in ADD:
        fs = Ext4(imgs['system']); assert fs.data(fs.lookup(dstp)) == open(srcp, 'rb').read(), dstp
        st = run(['debugfs', '-R', 'stat "%s"' % dstp, imgs['system']])
        assert 'Mode:  0644' in st and 'User:     0   Group:     0' in st and 'system_file:s0' in st, st
        print('system   + %s (%d bytes, %s)' % (dstp, os.path.getsize(srcp), pkg))

    patches = []; summary = []
    for n in imgs:
        after = (fsck(imgs[n]), free_blocks(imgs[n]))
        gained = after[1] - before[n][1]
        summary.append((n, before[n], after, gained))
        print('%-8s depois: %s | livres %d blocos (%+d = %+.1f MiB)' % (n, after[0], after[1], gained, gained * BS / 2**20))
        off = parts[n][0]
        with open(imgs[n] + '.orig', 'rb') as a, open(imgs[n], 'rb') as b:
            blk = 0
            while True:
                x = a.read(BS * 256); y = b.read(BS * 256)
                if not x: break
                if x != y:
                    for k in range(0, len(x), BS):
                        if x[k:k + BS] != y[k:k + BS]:
                            patches.append((off + (blk + k // BS) * BS, y[k:k + BS]))
                blk += len(x) // BS
    print('blocos alterados (metadados + scripts): %d' % len(patches))
    nchunks = write_patched(Sparse(src), dst, patches)
    print('escrito', dst, os.path.getsize(dst), 'bytes,', nchunks, 'chunks', flush=True)

    # ---- verificacao a partir do ficheiro escrito
    nraw = os.path.join(work, 'final.raw')
    if os.path.exists(nraw): os.remove(nraw)
    unsparse(dst, nraw)
    assert os.path.getsize(nraw) == os.path.getsize(raw)
    with open(raw, 'rb') as a, open(nraw, 'rb') as b:
        pos = 0; M = 1 << 24
        while True:
            x = a.read(M); y = b.read(M)
            if not x: break
            for n, (off, size) in parts.items():   # sobrepor as particoes modificadas
                lo, hi = max(off, pos), min(off + size, pos + len(x))
                if lo < hi:
                    with open(imgs[n], 'rb') as g:
                        g.seek(lo - off); seg = g.read(hi - lo)
                    x = x[:lo - pos] + seg + x[hi - pos:]
            assert x == y, 'diferenca inesperada perto de %#x' % pos
            pos += len(x)
    print('verificacao: final.raw == stage1.raw + particoes modificadas (fora delas: identico)')
    for n, (off, size) in parts.items():
        chk = os.path.join(work, n + '.check.img'); copy_range(nraw, off, size, chk)
        print('  %-8s e2fsck -fn: %s' % (n, fsck(chk)))
        fs = Ext4(chk)
        for p in REMOVE.get(n, []):
            q = p[:-2] if p.endswith('/*') else p
            try:
                ino = fs.lookup(q)
            except Exception:
                ino = None
            if p.endswith('/*'):
                left = [x for x, _, _ in fs.listdir(ino) if x not in ('.', '..')]
                assert sorted(left) == sorted(os.path.basename(d) for d, *_ in ADD if d.startswith(q + '/')), (q, left)
            else:
                assert ino is None, ('ainda existe', n, q)
        os.remove(chk)
    pk1 = {}
    for n, (off, size) in parts.items():
        chk = os.path.join(work, n + '.check.img'); copy_range(nraw, off, size, chk)
        pk1.update({'%s:%s' % (n, k): v for k, v in apk_packages(chk).items()})
        fs = Ext4(chk)
        for (pp, path), want in edited.items():
            if pp != n: continue
            got = fs.data(fs.lookup(path)); assert got == want, path
            if path.endswith('.xml'):
                names = codec_names(got.decode())
                drop = [d for q, f, dd in CODECS if (q, f) == (pp, path) for d in dd]
                assert not set(names) & set(drop), (path, names)
                print('  %s:%s XML bem formado, %d codecs, sem %s' % (pp, path, len(names), drop))
        if n == 'system':
            for dstp, srcp, sha, pkg in ADD:
                assert fs.data(fs.lookup(dstp)) == open(srcp, 'rb').read(), dstp
                st = run(['debugfs', '-R', 'stat "%s"' % dstp, chk])
                assert 'Mode:  0644' in st and 'User:     0   Group:     0' in st and 'system_file:s0' in st
            print('  system:/system/preinstall = %s' % sorted(x for x, _, _ in fs.listdir(fs.lookup('/system/preinstall')) if x not in ('.', '..')))
        if n == 'vendor':
            assert b'\npersist.sys.timezone=Europe/Lisbon\n' in fs.data(fs.lookup('/build.prop'))
            assert b'America/New_York' not in fs.data(fs.lookup('/build.prop'))
        os.remove(chk)
    still = sorted(set(pk1.values()) & set(PACKAGES))
    assert not still, still
    print('pacotes ausentes da imagem (nenhum AndroidManifest os declara): %d/%d' % (len(PACKAGES), len(PACKAGES)))
    print('APKs restantes: %d (antes %d)' % (len(pk1), sum(len(v) for v in pk0.values())))
    tot = sum(g for *_, g in summary)
    print('espaco livre ganho (liquido, ja com SmartTube + TV Launcher + Magisk): %d blocos = %.1f MiB' % (tot, tot * BS / 2**20))
    for f in (raw, nraw): os.remove(f)
    for d, *_ in ADD: os.remove(os.path.join(work, os.path.basename(d)))
    for n in imgs: os.remove(imgs[n] + '.orig')
    print('DEBLOAT OK')


if __name__ == '__main__':
    main()
