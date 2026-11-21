"""Gera o /system/etc/hosts com bloqueio de publicidade e rastreadores para a imagem A95X Z2.
Junta as duas listas que o AdAway usa por omissao (AdAway oficial + StevenBlack Unified), sem repetidos,
no formato "0.0.0.0 dominio". Garante que nada essencial fica bloqueado (YouTube/SmartTube, Play Store,
GitHub das atualizacoes, NTP, etc.).
Uso: python3 -I mkhosts.py <adaway.txt> <stevenblack.txt> <saida_hosts>
  (descarregar antes: https://adaway.org/hosts.txt e
   https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts)
"""
import sys, re, hashlib

LOCAL = {'localhost', 'localhost.localdomain', 'local', 'broadcasthost', 'ip6-localhost', 'ip6-loopback',
         'ip6-localnet', 'ip6-mcastprefix', 'ip6-allnodes', 'ip6-allrouters', 'ip6-allhosts', '0.0.0.0'}
# Nunca bloquear (o dominio e os subdominios): sem isto o firmware deixaria de funcionar.
KEEP = ['youtube.com', 'googlevideo.com', 'ytimg.com', 'ggpht.com', 'youtubei.googleapis.com',
        'play.google.com', 'android.clients.google.com', 'play.googleapis.com', 'gvt1.com', 'gvt2.com',
        'github.com', 'githubusercontent.com', 'githubassets.com', 'api.github.com',
        'smarttube.app', 'liskovsoft', 'connectivitycheck.gstatic.com', 'time.android.com', 'pool.ntp.org',
        'clients3.google.com', 'mtalk.google.com', 'android.googleapis.com']
DOM = re.compile(r'^[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?(\.[a-z0-9_]([a-z0-9_-]*[a-z0-9_])?)+$')


def parse(path):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.split('#', 1)[0].strip().lower()
        if not line:
            continue
        w = line.split()
        if len(w) < 2 or w[0] not in ('0.0.0.0', '127.0.0.1'):
            continue
        for d in w[1:]:
            if d not in LOCAL and DOM.match(d):
                out.append(d)
    return out


def kept(d):
    return any(d == k or d.endswith('.' + k) or (('.' not in k) and k in d) for k in KEEP)


def main():
    a, s, dst = sys.argv[1:4]
    doms, seen, dropped = [], set(), []
    for src in (a, s):
        for d in parse(src):
            if d in seen:
                continue
            seen.add(d)
            if kept(d):
                dropped.append(d)
                continue
            doms.append(d)
    head = ('# /system/etc/hosts - A95X Z2 (bloqueio de publicidade e rastreadores)\n'
            '# Fontes: https://adaway.org/hosts.txt + https://github.com/StevenBlack/hosts (Unified)\n'
            '# Gerado por 05-Construcao/mkhosts.py. Para desligar: AdAway ou Magisk "Systemless hosts".\n'
            '127.0.0.1 localhost\n::1 ip6-localhost\n')
    body = ''.join('0.0.0.0 %s\n' % d for d in doms)
    data = (head + body).encode()
    open(dst, 'wb').write(data)
    assert 'doubleclick.net' in seen
    print('%d dominios bloqueados, %d mantidos por seguranca (%s), %d bytes, sha256 %s'
          % (len(doms), len(dropped), ', '.join(sorted(dropped)[:8]) + ('...' if len(dropped) > 8 else ''),
             len(data), hashlib.sha256(data).hexdigest()))


if __name__ == '__main__':
    main()
