"""v6 a partir do super-hybrid-v5.img + pacote delta v5 -> v6 (gerado a partir de build_v5.py) para o A95X Z2 Updater.

Alteracoes na particao system (as outras ficam iguais):
  - /system/bin/vfdsrv  <- vfdsrv-v5.sh (no lugar, mesmo tamanho): visor com modo de espera e Wi-Fi
    dinamico, wake lock, ambiente do Magisk completado no 1.o arranque, root para o updater
  - /system/etc/a95xz2-release (novo): "version=5"
  - /system/priv-app/A95XZ2Updater/A95XZ2Updater.apk (novo): Definicoes -> Atualizacao do sistema
Saidas:
  - super-hybrid-v5.img (sparse; blocos livres DONT_CARE, como na v4)
  - delta-v4-to-v5.zip: apply.sh + plan.txt + blocks.bin. So os blocos usados na v5 que mudam (ou que
    estavam livres na v4); os que estavam usados na v4 sao verificados (sha256) antes de gravar.
Uso: python3 -I build_v6.py <super-hybrid-v5.img> <updater.apk> <shortcut.apk> <workdir>
"""
import os, sys, io, zipfile, hashlib, shutil, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import lp, unsparse
from build_v3 import Sparse, BS
from ext4r import Ext4
from debloat_v3 import run, fsck, free_blocks, copy_range, axml_package, T2009
from debloat_v4 import write_same_size, stat, free_ranges, write_compact, copy_into, SELINUX_SYSTEM_FILE

VERSION = 6
FROM = 5
REL_DST = '/system/etc/a95xz2-release'
UPD_DIR, UPD_DST = '/system/priv-app/A95XZ2Updater', '/system/priv-app/A95XZ2Updater/A95XZ2Updater.apk'
SC_DIR, SC_DST = '/system/app/A95XZ2UpdateShortcut', '/system/app/A95XZ2UpdateShortcut/A95XZ2UpdateShortcut.apk'


def vfd_payload(size):
    s = open(os.path.join(HERE, 'vfdsrv-v5.sh'), 'rb').read()
    assert s.startswith(b'#!/system/bin/sh\n') and b'\r' not in s and len(s) + 2 <= size
    return s + b'#' + b' ' * (size - len(s) - 2) + b'\n'


