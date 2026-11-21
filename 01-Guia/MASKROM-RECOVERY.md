# MaskROM recovery (box does not boot)

> ⚠️ See [DISCLAIMER.md](../DISCLAIMER.md). Opening the box and shorting test points is done at your own risk.

Use this when the box shows nothing, does not reach the boot logo, and RKDevTool does not see it in
Loader mode. In MaskROM mode the RK3318 boots from its internal ROM and waits for the PC, so the box can
always be flashed again — as long as the hardware is fine.

**Before anything else, check the power supply and the power strip.** A faulty power strip looks exactly like
a dead box. Plug the power supply directly into a wall socket.

## What you need
- Windows PC with `A95XZ2-Flash-Tools-Windows.zip` (driver installed, see [INSTALL.md](../INSTALL.md)).
- USB A-to-A cable, preferably short.
- A small screwdriver to open the case, and **metal tweezers** (or a thin wire).
- The firmware image `update-a95xz2-a10-vX.img` from the Releases.

## 1. Find the test points
1. Unplug the power. Open the case and take out the board (**A95XF2R_V20**).
2. On the **bottom side**, near the **lower edge, in the middle**, are the test points **TP2300** and **TP2301**
   (they belong to the eMMC chip, U2300). Shorting them stops the eMMC from answering, so the SoC falls back
   to MaskROM.

## 2. Enter MaskROM
1. Open RKDevTool on the PC. The box power supply stays **unplugged**.
2. Connect the A-to-A cable **to the box only** (USB 2.0 OTG port, not the blue USB 3.0 port).
3. Touch **TP2300 and TP2301 at the same time** with the tweezers.
4. Keep the short and plug the other end of the cable into the PC (the box is powered by USB).
5. When RKDevTool shows **"Found One MASKROM Device"**, remove the tweezers.
   If it does not appear: unplug the cable, adjust the tweezers and try again.

## 3. Flash
1. **Upgrade Firmware** tab → **Firmware** → choose `update-a95xz2-a10-vX.img` → **Upgrade**.
2. Wait for **"Download Firmware Success"**. Do not touch anything while it runs.
3. Unplug the USB cable, connect HDMI and the power supply. The first boot takes 3–5 minutes.

> In the *Download Image* tab, RKDevTool v3.28 refuses to write below sector 1292 ("IDB will be destroyed").
> Use **Upgrade Firmware** with the full image instead.

## 4. If it stays on the boot animation
Boot into recovery: unplug the power, **hold the reset button inside the AV jack** (or the SW1 button on the
board, next to the AV output) and plug the power back in; release when the recovery menu appears. Choose
**Wipe data/factory reset**, confirm, then **Reboot system now**.

## Troubleshooting
| Symptom | What to do |
|---|---|
| Windows shows "USB download gadget" (VID_2207) with an error | Driver not installed: run `DriverInstall.exe` as administrator |
| RKDevTool finds nothing | Wrong port (must be the USB 2.0 OTG), weak cable, or the TP2300/TP2301 short was not made |
| The box only powers on while connected to the PC | Check the wall socket, power strip and power supply |
| Stuck on the boot animation | Recovery → *Wipe data/factory reset* (step 4) |
