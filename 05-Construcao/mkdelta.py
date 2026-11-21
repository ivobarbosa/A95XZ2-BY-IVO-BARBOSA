"""Pacote delta generico entre duas versoes do super (sparse, blocos livres DONT_CARE).
Inclui os blocos usados no destino que mudam (ou que estavam livres na origem); os usados na origem sao
verificados pelo apply.sh (sha256) antes de gravar. Simula a aplicacao e compara com o destino.
Uso: python3 -I mkdelta.py <super_origem.img> <super_destino.img> <v_origem> <v_destino> <saida.zip> <workdir>
"""
import os, sys, hashlib, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from superinfo import unsparse
from build_v3 import BS
from build_v5 import APPLY_SH, dc_from_sparse


def main():
    a, b, va, vb, out, work = sys.argv[1:7]
    os.makedirs(work, exist_ok=True)
    ra, rb = os.path.join(work, 'a.raw'), os.path.join(work, 'b.raw')
    unsparse(a, ra); unsparse(b, rb)
    assert os.path.getsize(ra) == os.path.getsize(rb)
    tblk = os.path.getsize(rb) // BS
    dca, dcb = dc_from_sparse(a, tblk), dc_from_sparse(b, tblk)
    ranges = []
    with open(ra, 'rb') as A, open(rb, 'rb') as B:
        k = 0
        while True:
            x = A.read(1024 * BS); y = B.read(1024 * BS)
            if not y: break
            for j in range(len(y) // BS):
                q = k + j
                if dcb[q]: continue
                if dca[q] or x[j * BS:(j + 1) * BS] != y[j * BS:(j + 1) * BS]:
                    v = 0 if dca[q] else 1
                    if ranges and ranges[-1][0] + ranges[-1][1] == q and ranges[-1][2] == v and ranges[-1][1] < 256:
                        ranges[-1][1] += 1
                    else:
                        ranges.append([q, 1, v])
            k += len(y) // BS
    plan = ['DEV /dev/block/by-name/super', 'SIZE %d' % os.path.getsize(rb), 'BS 4096', 'FROM %s' % va, 'TO %s' % vb]
    binf = os.path.join(work, 'blocks.bin'); off = 0
    with open(ra, 'rb') as A, open(rb, 'rb') as B, open(binf, 'wb') as O:
        for st, cnt, v in ranges:
            A.seek(st * BS); B.seek(st * BS)
            old = A.read(cnt * BS); new = B.read(cnt * BS)
            O.write(new)
            plan.append('R %d %d %d %s %s %d' % (st, cnt, v, hashlib.sha256(old).hexdigest() if v else '-',
                                                 hashlib.sha256(new).hexdigest(), off))
            off += cnt
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr('apply.sh', APPLY_SH)
        z.writestr('plan.txt', '\n'.join(plan) + '\n')
        z.write(binf, 'blocks.bin')
    with open(ra, 'r+b') as S, open(binf, 'rb') as Bn:
        for st, cnt, v in ranges:
            S.seek(st * BS); S.write(Bn.read(cnt * BS))
    with open(ra, 'rb') as A, open(rb, 'rb') as B:
        k = 0
        while True:
            x = A.read(1024 * BS); y = B.read(1024 * BS)
            if not y: break
            for j in range(len(y) // BS):
                if not dcb[k + j]:
                    assert x[j * BS:(j + 1) * BS] == y[j * BS:(j + 1) * BS], 'simulacao falhou no bloco %d' % (k + j)
            k += len(y) // BS
    print('%s: v%s -> v%s, %d zonas, %d blocos, zip %d bytes; simulacao OK'
          % (os.path.basename(out), va, vb, len(ranges), off, os.path.getsize(out)))
    for f in (ra, rb, binf): os.remove(f)


if __name__ == '__main__':
    main()