def dc_from_sparse(path, tblk):
    dc = bytearray(tblk)
    for cs, ce, ct, fo, ex in Sparse(path).chunks:
        if ct == 0xCAC3:
            dc[cs // BS:ce // BS] = b'\1' * ((ce - cs) // BS)
    return dc


APPLY_SH = r'''#!/system/bin/sh
# A95X Z2 - aplica um pacote delta de firmware (gerado por 05-Construcao/build_v5.py).
# Uso: sh apply.sh <pasta_do_pacote> [--check]
# 1) confirma o dispositivo; 2) verifica cada bloco a alterar (tem de estar na versao de origem ou
# ja na de destino); 3) grava; 4) rele e compara. Sai 0 so se tudo estiver certo.
D=${1:-.}; CHECK=$2
PLAN=$D/plan.txt; BIN=$D/blocks.bin
DEV=$(sed -n 's/^DEV //p' $PLAN); SIZE=$(sed -n 's/^SIZE //p' $PLAN)
say() { echo "$*"; echo "$(date '+%F %T') $*" >> /data/local/tmp/a95x-ota.log 2>/dev/null; }
fail() { say "ERRO: $*"; exit 1; }
[ "$(id -u)" = 0 ] || fail "precisa de root"
[ -b "$DEV" ] || fail "dispositivo $DEV nao existe"
[ "$(getprop ro.product.model)" = "A95X Z2" ] || fail "modelo nao suportado"
[ "$(blockdev --getsize64 $DEV)" = "$SIZE" ] || fail "tamanho de $DEV diferente do esperado"
N=$(grep -c '^R ' $PLAN); say "pacote $(sed -n 's/^FROM //p' $PLAN) -> $(sed -n 's/^TO //p' $PLAN): $N zonas"
cur() { dd if=$DEV bs=4096 skip=$1 count=$2 2>/dev/null | sha256sum | cut -d' ' -f1; }
todo=0; i=0
while read -r t st n v old new off; do
  [ "$t" = R ] || continue; i=$((i + 1))
  h=$(cur $st $n)
  if [ "$h" = "$new" ]; then continue; fi
  if [ "$v" = 1 ] && [ "$h" != "$old" ]; then fail "zona $i (bloco $st): conteudo inesperado - firmware nao e a versao de origem"; fi
  todo=$((todo + 1))
done < $PLAN
say "verificacao OK: $todo zonas por gravar"
[ "$CHECK" = "--check" ] && { say "modo --check: nada gravado"; exit 0; }
[ $todo -eq 0 ] && { say "ja estava atualizado"; exit 0; }
blockdev --setrw $DEV 2>/dev/null
i=0
while read -r t st n v old new off; do
  [ "$t" = R ] || continue; i=$((i + 1))
  [ "$(cur $st $n)" = "$new" ] && continue
  dd if=$BIN of=$DEV bs=4096 skip=$off seek=$st count=$n conv=notrunc 2>/dev/null || fail "escrita falhou na zona $i"
  say "gravada zona $i/$N"
done < $PLAN
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
i=0
while read -r t st n v old new off; do
  [ "$t" = R ] || continue; i=$((i + 1))
  [ "$(cur $st $n)" = "$new" ] || fail "releitura falhou na zona $i"
done < $PLAN
say "SUCESSO: firmware atualizado, reinicie a box"
exit 0
'''


def main():
    src, upd_apk, sc_apk, work = sys.argv[1:5]
    os.makedirs(work, exist_ok=True)
    raw4 = os.path.join(work, 'from.raw'); raw5 = os.path.join(work, 'to.raw')
    for f in (raw4, raw5):
        if os.path.exists(f): os.remove(f)
    unsparse(src, raw4)
    tblk = os.path.getsize(raw4) // BS
    dc4 = dc_from_sparse(src, tblk)
    shutil.copyfile(raw4, raw5)
    parts = {n: (e[0][2] * 512, e[0][0] * 512) for n, a, e in lp(raw5)}
    off, size = parts['system']
    s = os.path.join(work, 'system.img'); copy_range(raw5, off, size, s)
    print('system v5:', fsck(s), flush=True)

    # v6: ficheiro de versao (mesmo tamanho), updater 1.1 por cima do 1.0, atalho das Definicoes
    rel = ('version=%d\nname=v%d\n' % (VERSION, VERSION)).encode()
    write_same_size(s, REL_DST, rel)
    apk = open(upd_apk, 'rb').read()
    assert axml_package(zipfile.ZipFile(io.BytesIO(apk)).read('AndroidManifest.xml')) == 'pt.a95xz2.updater'
    sc = open(sc_apk, 'rb').read()
    assert axml_package(zipfile.ZipFile(io.BytesIO(sc)).read('AndroidManifest.xml')) == 'com.dtinfo.tools'
    la = os.path.join(work, 'A95XZ2Updater.apk'); open(la, 'wb').write(apk)
    ls_ = os.path.join(work, 'A95XZ2UpdateShortcut.apk'); open(ls_, 'wb').write(sc)
    sel = os.path.join(work, 'selinux.bin'); open(sel, 'wb').write(SELINUX_SYSTEM_FILE)
    cmds = ['rm "%s"' % UPD_DST, 'write "%s" "%s"' % (la, UPD_DST),
            'mkdir "%s"' % SC_DIR, 'write "%s" "%s"' % (ls_, SC_DST)]
    for p, mode in ((UPD_DST, '0100644'), (SC_DIR, '040755'), (SC_DST, '0100644')):
        for fld, val in (('mode', mode), ('uid', '0'), ('gid', '0'), ('atime', T2009), ('mtime', T2009), ('ctime', T2009)):
            cmds.append('set_inode_field "%s" %s %s' % (p, fld, val))
        if mode != '040755':
            cmds.append('set_inode_field "%s" links_count 1' % p)
        cmds.append('ea_set -f "%s" "%s" security.selinux' % (sel, p))
    cf = os.path.join(work, 'debugfs-v6.cmd'); open(cf, 'w').write('\n'.join(cmds) + '\n')
    out = run(['debugfs', '-w', '-f', cf, s])
    errs = [l for l in out.splitlines() if l and not l.startswith('debugfs') and
            not l.startswith(('mkdir ', 'write ', 'rm ', 'set_inode_field ', 'ea_set ', 'Allocated inode'))]
    assert not errs, errs
    print('system v6:', fsck(s), flush=True)
    fs = Ext4(s)
    assert fs.data(fs.lookup(REL_DST)) == rel and fs.data(fs.lookup(UPD_DST)) == apk and fs.data(fs.lookup(SC_DST)) == sc
    for p in (UPD_DST, SC_DIR, SC_DST):
        t = stat(s, p); assert 'User:     0   Group:     0' in t and 'system_file:s0' in t, (p, t)

    copy_into(s, raw5, off)
    dc5 = bytearray(tblk); inside = bytearray(tblk)
    for n, (po, psz) in parts.items():
        inside[po // BS:(po + psz) // BS] = b'\1' * (psz // BS)
        img = s if n == 'system' else os.path.join(work, n + '.img')
        if n != 'system': copy_range(raw5, po, psz, img)
        nfree = 0
        for x, y in free_ranges(img):
            dc5[po // BS + x:po // BS + y + 1] = b'\1' * (y - x + 1); nfree += y - x + 1
        assert nfree == free_blocks(img), n
        if n != 'system': os.remove(img)
    for k in range(tblk):
        if dc4[k] and not inside[k]: dc5[k] = 1
    dst = os.path.join(HERE, 'super-hybrid-v6.img')
    n = write_compact(Sparse(src).hdr, raw5, dst, dc5)
    print('escrito', dst, os.path.getsize(dst), 'bytes,', n, 'chunks', flush=True)

    # ---- delta v4 -> v5
    ranges = []   # (start, count, verify)
    with open(raw4, 'rb') as A, open(raw5, 'rb') as B:
        k = 0
        while True:
            x = A.read(1024 * BS); y = B.read(1024 * BS)
            if not y: break
            for j in range(len(y) // BS):
                b = k + j
                if dc5[b]: continue
                if dc4[b] or x[j * BS:(j + 1) * BS] != y[j * BS:(j + 1) * BS]:
                    v = 0 if dc4[b] else 1
                    if ranges and ranges[-1][0] + ranges[-1][1] == b and ranges[-1][2] == v and ranges[-1][1] < 256:
                        ranges[-1][1] += 1
                    else:
                        ranges.append([b, 1, v])
            k += len(y) // BS
    plan = ['DEV /dev/block/by-name/super', 'SIZE %d' % os.path.getsize(raw5), 'BS 4096', 'FROM %d' % FROM, 'TO %d' % VERSION]
    binf = os.path.join(work, 'blocks.bin'); offb = 0
    with open(raw4, 'rb') as A, open(raw5, 'rb') as B, open(binf, 'wb') as O:
        for st, cnt, v in ranges:
            A.seek(st * BS); B.seek(st * BS)
            old = A.read(cnt * BS); new = B.read(cnt * BS)
            O.write(new)
            plan.append('R %d %d %d %s %s %d' % (st, cnt, v, hashlib.sha256(old).hexdigest() if v else '-',
                                                 hashlib.sha256(new).hexdigest(), offb))
            offb += cnt
    dz = os.path.join(HERE, 'delta-v5-to-v6.zip')
    with zipfile.ZipFile(dz, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr('apply.sh', APPLY_SH)
        z.writestr('plan.txt', '\n'.join(plan) + '\n')
        z.write(binf, 'blocks.bin')
    print('delta: %d zonas, %d blocos (%.1f KiB), %d verificadas; zip %d bytes'
          % (len(ranges), offb, offb * 4, sum(1 for r in ranges if r[2]), os.path.getsize(dz)))

    # ---- simulacao: aplicar o delta ao v4.raw tem de dar o v5 em todos os blocos usados
    sim = raw4
    with open(sim, 'r+b') as S, open(binf, 'rb') as Bn:
        for st, cnt, v in ranges:
            S.seek(st * BS); Bn.seek(0)
        Bn.seek(0)
        for st, cnt, v in ranges:
            S.seek(st * BS); S.write(Bn.read(cnt * BS))
    with open(sim, 'rb') as A, open(raw5, 'rb') as B:
        k = 0
        while True:
            x = A.read(1024 * BS); y = B.read(1024 * BS)
            if not y: break
            for j in range(len(y) // BS):
                if not dc5[k + j]:
                    assert x[j * BS:(j + 1) * BS] == y[j * BS:(j + 1) * BS], 'simulacao falhou no bloco %d' % (k + j)
            k += len(y) // BS
    print('simulacao: v5 + delta == v6 em todos os blocos usados')
    for f in (raw4, raw5, s, binf, la, ls_): os.remove(f)
    print('V6 OK')


if __name__ == '__main__':
    main()
