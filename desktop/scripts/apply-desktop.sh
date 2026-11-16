#!/usr/bin/env bash
# Install the Zaod desktop session configuration into a target root filesystem.
#
# Usage: apply-desktop.sh [--root DIR] [--dry-run]
#   --root DIR  target root filesystem (default: $ROOTFS or /)
#
# Idempotent: every file is installed with `install -D`, so re-running only
# rewrites identical content. Fails loudly when the target is not a root tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${ROOTFS:-/}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      TARGET_ROOT="${2:?--root needs a directory}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      sed -n '2,8p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      printf 'apply-desktop: unknown argument %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$TARGET_ROOT" ]]; then
  printf 'apply-desktop: target root %s does not exist\n' "$TARGET_ROOT" >&2
  exit 1
fi

if [[ ! -d "$TARGET_ROOT/etc" ]]; then
  printf 'apply-desktop: %s does not look like a root filesystem (no /etc)\n' "$TARGET_ROOT" >&2
  exit 1
fi

install_file() {
  local src="$1" dest="$2" mode="$3"
  if [[ ! -f "$src" ]]; then
    printf 'apply-desktop: missing source file %s\n' "$src" >&2
    exit 1
  fi
  printf '  %s -> %s (%s)\n' "$src" "$dest" "$mode"
  if [[ $DRY_RUN -eq 1 ]]; then
    return 0
  fi
  install -D -m "$mode" "$src" "$dest"
}

printf 'apply-desktop: installing into %s\n' "$TARGET_ROOT"

# Per-user defaults applied to new accounts.
for f in kdeglobals kwinrc kscreenlockerrc powermanagementprofilesrc kcminputrc \
         ksplashrc baloofilerc plasma-org.kde.plasma.desktop-appletsrc; do
  install_file "$DESKTOP_DIR/config/$f" "$TARGET_ROOT/etc/skel/.config/$f" 0644
done
install_file "$DESKTOP_DIR/config/mimeapps.list" "$TARGET_ROOT/etc/skel/.config/mimeapps.list" 0644

# System-wide defaults, so the live session and root session look identical.
for f in kdeglobals kwinrc mimeapps.list; do
  install_file "$DESKTOP_DIR/config/$f" "$TARGET_ROOT/etc/xdg/$f" 0644
done

# Session entries.
install_file "$DESKTOP_DIR/sessions/plasmawayland.desktop" \
  "$TARGET_ROOT/usr/share/wayland-sessions/plasmawayland.desktop" 0644
install_file "$DESKTOP_DIR/sessions/plasmax11.desktop" \
  "$TARGET_ROOT/usr/share/xsessions/plasmax11.desktop" 0644

# SDDM configuration and the Zaod theme.
install_file "$DESKTOP_DIR/sddm/sddm.conf.d/zaod.conf" \
  "$TARGET_ROOT/etc/sddm.conf.d/zaod.conf" 0644
install_file "$DESKTOP_DIR/sddm/sddm.conf.d/zaod-live.conf" \
  "$TARGET_ROOT/etc/sddm.conf.d/zaod-live.conf" 0644
for f in Main.qml theme.conf metadata.desktop background.svg; do
  install_file "$DESKTOP_DIR/sddm/themes/zaod/$f" \
    "$TARGET_ROOT/usr/share/sddm/themes/zaod/$f" 0644
done
install_file "$DESKTOP_DIR/sddm/themes/zaod/faces/user.svg" \
  "$TARGET_ROOT/usr/share/sddm/themes/zaod/faces/user.svg" 0644

# Lite mode service, memory policy and volatile journal for the live session.
install_file "$DESKTOP_DIR/systemd/zaod-lite-mode.service" \
  "$TARGET_ROOT/etc/systemd/system/zaod-lite-mode.service" 0644
install_file "$DESKTOP_DIR/systemd/60-zaod-swappiness.conf" \
  "$TARGET_ROOT/etc/sysctl.d/60-zaod-swappiness.conf" 0644
install_file "$DESKTOP_DIR/systemd/journald-live.conf" \
  "$TARGET_ROOT/usr/lib/systemd/journald.conf.d/90-zaod-live.conf" 0644
install_file "$DESKTOP_DIR/tools/lite_mode.py" \
  "$TARGET_ROOT/usr/lib/zaod/lite_mode.py" 0755

# First-boot onboarding: the wizard, its unit and the directory it marks done.
install_file "$DESKTOP_DIR/oobe/oobe.py" "$TARGET_ROOT/usr/lib/zaod/oobe.py" 0755
install_file "$DESKTOP_DIR/systemd/zaod-oobe.service" \
  "$TARGET_ROOT/etc/systemd/system/zaod-oobe.service" 0644
if [[ $DRY_RUN -eq 0 ]]; then
  install -d -m 0755 "$TARGET_ROOT/etc/zaod"
fi

printf 'apply-desktop: done\n'
