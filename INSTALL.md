# Installing the A95X Z2 Android 10 firmware

> ⚠️ Read **[DISCLAIMER.md](DISCLAIMER.md)** first. Flashing erases all data on the box and can,
> in the worst case, leave it unbootable. You do this at your own risk.

## 1. Check that your box is supported

This firmware is only for the **A95X Z2** with the **RK3318** SoC and board **`A95XF2R_V20`**
(2 GB RAM, front VFD clock display). The board name is printed on the PCB. If you can run apps on
the box, **AIDA64** shows the SoC and board under *System* / *CPU*.

Do **not** flash it on other models, even if they look the same.

## 2. What you need

- A **Windows PC** (Windows 10 or 11).
- A **USB A-to-A cable** (male on both ends).
- **`A95XZ2-Flash-Tools-Windows.zip`** from the same Release: Rockchip's DriverAssistant v5.14 (USB driver)
  and RKDevTool v3.28 (flashing tool), **already set to English** — nothing to configure.
- **7-Zip** or Windows Explorer to extract the download.
- A **reliable power supply** for the box (plug it directly into the wall, not into an old power strip).

## 3. Download and verify

1. Open **[Releases](../../releases)** and download the latest `update-a95xz2-a10-1.0.zip`,
   `A95XZ2-Flash-Tools-Windows.zip` and `SHA256SUMS.txt`.
2. Extract the ZIP. You get `update-a95xz2-a10-1.0.img` (about 2.6 GB).
3. Check the checksum. In PowerShell:
   ```powershell
   Get-FileHash .\update-a95xz2-a10-1.0.img -Algorithm SHA256
   ```
   The value must match the one in `SHA256SUMS.txt`. **If it does not, do not flash.**

## 4. Install the driver (once per PC)

1. Extract `A95XZ2-Flash-Tools-Windows.zip`.
2. Right-click `DriverAssistant_v5.14\DriverInstall.exe` → **Run as administrator** → **Install Driver**.
3. Open `RKDevTool_v3.28\RKDevTool.exe` (already in English).

## 5. Put the box in Loader mode

Use the box's **USB 2.0 OTG port** (the black USB 2.0 port that works as OTG — **not** the blue USB 3.0 port).
If RKDevTool does not see the box, try the other USB 2.0 port.

**Option A — the box still boots Android and has ADB enabled:**
```
adb connect <box-ip>:5555
adb reboot loader
```
Then connect the A-to-A cable between the PC and the OTG port.

**Option B — button method:** unplug the power, connect the A-to-A cable, press and hold the reset
button inside the **AV jack** (with a toothpick), plug the power back in, and release after ~5 seconds.

RKDevTool must show **"Found One LOADER Device"** (or *MASKROM*) at the bottom.

## 6. Flash

1. In RKDevTool open the **Upgrade Firmware** tab.
2. Click **Firmware** and choose `update-a95xz2-a10-1.0.img`.
3. Click **Upgrade**. Do not touch anything until the log shows **"Download Firmware Success"**
   (about 5–10 minutes).
4. If the box does not restart on its own, unplug and replug the power.

## 7. First boot

- The first boot takes **3–5 minutes** (boot logo, then the A95X Z2 animation).
- Connect to Wi-Fi with the remote: *Settings → Network & Internet*.
- The system is in **English**; change it in *Settings → Device Preferences → Language*.
  The launcher follows the system language (or choose one in its gear menu → *Language*).
- Ads and trackers are blocked by default (AdAway lists in the system `hosts` file); AdAway is
  preinstalled if you want to change the lists.
- **Root:** Magisk 31.1 is preinstalled. Apps are granted root in *Magisk → Superuser → "+"*
  (Magisk 31.1 no longer shows a pop-up when an app asks for root).

## 7b. Security notes
- **ADB requires authorization:** the first time a computer connects, the TV asks *"Allow USB debugging?"*.
  Only accept computers you own (choose *Always allow* for your own PC).
- **Network ADB** (port 5555) is **off** on a fresh install. Turn it on only if you need it, in the launcher:
  *gear menu → System → ADB debugging over network*.
- The vendor firmware's Android security patch level is **2020-05-05**; no vendor security updates exist for this
  box. Keep *Android System WebView* and *Chrome* updated from the Play Store, keep ad/tracker blocking on and only
  install apps from sources you trust.

## 8. If something goes wrong

- **The box does not show anything / does not boot:** first check the power supply and the power strip.
- **It still does not boot:** use **MaskROM mode** — open the case and short the eMMC test points
  **TP2300 + TP2301** while plugging the A-to-A cable into the OTG port, then flash again from step 6.
  Detailed guide: [01-Guia/MASKROM-RECOVERY.md](01-Guia/MASKROM-RECOVERY.md).
- **Stuck on the boot logo after flashing:** boot into recovery (hold the reset button in the AV jack
  while powering on) and choose *Wipe data/factory reset*, then *Reboot*.

## 9. Updates

Once 1.0 is installed, **no PC is needed for updates**:

- Open *Settings → System update* (or the launcher's gear menu → *System → System update*).
  The **A95X Z2 Updater** checks automatically and lists firmware and app updates.
- It also checks by itself every 6 hours and shows a small notice in the bottom-right corner when an update
  is available (OK opens the updater). It never interrupts video.
- **Firmware updates** are small deltas: every block is verified before writing (the box must be exactly on the
  expected version) and re-read after writing; then the box restarts. If the check fails nothing is written —
  flash the full image instead.
- Only our own components are updated this way. Third-party apps (SmartTube, AdAway, Magisk…) update from their
  authors as usual.
- Root for the updater is granted automatically on first boot.
