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
loader="$(find "$TARGET_ROOT/usr/lib" -name 'libpixbufloader*svg.so' 2>/dev/null | head -1)"
if [[ -n "$loader" ]]; then ok "SVG pixbuf loader (${loader#"$TARGET_ROOT"} )"; else bad "no SVG pixbuf loader (icons and wallpaper stay blank)"; fi

# 3a. The Zaod package system behind the Store and the zaod CLI.
have /usr/lib/zaod/zaodlib/__init__.py
have /usr/bin/zaod
if as_root test -x "$TARGET_ROOT/usr/bin/zaod" && \
   as_root chroot "$TARGET_ROOT" /usr/bin/zaod --help >/dev/null 2>&1; then
  ok "zaod --help runs"
else
  bad "the zaod CLI does not run inside the image"
fi

# 3b. The login theme: SDDM prints its red "the current theme cannot be loaded"
#     banner over the login box when a single property is unknown, so the theme
#     may only use Qt Quick core modules (Controls took `contentItem` away).
theme_qml="$TARGET_ROOT/usr/share/sddm/themes/zaod/Main.qml"
if as_root test -s "$theme_qml"; then
  ok "/usr/share/sddm/themes/zaod/Main.qml"
  if as_root grep -v '^[[:space:]]*//' "$theme_qml" | grep -Eq "QtQuick.Controls|SddmComponents"; then
    bad "the login theme imports a module whose components shadow the Qt Quick types it styles"
  else
    ok "the login theme stays inside Qt Quick core"
  fi
else
  bad "missing /usr/share/sddm/themes/zaod/Main.qml"
fi

# 3c. The built-in wallpaper collection and the login background.
wall_dir="$TARGET_ROOT/usr/share/wallpapers/zaod/collection"
count=0
if as_root test -d "$wall_dir"; then
  count=$(as_root find "$wall_dir" -maxdepth 1 -name '*.jpg' | wc -l)
fi
if [ "$count" -ge 9 ]; then
  ok "$count built-in wallpapers"
else
  bad "only $count built-in wallpapers in /usr/share/wallpapers/zaod/collection (want 9)"
fi
have /usr/share/wallpapers/zaod/collection/zaod-lake-louise.jpg
have /usr/share/doc/zaod/wallpaper-credits.md
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-wallpaper"; then
  ok "zaod-wallpaper is installed"
else
  bad "zaod-wallpaper is missing"
fi
have /usr/share/sddm/themes/zaod/background.jpg

# 3d. The built-in web apps, the browser they open in, and Studio.
have /usr/share/zaod/webapps.json
if as_root test -x "$TARGET_ROOT/usr/bin/chromium"; then
  ok "chromium is installed"
else
  bad "chromium is missing, so the web apps cannot open"
fi
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-cloud"; then
  ok "zaod-cloud is installed (account backup and a second computer)"
else
  bad "zaod-cloud is missing: accounts could not be backed up"
fi
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-update"; then
  ok "zaod-update is installed (signed updates without reinstalling)"
else
  bad "zaod-update is missing: an installed system could not receive fixes"
fi
if as_root test -f "$TARGET_ROOT/etc/zaod/update-channel.json"; then
  ok "the update channel is configured"
else
  bad "no update channel is configured in the image"
fi
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-hub"; then
  ok "zaod-hub (the local account backend) is installed"
else
  bad "zaod-hub is missing: Studio and the store would have no accounts"
fi
if as_root test -f "$TARGET_ROOT/usr/lib/zaod/zaodhub.py"; then
  ok "the apps' hub client is installed"
else
  bad "zaodhub.py is missing from /usr/lib/zaod"
fi
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-webapp"; then
  ok "zaod-webapp is installed"
else
  bad "zaod-webapp is missing"
fi
for webapp in youtube whatsapp instagram facebook tiktok x; do
  have "/usr/share/zaod/optional/webapps/zaod-web-$webapp.desktop"
