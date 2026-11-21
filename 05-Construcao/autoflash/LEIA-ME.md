# Autoflash — gravar o firmware Rockchip sem cabo nem PC Windows

Criado a 20/11/2026 para a A95X Z2 (RK3318), quando os recoveries de fábrica recusaram a `update.img`.

## Porque foi preciso
| Tentativa | Resultado | Causa |
|---|---|---|
| 1. recovery A9 + `--update_package` | `Unable to open /mnt/usb_storage/update.img` | pen na porta USB **OTG** (fica em modo dispositivo no recovery) — usar a **USB 3.0** |
| 2. idem, porta certa | `footer is wrong`, `error: 21` | `--update_package` só aceita OTA zip assinado |
| 3. recovery A9 + `--fw_update=` | "Error!" e ciclo de reinícios (pára sozinho) | o instalador Rockchip recusou a imagem; registos vazios |
| 4. recovery A10 (HK1) + `--update_package` | `error: 21` | idem 2 |
| 5. recovery A10 + `--fw_update=` | "Error!" e ciclo | idem 3 |

Em nenhuma foi gravado nada (confirmado por MD5 de uboot, trust, boot, recovery, dtbo, vbmeta e 16 MB iniciais).

## Como funciona
1. `gen.py <update.img> <sectores_do_eMMC> stick/` lê a `update.img` (RKFW/RKAF) e gera:
   - `gpt_primary.bin` / `gpt_backup.bin` — GPT do `parameter` novo (validada com `sgdisk -v`);
   - `plano.txt` — `W` partições (offset/4 na update.img, tamanho, destino em blocos 4096, MD5, sector),
     `Z` zonas a limpar, `S` resumo do super e `R`/`F`/`Z` cada bloco do `super.img` sparse;
   - `fill_*.bin` — padrões dos blocos FILL do sparse.
   Os offsets já vêm divididos: a shell `mksh` só faz contas de 32 bits.
2. `mkrec.py <recovery.img> stick/autoflash.sh <saida.img>` mete o script no ramdisk do recovery e troca
   `service recovery …` por `service recovery /system/bin/sh /autoflash.sh` (cabeçalho v0–v2, id SHA-1 refeito).
3. Na pen (FAT32, porta USB 3.0): `update.img` + pasta `autoflash/` com `MODO` = `teste` ou `gravar`.
4. `autoflash.sh` (corre em RAM): monta a pen, confirma o tamanho do eMMC, verifica o MD5 de todas as fontes,
   e só em `gravar`: muda `MODO`→`MODO.feito`, grava partições, zeros, super, GPT por último, relê e compara MD5,
   escreve `autoflash/log.txt` a cada passo e reinicia com `setprop sys.powerctl reboot`.
5. Mantém o idbloader actual (sector 64): o loader da box com o arranque de DDR que funciona.

## Armadilhas encontradas (ler antes de repetir)
- **busybox de 32 bits** (recovery A9, v1.22): `dd skip/seek` acima de 2 GB falha → leituras presas e
  **escritas em sítios errados**. Usar o recovery A10 (toybox 64 bits). Testar sempre em `MODO=teste` primeiro.
- **mksh**: aritmética de 32 bits — nada de `$((...))` com offsets grandes.
- **Reinício**: `echo b > /proc/sysrq-trigger` mantém o modo "recovery" do registo do PMU → ciclo infinito.
  Usar `setprop sys.powerctl reboot` (ou `reboot` normal). Para sair de um ciclo: desligar da corrente.
- **O Android 9 repõe o recovery de fábrica a cada arranque** (flash_recovery): gravar o recovery
  autoflash e fazer `adb reboot recovery` logo a seguir, sem reiniciar pelo meio.
- `dd conv=fsync` não existe no toybox do Android 9.
- O ecrã fica no logótipo enquanto o script corre (sem interface): seguir pelo `log.txt`.
