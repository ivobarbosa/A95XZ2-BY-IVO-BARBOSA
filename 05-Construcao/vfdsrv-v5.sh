#!/system/bin/sh
# vfdsrv v5 (A95X Z2, firmware hibrida HK1 Max Android 10)
# Servico init: /init.rk3328.rc "service vfdsrv" (class main, user root, oneshot,
# seclabel u:r:vfdsrv:s0). Quando este processo termina, o init mata o grupo de
# processos inteiro -> tudo o que corria em segundo plano morria (falha da v2).
# v3: o script principal so termina com "wait", depois de o bootstrap acabar.
# Sem credenciais embutidas (sem Wi-Fi, sem chave ADB): pode ser publicado.
LOG=/data/local/tmp/vfdsrv-boot.log
NAME="A95X Z2"
log() { echo "$(date '+%F %T') [$$] $*" >> $LOG 2>/dev/null; }

bootstrap() {
  log "bootstrap: inicio (uptime $(cut -d' ' -f1 /proc/uptime)s)"
  n=0
  while [ "$(getprop sys.boot_completed)" != 1 ]; do
    sleep 3; n=$((n + 1))
    [ $n -ge 200 ] && { log "bootstrap: sys.boot_completed nao chegou em 600s, a continuar"; break; }
  done
  sleep 5
  bid=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)
  if [ -n "$bid" ] && [ "$(cat /data/local/tmp/.a95x_boot_id 2>/dev/null)" = "$bid" ]; then
    log "bootstrap: ja executado neste arranque ($bid), nada a fazer"; return 0
  fi

  # 1) ADB por USB (config persistente)
  if [ "$(getprop persist.sys.usb.config)" != adb ]; then
    setprop persist.sys.usb.config adb; log "1 persist.sys.usb.config=adb (rc=$?)"
  else log "1 persist.sys.usb.config ja = adb"; fi

  # 2) ADB por rede, porta 5555 (+ reinicio do adbd). A chave do PC NAO e
  #    embutida: aceitar uma vez o aviso "Permitir depuracao USB" no ecra.
  setprop service.adb.tcp.port 5555; r1=$?
  setprop persist.adb.tcp.port 5555; r2=$?
  setprop ctl.stop adbd; sleep 1; setprop ctl.start adbd
  sleep 2; log "2 adb tcp 5555 (rc=$r1/$r2), adbd=$(getprop init.svc.adbd)"

  # 3) Porta OTG -> "otg" (comutacao automatica host/dispositivo pelo pino ID/VBUS):
  #    pen USB continua a funcionar nessa porta e, ligada a um PC, a porta passa a
  #    dispositivo (ADB por USB). Nunca "peripheral" (desligaria o modo host).
  #    So faz sentido se o dwc2 (ff580000.usb) tiver UDC (dr_mode=otg no DTB v3);
  #    sem UDC (dr_mode=host) nao mexe.
  otg=
  for f in /sys/devices/platform/*/*usb2-phy*/otg_mode /sys/devices/platform/*usb2-phy*/otg_mode; do
    [ -e "$f" ] && { otg=$f; break; }
  done
  udc=$(ls /sys/class/udc 2>/dev/null)
  if [ -z "$otg" ]; then
    log "3 otg_mode nao encontrado"
  elif [ -z "$udc" ]; then
    log "3 sem UDC (dr_mode=host no DTB): $otg fica '$(cat $otg)'"
  else
    [ "$(cat $otg 2>/dev/null)" = otg ] || echo otg > "$otg" 2>/dev/null
    log "3 UDC=$udc, $otg agora '$(cat $otg)'"
  fi

  # 4) Nome do dispositivo / Bluetooth
  [ "$(settings get global device_name)" = "$NAME" ] || settings put global device_name "$NAME"
  [ "$(settings get secure bluetooth_name)" = "$NAME" ] || settings put secure bluetooth_name "$NAME"
  # nome Wi-Fi Direct (o que aparece no WifiDisplay/Miracast e nos telemoveis): era "Android_xxxx"
  [ "$(settings get global wifi_p2p_device_name)" = "$NAME" ] || settings put global wifi_p2p_device_name "$NAME"
  log "4 device_name='$(settings get global device_name)' bluetooth_name='$(settings get secure bluetooth_name)'"

  # 5) A95X Z2 Home como ecra inicial, UMA VEZ POR INSTALACAO (marcador em /data).
  #    O launcher e app de sistema (/system/app/A95XZ2Home): existe desde o 1.o arranque.
  #    Depois disso o utilizador pode escolher outro launcher: nunca e reposto.
  HOMEDONE=/data/local/tmp/.a95x_home_done
  if [ -e "$HOMEDONE" ]; then
    log "5 home: ja definido nesta instalacao ($(cat $HOMEDONE 2>/dev/null))"
  elif pm path pt.a95xz2.launcher 2>/dev/null | grep -q '^package:'; then
    r=$(cmd package set-home-activity pt.a95xz2.launcher/.MainActivity 2>&1)
    date '+%F %T' > "$HOMEDONE" 2>/dev/null
    log "5 home: set-home-activity pt.a95xz2.launcher/.MainActivity -> $r"
  else
    log "5 home: pt.a95xz2.launcher nao instalado, tenta no proximo arranque"
  fi

  # 5b) Ambiente do Magisk (/data/adb/magisk), como na "configuracao adicional" da app: depois de
  #     gravar o firmware fica vazio e o magiskd aborta o post-fs-data (sem modulos nem service.d,
  #     portanto sem o "Systemless hosts" do AdAway). Copia os binarios e scripts da app instalada.
  ME=/data/adb/magisk
  if [ ! -x $ME/busybox ] || [ ! -f $ME/util_functions.sh ]; then
    MAPK=$(pm path com.topjohnwu.magisk 2>/dev/null | sed -n 's/^package://p' | head -1)
    if [ -n "$MAPK" ]; then
      ML=$(dirname "$MAPK")/lib/arm64
      mkdir -p $ME
      for x in busybox magisk magiskboot magiskinit magiskpolicy init-ld bootctl; do
        [ -f "$ML/lib$x.so" ] && cp "$ML/lib$x.so" "$ME/$x"
      done
      for x in util_functions.sh boot_patch.sh addon.d.sh; do
        unzip -o -p "$MAPK" "assets/$x" > "$ME/$x" 2>/dev/null
      done
      chmod -R 755 $ME; chown -R 0:0 $ME; chcon -R u:object_r:system_file:s0 $ME 2>/dev/null
      log "5b magisk: ambiente completado em $ME (ativo no proximo arranque)"
    else
      log "5b magisk: app ainda nao instalada, tenta no proximo arranque"
    fi
  fi

  # 6) Root para o ADB (uid 2000 = shell) no Magisk, UMA VEZ POR INSTALACAO.
  #    O Magisk 31.1 deixou de mostrar o aviso de pedido de root: o acesso concede-se antes, no
  #    separador Superuser da app ("+"). Aqui so o shell do ADB; as apps autorizam-se pelo utilizador.
  SUDONE=/data/local/tmp/.a95x_su_done
  M=
  if [ ! -e "$SUDONE" ] || [ ! -e /data/local/tmp/.a95x_adaway_done ]; then
    n=0
    while ! pidof magiskd >/dev/null 2>&1 && [ $n -lt 40 ]; do sleep 3; n=$((n + 1)); done
    M=$(command -v magisk 2>/dev/null)
    [ -z "$M" ] && [ -x /sbin/magisk ] && M=/sbin/magisk
  fi
  if [ ! -e "$SUDONE" ]; then
    if [ -n "$M" ] && "$M" --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES(2000,2,0,1,1)" >/dev/null 2>&1; then
      date '+%F %T' > "$SUDONE" 2>/dev/null
      log "6 magisk: root autorizado para o shell do ADB (uid 2000)"
    else
      log "6 magisk: magiskd indisponivel, tenta no proximo arranque"
    fi
  fi

  # 7) Bloqueio de publicidade, UMA VEZ POR INSTALACAO: o /system/etc/hosts da imagem ja bloqueia
  #    anuncios e rastreadores (AdAway + StevenBlack). Aqui: modulo "Systemless hosts" do Magisk (copia
  #    gravavel do hosts, para o AdAway poder atualizar as listas sem mexer na system) e root para o
  #    AdAway pre-instalado. Ativo no arranque seguinte (o Magisk monta os modulos no arranque).
  ADDONE=/data/local/tmp/.a95x_adaway_done
  if [ ! -e "$ADDONE" ] && [ -n "$M" ]; then
    HM=/data/adb/modules/hosts
    if [ ! -e $HM/system/etc/hosts ]; then
      mkdir -p $HM/system/etc
      printf 'id=hosts\nname=Systemless Hosts\nversion=1.0\nversionCode=1\nauthor=Magisk\ndescription=Magisk app built-in systemless hosts module\n' > $HM/module.prop
      cp /system/etc/hosts $HM/system/etc/hosts
      chmod 644 $HM/system/etc/hosts; chcon u:object_r:system_file:s0 $HM/system/etc/hosts 2>/dev/null
    fi
    n=0
    while ! pm path org.adaway >/dev/null 2>&1 && [ $n -lt 100 ]; do sleep 3; n=$((n + 1)); done
    au=$(pm list packages -U org.adaway 2>/dev/null | sed -n 's/.*uid:\([0-9]*\).*/\1/p' | head -1)
    if [ -n "$au" ] && "$M" --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES($au,2,0,1,1)" >/dev/null 2>&1; then
      date '+%F %T' > "$ADDONE" 2>/dev/null
      log "7 adaway: systemless hosts criado, root autorizado ao AdAway (uid $au)"
    else
      log "7 adaway: AdAway ainda nao instalado, tenta no proximo arranque"
    fi
  fi

  # 8) Root para o A95X Z2 Updater (app de sistema, Definicoes -> Atualizacao do sistema), UMA VEZ:
  #    precisa de root para gravar as atualizacoes de firmware (delta) e instalar apps.
  UPDONE=/data/local/tmp/.a95x_updater_done
  if [ ! -e "$UPDONE" ]; then
    [ -z "$M" ] && M=$(command -v magisk 2>/dev/null)
    [ -z "$M" ] && [ -x /sbin/magisk ] && M=/sbin/magisk
    uu=$(pm list packages -U pt.a95xz2.updater 2>/dev/null | sed -n 's/.*uid:\([0-9]*\).*/\1/p' | head -1)
    if [ -n "$M" ] && [ -n "$uu" ] && "$M" --sqlite "REPLACE INTO policies (uid,policy,until,logging,notification) VALUES($uu,2,0,1,1)" >/dev/null 2>&1; then
      date '+%F %T' > "$UPDONE" 2>/dev/null
      log "8 updater: root autorizado ao A95X Z2 Updater (uid $uu)"
    else
      log "8 updater: magisk ou updater indisponivel, tenta no proximo arranque"
    fi
  fi

  [ -n "$bid" ] && echo "$bid" > /data/local/tmp/.a95x_boot_id
  log "bootstrap: fim"
}