done
have /usr/share/zaod/optional/webapps/webapps.json
have /usr/share/zaod/optional/apps/studio/payload/main.py
if as_root test -x "$TARGET_ROOT/usr/local/bin/zaod-open"; then
  ok "zaod-open is installed"
else
  bad "zaod-open is missing, so the Super+key bindings would do nothing"
fi
# Touchpad taps and two-finger right click are off in libinput's defaults; on a
# laptop that is indistinguishable from a broken mouse.
if as_root grep -q "<tap>yes</tap>" "$TARGET_ROOT/etc/xdg/labwc/rc.xml" 2>/dev/null; then
  ok "tap-to-click is enabled for touchpads"
else
  bad "rc.xml does not enable tap-to-click"
fi
if as_root test -f "$TARGET_ROOT/usr/share/applications/zaod-web-youtube.desktop"; then
  bad "a social web app is installed in the launcher without being asked for"
else
  ok "no social web app is installed by default"
fi

# 3e. The wallpapers have to be the full-size ones plus thumbnails for the picker.
thumbs=$(as_root find "$TARGET_ROOT/usr/share/wallpapers/zaod/collection/thumbs" \
  -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l)
if [ "$thumbs" -ge 9 ]; then ok "$thumbs wallpaper thumbnails"; else bad "only $thumbs wallpaper thumbnails"; fi
big=$(as_root find "$TARGET_ROOT/usr/share/wallpapers/zaod/collection" -maxdepth 1 -name 'zaod-lake-louise.jpg' \
  -size +400k 2>/dev/null | wc -l)
if [ "$big" -ge 1 ]; then ok "the default wallpaper is the full-size 8K file"; else bad "the default wallpaper is missing or small"; fi

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
  zaod_entry="$(as_root sed -n 's/^X-Zaod-AppId=//p' "$TARGET_ROOT$entry" 2>/dev/null | head -1 || true)"
  exec_line="$(as_root sed -n 's/^Exec=//p' "$TARGET_ROOT$entry" 2>/dev/null | head -1 || true)"
  [[ -n "$exec_line" ]] || { bad "$entry has no Exec line"; continue; }
  program="${exec_line%% *}"
  # Exec= may name a bare command that the image finds on PATH.
  if [[ "$program" != /* ]]; then
    resolved=""
    for dir in /usr/local/bin /usr/bin /usr/sbin /bin /sbin; do
      if as_root test -x "$TARGET_ROOT$dir/$program"; then resolved="$dir/$program"; break; fi
    done
    program="${resolved:-$program}"
  fi
  if [[ "$program" == /usr/bin/python3 || "$program" == /usr/local/bin/zaod-run ]]; then
    # zaod-run APP-ID python3 SCRIPT: the last field is the script.
    script="$(printf '%s\n' "$exec_line" | awk '{print $NF}')"
    if as_root test -f "$TARGET_ROOT$script"; then ok "$entry -> $script"; else bad "$entry runs $script, which is not in the image"; fi
  elif as_root test -x "$TARGET_ROOT$program"; then
    ok "$entry -> $program"
  elif [[ -n "$zaod_entry" ]]; then
    bad "$entry runs $program, which is not in the image"
  else
    # A package's own entry may name an alternative this image does not ship;
    # only the launchers Zaod installs have to work.
    printf '  note %s names %s, not installed\n' "$entry" "$program"
  fi
  # Only the launchers Zaod installs are held to the icon rule; a package's own
  # entry may name a theme icon we are not required to ship.
  icon="$(as_root sed -n 's/^Icon=//p' "$TARGET_ROOT$entry" 2>/dev/null | head -1 || true)"
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
    elif [[ -n "$zaod_entry" ]]; then
      bad "$entry wants icon $icon, which is not installed"
    else
      printf '  note %s names theme icon %s\n' "$entry" "$icon"
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
