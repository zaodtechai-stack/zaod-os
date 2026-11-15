## Zaod OS Phase 5 desktop session report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - session configuration, Lite mode logic and install automation are complete and tested; a Plasma boot, the idle-RAM measurement and screenshots need QEMU with real graphics, which this build host cannot run.
- Phase version: 0.5.0

## What was built

- `desktop/config/`: Plasma/KWin/baloo/power/input/splash defaults, a centered floating panel layout (`plasma-org.kde.plasma.desktop-appletsrc`), and default application associations.
- `desktop/sessions/`: Wayland session (default) and X11 fallback session entries.
- `desktop/sddm/`: display manager configuration, live-media autologin file, and an original Zaod login theme (`Main.qml`, `theme.conf`, `metadata.desktop`, original SVG background and face placeholder art). No vendor assets or trademarks.
- `desktop/systemd/`: `zaod-lite-mode.service` (hardened oneshot, ordered before the display manager), `60-zaod-swappiness.conf`, `journald-live.conf`.
- `desktop/tools/lite_mode.py`: measured Lite/full decision from total RAM and DRM driver, with `--status`, `--apply`, `--dry-run`, `--force-lite`, `--force-full`, `--json`, and an injectable `--root` so tests never touch a real home directory.
- `desktop/scripts/apply-desktop.sh`: idempotent installer into a target root filesystem with a guard against non-root targets.
- `desktop/package-list.txt`: the trimmed Plasma 6 package set the rootfs installs.

## Acceptance table

| PRD acceptance item | Status here | Evidence |
| --- | --- | --- |
| QEMU 2 GB boots Plasma, screenshot saved | NOT RUN | needs `qemu-system-x86_64` + OVMF, unavailable on this host |
| Idle RAM <= 1 GB in Lite mode after two minutes | NOT RUN | needs a booted session; measurement command documented in `docs/desktop.md` |
| Wayland and X11 fallback verified | PARTIAL | both session entries validated; runtime start needs QEMU |
| Dolphin/Konsole/Kate open and close | NOT RUN | applications come from `desktop/package-list.txt`; needs a booted session |
| Lite mode auto-selects at 2 GB and disables at 4 GB | PASS (logic) | `tests/test_lite_mode.py`, 35 tests, thresholds frozen at 2560/3840 MB |

## Commands executed here

```
python3 -m pytest tests/test_lite_mode.py -q        -> 35 passed
python3 tests/check_desktop_config.py               -> 341 checks run, 0 failed (PASS)
shellcheck desktop/scripts/*.sh                     -> clean
ruff check desktop/ tests/                          -> All checks passed
desktop/scripts/apply-desktop.sh --root fakeroot    -> 24 files installed, second run unchanged
desktop/scripts/apply-desktop.sh --root /nonexistent-root -> exit 1 with a clear message
```

## Honest limitations

- Nothing in this phase has been observed on a screen. The panel layout, SDDM theme and session entries are validated syntactically and against the files they reference, not visually.
- Plasma's `plasma-org.kde.plasma.desktop-appletsrc` is version sensitive; it must be confirmed on a real Plasma 6 build and may need the applet plugin names adjusted for the exact trixie Plasma release.
- The idle-RAM budget and the 3-tab Firefox interaction check belong to Phases 5 and 8 and both need QEMU.

## Owner test steps after the Codespaces build

```sh
make rootfs-image && desktop/scripts/apply-desktop.sh --root build/rootfs
qemu-system-x86_64 -m 2048 -enable-kvm -serial mon:stdio ...   # 2 GB guest
# inside the guest, after two minutes idle:
desktop/scripts/lite-mode.sh --status --json
free -m
systemctl status zaod-lite-mode
```

## Deviations

None. `zram-generator` and `earlyoom` configuration live in the Phase 3 rootfs overlay; this phase only ships the session-side memory tuning (swappiness, volatile journal, Lite mode) to avoid two sources of truth.
