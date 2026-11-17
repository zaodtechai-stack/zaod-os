#!/usr/bin/env bash
# Verify that the desktop an image ships can actually run, inside the built tree.
#
# Usage: verify-rootfs-desktop.sh --root DIR
#
# Every check here answers a failure a person saw on real hardware: applications
# that would not start (no PySide6 in the image), launcher icons that were blank
# (no hicolor theme, no SVG loader), a login that refused its theme, and a
# wallpaper that never appeared. It runs against the assembled root filesystem
# before it is squashed, so a broken desktop cannot reach an ISO.
set -euo pipefail

TARGET_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      TARGET_ROOT="${2:?--root needs a directory}"
      shift 2
      ;;
    *)
      printf 'verify-rootfs-desktop: unknown argument %s\n' "$1" >&2
      exit 2
      ;;
  esac
done

[[ -n "$TARGET_ROOT" && -d "$TARGET_ROOT" ]] || {
  printf 'verify-rootfs-desktop: --root must be an existing directory\n' >&2
  exit 2
}

as_root() {
  if (( EUID == 0 )); then "$@"; else sudo -n "$@"; fi
}

FAILED=0
ok() { printf '  ok   %s\n' "$1"; }
bad() { printf '  FAIL %s\n' "$1" >&2; FAILED=1; }
have() { if as_root test -e "$TARGET_ROOT$1"; then ok "$1"; else bad "missing $1"; fi; }

# Inside the target root, imports are the real test: a module can be listed in a
# package and still fail to import, which is exactly how the app set shipped
# without the toolkit it is written against.
imports() {
  local label="$1" code="$2"
  if as_root chroot "$TARGET_ROOT" /usr/bin/python3 -c "$code" >/dev/null 2>&1; then
    ok "$label"
  else
    bad "$label (python import failed inside the image)"
  fi
}

printf 'verify-rootfs-desktop: checking %s\n' "$TARGET_ROOT"

# 1. The toolkit every first-party app is written against.
imports "PySide6 QtCore/QtGui/QtWidgets" \
  'import PySide6.QtCore, PySide6.QtGui, PySide6.QtWidgets'
imports "PySide6 QtQml/QtQuick" 'import PySide6.QtQml, PySide6.QtQuick'

# 2. The panel is a GTK 3 application on gtk-layer-shell.
imports "Gtk 3 for the panel" \
  'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk'
imports "gtk-layer-shell for the panel" \
  'import gi; gi.require_version("GtkLayerShell", "0.1"); from gi.repository import GtkLayerShell'

# 3. Icons: GTK ignores an icon directory that has no index.theme, and an SVG
#    icon needs librsvg's gdk-pixbuf loader to load at all.
have /usr/share/icons/hicolor/index.theme
loader="$(find "$TARGET_ROOT/usr/lib" -name 'libpixbufloader-svg.so' 2>/dev/null | head -1)"
if [[ -n "$loader" ]]; then ok "SVG pixbuf loader (${loader#"$TARGET_ROOT"} )"; else bad "no SVG pixbuf loader (icons and wallpaper stay blank)"; fi

# 4. The session: entry file, launcher, panel, compositor and wallpaper.
have /usr/share/wayland-sessions/zaod.desktop
have /usr/local/bin/zaod-session
have /usr/local/bin/zaod-panel
for binary in labwc swaybg foot thunar; do
  if as_root test -x "$TARGET_ROOT/usr/bin/$binary"; then ok "$binary"; else bad "missing /usr/bin/$binary"; fi
done

mapfile -t wallpapers < <(as_root grep -ho '/usr/share/wallpapers/[^ ]*' \
  "$TARGET_ROOT/etc/xdg/labwc/autostart" 2>/dev/null | sort -u)
if (( ${#wallpapers[@]} == 0 )); then
  bad "the session starts no wallpaper"
fi
for wallpaper in "${wallpapers[@]}"; do
  if as_root test -s "$TARGET_ROOT$wallpaper"; then ok "$wallpaper"; else bad "missing wallpaper $wallpaper"; fi
done

# 5. Every launcher entry has to point at a program that exists, and its icon at
#    a file that exists, or the app grid is a column of blank squares.
entry_count=0
while IFS= read -r entry; do
  [[ -n "$entry" ]] || continue
  entry_count=$((entry_count + 1))
  exec_line="$(as_root sed -n 's/^Exec=//p' "$TARGET_ROOT$entry" 2>/dev/null | head -1 || true)"
  [[ -n "$exec_line" ]] || { bad "$entry has no Exec line"; continue; }
  program="${exec_line%% *}"
  if [[ "$program" == /usr/bin/python3 ]]; then
    script="$(printf '%s\n' "$exec_line" | awk '{print $2}')"
    if as_root test -f "$TARGET_ROOT$script"; then ok "$entry -> $script"; else bad "$entry runs $script, which is not in the image"; fi
  elif as_root test -x "$TARGET_ROOT$program"; then
    ok "$entry -> $program"
  else
    bad "$entry runs $program, which is not in the image"
  fi
  icon="$(as_root sed -n 's/^Icon=//p' "$TARGET_ROOT$entry" | head -1)"
  if [[ -n "$icon" ]]; then
    if [[ "$icon" == /* ]]; then
      if as_root test -s "$TARGET_ROOT$icon"; then
        ok "  icon $icon"
      else
        bad "  icon $icon is missing"
      fi
    elif as_root find "$TARGET_ROOT/usr/share/icons" -path "*/apps/${icon}.*" -print -quit 2>/dev/null | grep -q .; then
      ok "  icon $icon"
    elif as_root test -s "$TARGET_ROOT/usr/share/pixmaps/$icon.svg" || as_root test -s "$TARGET_ROOT/usr/share/pixmaps/$icon.png"; then
      ok "  icon $icon (pixmaps)"
    else
      bad "$entry wants icon $icon, which is not installed"
    fi
  fi
done < <(find "$TARGET_ROOT/usr/share/applications" -maxdepth 1 -name '*.desktop' -printf '/usr/share/applications/%f\n' 2>/dev/null | sort)
if (( entry_count == 0 )); then
  bad "the image has no launcher entries at all"
fi
printf 'verify-rootfs-desktop: %d launcher entries checked\n' "$entry_count"

if (( FAILED )); then
  printf 'verify-rootfs-desktop: FAIL\n' >&2
  exit 1
fi
printf 'verify-rootfs-desktop: PASS\n'
