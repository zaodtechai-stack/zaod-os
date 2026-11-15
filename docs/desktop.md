# Zaod desktop session

The Zaod session is a trimmed KDE Plasma 6 desktop with Wayland as the default
and X11 kept as a fallback for hardware where Wayland cannot start. This
document describes what the repository ships, how it is installed into a root
filesystem, and how Lite mode changes behaviour on low-end machines.

## What is in `desktop/`

| Path | Purpose |
| --- | --- |
| `desktop/config/` | Base Plasma/KWin/SDDM-adjacent user defaults installed to `/etc/skel/.config` and `/etc/xdg` |
| `desktop/sessions/` | Wayland and X11 session entries for the display manager |
| `desktop/sddm/` | Display manager configuration plus the original Zaod login theme (QML + SVG artwork) |
| `desktop/systemd/` | Lite mode oneshot unit, swappiness sysctl, volatile journal drop-in for live media |
| `desktop/tools/lite_mode.py` | Measured Lite/full decision logic and the config applier |
| `desktop/scripts/` | `apply-desktop.sh` installer and the `lite-mode.sh` wrapper |
| `desktop/package-list.txt` | Plasma 6 packages the Phase 3 rootfs installs for this session |
| `desktop/design/` | Phase 6 design system (tokens, generated themes, shell QML, wallpapers) |

## Installing the session config

```sh
sudo desktop/scripts/apply-desktop.sh --root /            # install into a live root
desktop/scripts/apply-desktop.sh --root build/rootfs --dry-run   # inspect first
```

The installer verifies that the target looks like a root filesystem, installs
each file with `install -D`, and is safe to re-run: content depends only on the
repository, so a second run rewrites identical bytes.

## Wayland first, X11 fallback

* `plasmawayland.desktop` runs `startplasma-wayland` and is the default session
  in `sddm.conf.d/zaod.conf`.
* `plasmax11.desktop` runs `startplasma-x11`. It exists for GPUs whose driver
  cannot start a Wayland compositor; `zaod.safegfx` on the live ISO boots with
  `nomodeset`, and the display manager then offers the X11 session.
* Xwayland is installed by the package list so X11-only applications keep
  working inside the Wayland session.

## Lite mode

Lite mode is decided from two measured facts only, which makes it reproducible
and testable without a running desktop:

| Input | Source |
| --- | --- |
| Total RAM | `MemTotal` in `/proc/meminfo` |
| Graphics | driver name behind `/sys/class/drm/card*/device/driver`, with a kernel module list fallback |

Decision rules (`desktop/tools/lite_mode.py`):

| Condition | Mode |
| --- | --- |
| RAM <= 2560 MB | `lite` |
| 2561-3839 MB | `lite` (conservative) |
| RAM >= 3840 MB and a real DRM driver | `full` |
| Software rendering only (`simpledrm`, `simple-framebuffer`, `vkms`, none) | `lite` regardless of RAM |

When Lite mode is active the applier disables KWin effects and baloo indexing,
caps the compositor to 30 FPS with a low latency policy, and records the chosen
mode in `zaod-lite.conf`. `systemd/zaod-lite-mode.service` runs the applier
before the display manager so the session starts already tuned.

Manual control:

```sh
desktop/scripts/lite-mode.sh --status          # what would be chosen now
desktop/scripts/lite-mode.sh --status --json   # machine readable
sudo desktop/scripts/lite-mode.sh --apply      # write configs
desktop/scripts/lite-mode.sh --force-full      # override the measurement
```

## Live media versus installed system

* Live images use `sddm.conf.d/zaod-live.conf`, which autologins the passwordless
  `zaodlive` account. The installer removes that file; the installed system never
  ships a passwordless account.
* Journald runs with `Storage=volatile` (`journald-live.conf`) so live sessions
  never write logs to the read-only squashfs.
* `vm.swappiness=100` with `vm.page-cluster=0` matches the zram-only swap policy
  fixed in the PRD.

## Verification

```sh
python3 -m pytest tests/test_lite_mode.py -q      # 35 decision and applier tests
python3 tests/check_desktop_config.py             # 341 shipped-config checks
shellcheck desktop/scripts/*.sh
```
