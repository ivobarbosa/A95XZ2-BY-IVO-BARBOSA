import json,sys
def load(p):
    d=json.load(open(p))
    def find(o,k):
        if isinstance(o,dict):
            if k in o and isinstance(o[k],list) and o[k] and isinstance(o[k][0],dict) and 'path' in o[k][0]: return o[k]
            for v in o.values():
                r=find(v,k)
                if r: return r
        elif isinstance(o,list):
            for v in o:
                r=find(v,k)
                if r: return r
    nodes=find(d,'nodes'); out={}; ph={}
    for n in nodes:
        for p in n.get('properties',[]):
            if p['name'] in ('phandle','linux,phandle'): ph[p['hex']]=n['path'].split('/')[-1]
    for n in nodes:
        props={}
        for p in n.get('properties',[]):
            dv=(p.get('derived') or {}).get('strings'); h=p.get('hex','')
            if dv: v=' '.join(dv)
            else:
                raw=bytes.fromhex(h)
                if raw and raw[-1]==0 and all(32<=c<127 or c==0 for c in raw) and any(c for c in raw[:-1]): v=raw.rstrip(b'\0').decode().replace('\0',' ')
                elif len(raw)%4==0 and raw:
                    cells=[h[i:i+8] for i in range(0,len(h),8)]
                    v=' '.join(('@'+ph[c]) if (c in ph and k%3==0 and len(cells)%3==0) else str(int(c,16)) for k,c in enumerate(cells))
                else: v=h
            props[p['name']]=v
        out[n['path']]=props
    return out
a=load(sys.argv[1]); b=load(sys.argv[2])
print('nós: box=%d  hk1=%d'%(len(a),len(b)))
print('compatible box:',a['/'].get('compatible'),'| hk1:',b['/'].get('compatible'))
print('model box:',a['/'].get('model'),'| hk1:',b['/'].get('model'))
keys=['/wireless-wlan','/wireless-bluetooth','/sdio-pwrseq','/pwm@ff1b0030','/gpio-leds','/cyx-vfd','/dmc','/ddr_timing','/reserved-memory','/memory','/adc-keys','/vcc-phy-regulator']
for k in keys:
    pa=a.get(k); pb=b.get(k)
    print('\n###',k,'box' if pa is not None else '(sem box)','/','hk1' if pb is not None else '(sem hk1)')
    if pa is None or pb is None:
        if pb is None and pa is not None: print('   FALTA NA HK1')
        continue
    for p in sorted(set(pa)|set(pb)):
        if p in ('phandle','linux,phandle'): continue
        if pa.get(p)!=pb.get(p): print('   %-28s box=%s | hk1=%s'%(p,(pa.get(p) or '-')[:70],(pb.get(p) or '-')[:70]))
# IR children
for base in ['/pwm@ff1b0030']:
    ca=sorted(x for x in a if x.startswith(base+'/')); cb=sorted(x for x in b if x.startswith(base+'/'))
    print('\nIR filhos box:',ca,' hk1:',cb)
    for c in ca:
        print('  ',c,'box usercode', a[c].get('rockchip,usercode'),'| hk1', b.get(c,{}).get('rockchip,usercode'))
only_a=sorted(x for x in a if x.count('/')==1 and x not in b); only_b=sorted(x for x in b if x.count('/')==1 and x not in a)
print('\nNós de topo só na box:',only_a); print('Nós de topo só na hk1:',only_b)