# Relogio VFD por GPIO (so se o driver do kernel fd628 nao existir; no kernel
# HK1 os GPIO 85/86 pertencem ao fd628_dev e a app com.gaoee.led trata do
# visor -> o "exec 3>" falhava e terminava o script, matando o bootstrap).
# Corre num subshell: qualquer erro aqui nunca afeta o bootstrap.
vfd_clock() {
  STB=84; DIO=85; CLK=86
  G=/sys/class/gpio
  for p in $STB $DIO $CLK; do
    [ -d $G/gpio$p ] || echo $p > $G/export 2>/dev/null
    echo out > $G/gpio$p/direction 2>/dev/null || { log "vfd: gpio$p indisponivel, relogio desligado"; return 1; }
    echo 1 > $G/gpio$p/value
  done
  command exec 3>$G/gpio$CLK/value 4>$G/gpio$DIO/value 5>$G/gpio$STB/value || { log "vfd: exec falhou"; return 1; }
  BRIGHT=${VFD_BRIGHT:-4}
  F0=63; F1=6; F2=91; F3=79; F4=102; F5=109; F6=125; F7=7; F8=127; F9=111
  sbyte() { # envia um byte, LSB primeiro, amostrado no flanco ascendente de CLK
    b=$1; i=0
    while [ $i -lt 8 ]; do
      echo 0 >&3; echo $((b & 1)) >&4; echo 1 >&3
      b=$((b >> 1)); i=$((i + 1))
    done
  }
  cmd() { echo 0 >&5; sbyte $1; echo 1 >&5; }
  show() { # $1..$4 segmentos dos digitos, $5 icones
    cmd 3; cmd 64
    echo 0 >&5; sbyte 192
    sbyte $1; sbyte 0; sbyte $2; sbyte 0; sbyte $3; sbyte 0; sbyte $4; sbyte 0; sbyte $5; sbyte 0
    echo 1 >&5
    cmd $((136 + BRIGHT))
  }
  seg() { eval echo \$F$1; }
  # Icones do visor (mapa medido na A95X Z2, 21/11/2026): bit2=power, bit3=LAN, bit4=":",
  # bit5=os dois arcos maiores do Wi-Fi (acendem juntos), bit6=arco pequeno + ponto; 0/1/7 nada.
  # Por isso o Wi-Fi so tem 2 niveis: fraco (bit6) e bom (bit5+bit6).
  icons_net() {
    n=0
    if [ "$(cat /sys/class/net/wlan0/operstate 2>/dev/null)" = up ]; then
      # RSSI em dBm via wpa_supplicant (o driver bcmdhd deixa /proc/net/wireless a zeros)
      dbm=$(wpa_cli -i wlan0 -p /data/vendor/wifi/wpa/sockets signal_poll 2>/dev/null | sed -n 's/^RSSI=//p')
      case "$dbm" in
        -*) [ "$dbm" -ge -70 ] && n=$((n | 96)) || n=$((n | 64)) ;;
        *)  n=$((n | 96)) ;;
      esac
    fi
    [ "$(cat /sys/class/net/eth0/operstate 2>/dev/null)" = up ] && n=$((n | 8))
    echo $n
  }
  # Em espera (ecra desligado pelo comando) o visor mostra so as horas, com menos brilho.
  awake() {
    case "$(dumpsys power 2>/dev/null | grep -m1 'mWakefulness=')" in
      *Asleep*|*Dozing*) return 1 ;;
    esac
    return 0
  }
  # Sem isto, ao desligar pelo comando a box entra em suspensao profunda: o CPU para e o visor
  # fica congelado (hora parada, power e Wi-Fi acesos). O wake lock mantem o CPU em minimos
  # (o Android continua em espera, HDMI desligado) e o visor mostra so as horas, a andar.
  echo a95x_vfd > /sys/power/wake_lock 2>/dev/null && log "vfd: wake lock a95x_vfd (espera sem suspensao)"
  log "vfd: relogio GPIO ativo"
  tick=0; net=0; on=1
  while true; do
    if [ $((tick % 5)) -eq 0 ]; then
      net=$(icons_net)
      if awake; then on=1; BRIGHT=${VFD_BRIGHT:-4}; else on=0; BRIGHT=1; fi
    fi
    if [ $on -eq 1 ]; then ic=$((4 | net)); else ic=0; fi
    # A box nao tem RTC: ate haver hora valida (ano >= 2025, vinda da rede) o
    # relogio do sistema mostra 01:00 (1970) e depois a data de compilacao (2020).
    # Nesse periodo o visor mostra "boot" em vez de uma hora errada.
    if [ "$(date +%Y)" -lt 2025 ]; then
      show 124 92 92 120 $ic       # b o o t
    else
      t=$(date +%H%M)
      # ":" pisca com a box ligada; fixo em espera
      if [ $on -eq 0 ] || [ $((tick % 2)) -eq 0 ]; then ic=$((ic | 16)); fi
      show $(seg ${t:0:1}) $(seg ${t:1:1}) $(seg ${t:2:1}) $(seg ${t:3:1}) $ic
    fi
    tick=$((tick + 1))
    sleep 1
  done
}

log "vfdsrv v5 iniciado (uid $(id -u), $(getenforce 2>/dev/null))"
bootstrap &
# O visor da A95X Z2 e de 3 fios (STB=84, DIO=85, CLK=86; no cyx-vfd do DTB
# Android 9). O kernel HK1 so tem o driver fd628 (2 fios, sem STB), que ocupa os
# GPIO 85/86 e deixa o visor apagado. Solucao (testada 21/11/2026): desligar o
# driver do dispositivo (unbind, sem panico) e correr o relogio por GPIO.
if [ -e /sys/bus/platform/drivers/fd628_dev/fd628_dev ]; then
  echo fd628_dev > /sys/bus/platform/drivers/fd628_dev/unbind 2>/dev/null
  log "vfd: driver fd628 desligado (unbind rc=$?)"
fi
( vfd_clock ) &
wait
log "vfdsrv v5: todos os trabalhos terminaram"
