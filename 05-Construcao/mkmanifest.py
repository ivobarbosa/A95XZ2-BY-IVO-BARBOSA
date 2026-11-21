"""Gera e assina updates/updates.json para o A95X Z2 Updater.

O manifesto diz qual e a ultima versao do firmware (com o pacote delta de cada versao anterior e a imagem
completa) e das apps. A assinatura (RSA SHA-256, PKCS#1 v1.5, em base64) usa a chave privada que fica SO no PC
(~/android-build/keys/ota-key.pem); a app traz a chave publica (09-Updater/res/raw/ota_pub.der).
Uso: python3 -I mkmanifest.py <manifest_src.json> <pasta_updates_do_repo>
  manifest_src.json: igual ao final, mas com "file" (caminho local) em vez de size/sha256 em cada item;
  os tamanhos e sha256 sao calculados aqui a partir dos ficheiros.
"""
import json, sys, os, hashlib, subprocess, base64

KEY = os.path.expanduser('~/android-build/keys/ota-key.pem')


def fill(item):
    f = item.pop('file')
    data = open(f, 'rb').read()
    item['size'] = len(data)
    item['sha256'] = hashlib.sha256(data).hexdigest()
    return item


def main():
    src, outdir = sys.argv[1:3]
    m = json.load(open(src))
    fw = m['firmware']
    fw['deltas'] = [fill(d) for d in fw.get('deltas', [])]
    if 'full' in fw: fill(fw['full'])
    m['apps'] = [fill(a) for a in m.get('apps', [])]
    body = (json.dumps(m, indent=2, ensure_ascii=False) + '\n').encode()
    os.makedirs(outdir, exist_ok=True)
    jp = os.path.join(outdir, 'updates.json'); open(jp, 'wb').write(body)
    sig = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', KEY, jp], capture_output=True, check=True).stdout
    open(jp + '.sig', 'w').write(base64.b64encode(sig).decode() + '\n')
    pub = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '09-Updater', 'res', 'raw', 'ota_pub.der')
    tmp = jp + '.sigbin'; open(tmp, 'wb').write(sig)
    v = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', pub, '-keyform', 'DER', '-signature', tmp, jp],
                       capture_output=True, text=True)
    os.remove(tmp)
    assert 'Verified OK' in v.stdout, v.stdout + v.stderr
    print(jp, len(body), 'bytes; assinatura verificada com a chave publica do updater')


if __name__ == '__main__':
    main()
