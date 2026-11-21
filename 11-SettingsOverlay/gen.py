"""Gera res/values*/strings.xml a partir de translations.py e do texto ingles original (base.tsv)."""
import os, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from translations import T
def esc(v):
    v = html.escape(v, quote=False).replace("'", "\\'").replace('"', '\\"')
    return v
base = dict(l.rstrip('\n').split('\t', 1) for l in open('base.tsv', encoding='utf-8'))
missing = [k for k in T if k not in base]; assert not missing, missing
for i, lang in enumerate([None, 'pt', 'es', 'fr', 'de']):
    d = 'res/values' + ('-' + lang if lang else ''); os.makedirs(d, exist_ok=True)
    with open(d + '/strings.xml', 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n')
        for k, v in T.items():
            f.write('    <string name="%s" formatted="false">%s</string>\n' % (k, esc(base[k] if lang is None else v[i - 1])))
        f.write('</resources>\n')
print(len(T), 'textos x 4 idiomas')
