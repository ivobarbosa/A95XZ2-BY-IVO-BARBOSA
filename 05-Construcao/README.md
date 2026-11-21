# 05-Construcao — build tools

Everything needed to rebuild the A95X Z2 firmware, make update packages and sign the update manifest.
All tools are **plain Python 3 (standard library only)** plus `e2fsprogs` (`debugfs`, `e2fsck`, `dumpe2fs`)
and `openssl`, on Linux or WSL. Run them with `python3 -I <tool>.py` (each file starts with a usage line).

> ⚠️ See [DISCLAIMER.md](../DISCLAIMER.md). These tools write firmware images; test on your own risk.

## What is NOT in the repository (get it yourself)
| Item | Where it comes from |
|---|---|
| HK1 Max Android 10 firmware (`update.img`, RK3318) | The vendor's public download — base of the hybrid image |
| A95X Z2 stock Android 9 backup / DTB | Your own box (`a95xz2-android9.dtb` here is the reference DTB we used) |
| Magisk binaries (`magisk`, `magiskboot`, `magiskinit`, `init-ld`) | Official Magisk release APK (`lib/arm64-v8a/lib*.so`) |
| Signing keys | **Create your own**: APK keystore (made by `08-Launcher/build.sh` on first build) and OTA key (`openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072`). Never commit them. |
| Built images (`*.img`, `*.zip`) | Produced by these tools; published in GitHub **Releases** |

## How a release is built (recipe)
1. **Change the system partition** of the previous version with a `build_vN.py` (copy the latest one):
   `python3 -I build_v7.py super-hybrid-v6.img <launcher.apk> <updater.apk> <workdir>` → `super-hybrid-v7.img`.
   Files are replaced with `debugfs` keeping mode, owner and SELinux context; `e2fsck` must stay clean; free
   blocks are written as sparse `DONT_CARE` (smaller image, faster flashing).
2. **Delta packages** from each older version: `python3 -I mkdelta.py super-hybrid-v6.img super-hybrid-v7.img 6 7 delta-v6-to-v7.zip <work>`.
   The ZIP holds `apply.sh` + `plan.txt` + `blocks.bin`; the tool simulates the update and checks the result.
   On a box: `sh apply.sh <dir> --check` only reads (verifies the source version).
3. **Full image**: `python3 -I build_update_v3.py update-a95xz2-a10-v6.img update-a95xz2-a10-v7.img super=super-hybrid-v7.img`
   (Rockchip RKFW/RKAF with CRC + MD5; flash with RKDevTool *Upgrade Firmware*).
4. **Release**: upload the full image (zipped), deltas, apps and `SHA256SUMS.txt` to a new GitHub Release.
5. **Manifest**: `python3 -I mkmanifest.py manifest-src.json ../updates` writes and signs `updates/updates.json(.sig)`
   (push it **after** the Release files exist). Then delete the previous Release — only the latest is kept.

## Tools
| Tool | Purpose |
|---|---|
| `unrkfw.py` | Unpack a Rockchip RKFW/RKAF `update.img` |
| `build_update_v3.py` | Rebuild an RKFW `update.img`, replacing partitions of any size (Rockchip CRC `0x04c10db7` + MD5) |
| `build_update.py` | Older same-size variant (legacy) |
| `superinfo.py` | Read a sparse `super.img`, list dynamic partitions (LP metadata), unsparse |
| `ext4r.py` | Minimal read-only ext4 reader (lookup, read file, list dirs) |
| `build_v5.py` … `build_v9.py` | Build each version's `super` from the previous one (v5 also defines `apply.sh`) |
| `mkdelta.py` | Block-level delta between any two versions, with simulation |
| `mkmanifest.py` | Generate and sign `updates/updates.json` (RSA-SHA256) for the A95X Z2 Updater |
| `mkhosts.py` | Ad/tracker blocking `hosts` from the AdAway + StevenBlack lists (`hosts-a95xz2` is the result) |
| `vfdsrv-v7.sh` | Boot script installed as `/system/bin/vfdsrv`: front display clock (GPIO), first-boot setup, root for our apps |
| `rsce.py`, `mklogo1080.py`, `mklogo_v4.py` | Rockchip RSCE resource (DTB, boot logo) inside boot/recovery images |
| `mkbootanim_v2.py` | Boot animation generator (pure Python) |
| `mkotg_v3.py` | Patch the DTB so the OTG port works as host and device |
| `hybrid.py`, `dtdiff.py` | Hybrid boot image (A95X Z2 IR keymap/DDR values into the HK1 DTB); compare DTBs |
| `a64refs.py` | Tiny AArch64 scanner used while analysing the kernel |
| `un7z.py` | Minimal 7z extractor (LZMA/LZMA2) |
| `autoflash/` | Flash an `update.img` from a USB stick through a custom recovery (no PC); `gen.py` makes the plan |
| `magisk-patchkit/` | Magisk's boot patch scripts (binaries not included, see above) |

### Legacy (kept because newer tools import them, or for reference)
`build_v3.py` (sparse writer, model/boot-video patches), `debloat_v3.py` / `debloat_v4.py` (debugfs helpers, app
removal, VP9/AV1 codec hiding), `patch_super.py`, `build_revert.py` (restore image for the original Android 9 —
needs your own backup), `mkbootanim.py`, `mklogo.py`, `vfdsrv-v3/v4/v5.sh` (older boot scripts).
