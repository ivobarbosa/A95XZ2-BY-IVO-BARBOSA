# 07-Logo — Logótipo de arranque A95X Z2

Novo logótipo de arranque para substituir o antigo "HK1 RBOX".
Fundo escuro com gradiente radial, "A95X" a branco e "Z2" em gradiente ciano→violeta,
uma linha de destaque, o subtítulo "ANDROID TV" e, por baixo, em letra mais pequena,
"Firmware personalizado · by Ivo Barbosa".

Há duas variantes para comparar (só muda o texto por baixo da linha):

- **Variante A** (ficheiros sem sufixo): "ANDROID TV" + "Firmware personalizado · by Ivo Barbosa".
- **Variante B** (ficheiros com sufixo `_v2`): "ANDROID 10 · 2026" + "by Ivo Barbosa".
  Para usar a B, renomear `logo_v2.bmp` → `logo.bmp` e `logo_kernel_v2.bmp` → `logo_kernel.bmp`.

## Ficheiros

| Ficheiro | Formato | Tamanho |
|---|---|---|
| `logo.bmp` | BMP 1280x720, 24 bits, sem compressão (BI_RGB), bottom-up | 2 764 854 bytes |
| `logo_kernel.bmp` | Igual ao `logo.bmp` (cópia idêntica) | 2 764 854 bytes |
| `logo_8bit.bmp` | BMP 1280x720, 8 bits com paleta de 256 cores, sem compressão | 922 678 bytes |
| `preview.png` | Pré-visualização PNG 1280x720 (só para aprovar o aspecto) | ~149 KB |
| `logo_v2.bmp`, `logo_kernel_v2.bmp`, `logo_8bit_v2.bmp`, `preview_v2.png` | Variante B, mesmos formatos | iguais aos da A (PNG ~147 KB) |
| `logo_v2_1080.bmp`, `preview_v2_1080.png` | Variante B em 1920x1080 (BMP 24-bit bottom-up normal) — a que vai para o boot/recovery (`05-Construcao/mklogo1080.py`), para ocupar o ecrã todo sem escalar | 6 220 854 bytes |
| `gerar_logo.py` | Script em Python puro (sem Pillow) que gera as duas variantes | — |

Para regenerar: `python3 gerar_logo.py` (ou `python3 gerar_logo.py 1080` só para a versão 1920x1080) (usa as fontes Segoe UI do Windows em `/mnt/c/Windows/Fonts`).

## Onde entram

Nas boxes Rockchip o logótipo não é uma imagem solta: fica dentro da **imagem de recursos
Rockchip (RSCE, `resource.img`)**, que nesta box está embutida no `boot.img`
(e também no `recovery.img`). Lá dentro há dois ficheiros com estes nomes exactos:

- `logo.bmp` — mostrado pelo U-Boot assim que a box liga;
- `logo_kernel.bmp` — mostrado pelo kernel até o Android arrancar.

Basta substituir esses dois ficheiros dentro do RSCE e reempacotar o `boot.img`/`recovery.img`.
Em alguns firmwares existe também uma partição própria `logo`; nesse caso grava-se lá o `logo.bmp`.

Se o U-Boot desta box não aceitar BMP de 24 bits (fica ecrã preto ou volta o logo antigo),
usar o `logo_8bit.bmp` renomeado para `logo.bmp` (e `logo_kernel.bmp`).

**Nota:** nada foi gravado na box. Estes ficheiros são só as imagens; a substituição no
`boot.img` e o flash são um passo separado, a fazer com cópia de segurança e só depois de
aprovado o aspecto no `preview.png`.
