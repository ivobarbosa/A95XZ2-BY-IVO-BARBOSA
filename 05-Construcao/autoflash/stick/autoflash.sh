#!/system/bin/sh
# Versão para o recovery do Android 10 (toybox 64 bits; o busybox 32 bits do recovery A9 falha acima de 2 GB).
# Sem contas na shell (mksh = 32 bits): o plano traz offsets já em unidades (src/4, dst em blocos 4096, sectores 512).
# autoflash A95X Z2: corre no recovery (RAM). Lê /usb/autoflash/MODO: "teste" (só lê e verifica) ou "gravar".
B=/system/bin/toybox; G=/system/bin/grep; DEV=/dev/block/mmcblk2; LOG=/tmp/af.log; D=/usb/autoflash; IMG=/usb/update.img
log(){ echo "$($B cut -d" " -f1 /proc/uptime)s $*" >> $LOG; echo "autoflash: $*" > /dev/kmsg; [ -d $D ] && { $B cp $LOG $D/log.txt; $B sync; }; }
fim(){ log "FIM: $*"; $B cp $LOG $D/log.txt 2>/dev/null; $B sync; $B umount /usb; $B sync; $B sleep 2; $B setprop sys.powerctl reboot; $B sleep 15; echo b > /proc/sysrq-trigger; }
srcmd5(){ exec 3<"$IMG"; $B dd bs=4 skip=$1 count=0 <&3 2>/dev/null; $B head -c $2 <&3 | $B md5sum | $B cut -c1-32; exec 3<&-; }
devmd5(){ exec 3<$DEV; $B dd bs=512 skip=$1 count=0 <&3 2>/dev/null; $B head -c $2 <&3 | $B md5sum | $B cut -c1-32; exec 3<&-; }
wr(){ exec 3<"$IMG"; $B dd bs=4 skip=$1 count=0 <&3 2>/dev/null; $B head -c $2 <&3 | $B dd of=$DEV bs=4096 seek=$3 2>/dev/null; exec 3<&-; }
zr(){ $B dd if=/dev/zero of=$DEV bs=4096 seek=$1 count=$2 2>/dev/null; }
k=0
superstream(){ # src=1: lê da pen; src=0: lê do eMMC (verificação)
  $G -E '^(R|F) ' $D/plano.txt | while read t a b c e; do
    k=$(($k+1)); [ $(($k%200)) = 0 ] && log "super $1: bloco $k de 2931"
    if [ $t = R ]; then if [ $1 = 1 ]; then exec 3<"$IMG"; $B dd bs=4 skip=$a count=0 <&3 2>/dev/null; $B head -c $b <&3; exec 3<&-
                        else exec 3<$DEV; $B dd bs=512 skip=$e count=0 <&3 2>/dev/null; $B head -c $b <&3; exec 3<&-; fi
    else if [ $1 = 1 ]; then $B head -c $c "$D/$a"; else exec 3<$DEV; $B dd bs=512 skip=$e count=0 <&3 2>/dev/null; $B head -c $c <&3; exec 3<&-; fi; fi
  done | $B md5sum | $B cut -c1-32; }
log "inicio"
for i in $($B seq 1 40); do [ -b /dev/block/sda1 ] && break
  [ -r /sys/class/block/sda1/dev ] && { $B mknod /dev/block/sda1 b $($B cut -d: -f1 /sys/class/block/sda1/dev) $($B cut -d: -f2 /sys/class/block/sda1/dev); break; }; $B sleep 1; done
$B mkdir -p /usb; $B mount -t vfat /dev/block/sda1 /usb || { log "sem pen"; $B sleep 5; echo b > /proc/sysrq-trigger; }
MODO=$($B cat $D/MODO 2>/dev/null | $B tr -d '\r\n '); log "modo=$MODO"
[ "$MODO" = teste ] || [ "$MODO" = gravar ] || fim "modo invalido"
[ "$($B cat /sys/block/mmcblk2/size)" = 30777344 ] || fim "ERRO tamanho do eMMC inesperado"
log "eMMC ok; uboot actual md5 $(devmd5 16384 4194304)"
ERR=0
$G '^W ' $D/plano.txt | while read t n o l s m sec; do r=$(srcmd5 $o $l); [ "$r" = "$m" ] && log "fonte $n OK" || { log "fonte $n ERRO $r"; echo x >> /tmp/err; }; done
SM=$($G '^S ' $D/plano.txt | $B cut -d' ' -f3)
r=$(superstream 1); [ "$r" = "$SM" ] && log "fonte super OK" || { log "fonte super ERRO $r"; echo x >> /tmp/err; }
[ -s /tmp/err ] && fim "ERRO nas fontes: nada foi gravado"
[ "$MODO" = teste ] && fim "TESTE OK: nada foi gravado"
# ---------------- gravação
$B mv $D/MODO $D/MODO.feito; $B sync; log "A GRAVAR"
$G '^W ' $D/plano.txt | while read t n o l s m sec; do wr $o $l $s; log "gravado $n"; done
$G '^Z ' $D/plano.txt | while read t n s c; do zr $s $c; done; log "zeros ok"
$G -E '^(R|F) ' $D/plano.txt | while read t a b c e; do
  k=$(($k+1)); [ $(($k%200)) = 0 ] && log "a gravar super: bloco $k de 2931"
  if [ $t = R ]; then wr $a $b $c; else $B head -c $c "$D/$a" | $B dd of=$DEV bs=4096 seek=$b 2>/dev/null; fi; done; log "super gravado"
$B dd if=$D/gpt_primary.bin of=$DEV bs=512 seek=0 2>/dev/null; $B dd if=$D/gpt_backup.bin of=$DEV bs=512 seek=30777311 2>/dev/null; $B sync; log "GPT gravada"
echo 3 > /proc/sys/vm/drop_caches
$G '^W ' $D/plano.txt | while read t n o l s m sec; do r=$(devmd5 $sec $l); [ "$r" = "$m" ] && log "verif $n OK" || log "verif $n ERRO $r"; done
r=$(superstream 0); [ "$r" = "$SM" ] && log "verif super OK" || log "verif super ERRO $r"
fim "GRAVACAO TERMINADA"
