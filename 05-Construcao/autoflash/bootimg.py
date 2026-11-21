"""Unpack/repack Android boot image v0/v1 (recovery) + newc cpio helpers. stdlib only.
unpack: python3 -I bootimg.py unpack <img> <dir> ; repack: python3 -I bootimg.py repack <orig.img> <dir> <out.img>"""
import struct, sys, os, gzip, hashlib
def rd(img):
    d=open(img,'rb').read(); assert d[:8]==b'ANDROID!'
    ks,ka,rs,ra,ss,sa,ta,ps=struct.unpack_from('<8I',d,8)
    pg=ps; o=pg
    def take(o,n): return d[o:o+n], o+((n+pg-1)//pg)*pg
    k,o=take(o,ks); r,o=take(o,rs); s,o=take(o,ss)
    hv=struct.unpack_from('<I',d,40)[0]
    ro=b''
    if hv>=1:
        rsz,roff=struct.unpack_from('<IQ',d,1632); ro,o=take(o,rsz)
    dt=b''
    if hv>=2:
        dsz=struct.unpack_from('<I',d,1648)[0]; dt,o=take(o,dsz)
    rd.dtb=dt
    return d,k,r,s,ro,pg,hv
def cpio_read(b):
    out=[];o=0
    while True:
        h=b[o:o+110]; assert h[:6]==b'070701',h[:6]
        f=[int(h[6+i*8:14+i*8],16) for i in range(13)]
        ns=f[11]; fs=f[6]; name=b[o+110:o+110+ns-1].decode(); o=(o+110+ns+3)&~3
        data=b[o:o+fs]; o=(o+fs+3)&~3
        if name=='TRAILER!!!': return out
        out.append([name,f,data])
def cpio_write(ents):
    o=bytearray(); ino=300000
    for name,f,data in ents+[['TRAILER!!!',[0]*13,b'']]:
        f=list(f); f[6]=len(data); f[11]=len(name)+1
        if name=='TRAILER!!!': f=[0]*13; f[11]=11; f[4]=1
        else: ino+=1; f[0]=ino
        o+=b'070701'+b''.join(b'%08X'%x for x in f)+name.encode()+b'\0'
        while len(o)%4: o+=b'\0'
        o+=data
        while len(o)%4: o+=b'\0'
    return bytes(o)
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='unpack':
        d,k,r,s,ro,pg,hv=rd(sys.argv[2]); os.makedirs(sys.argv[3],exist_ok=True)
        ents=cpio_read(gzip.decompress(r))
        print('hv',hv,'page',pg,'kernel',len(k),'ramdisk',len(r),'second',len(s),'entries',len(ents))
        for n,f,da in ents:
            if f[1]&0o170000==0o100000 and (n.endswith('.rc') or n.startswith(('system/bin','sbin'))): print(oct(f[1]),len(da),n)
