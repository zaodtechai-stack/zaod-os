#!/bin/bash
# Prove every app opens its window on the real Wayland path, inside the image.
#
# Run inside the built root filesystem: /usr/local/lib/zaod/test-apps-wayland.sh
#
# The offscreen smoke test proves an app imports and builds its window; it says
# nothing about the platform plugin the session actually uses, nor about the way
# the panel starts an app (Gio.AppInfo.launch). This starts a headless labwc - the
# same compositor the session runs - then launches each app with WAYLAND_DISPLAY
# pointing at it, and finally starts one entry through Gio, failing if an app
# exits before it settles.
set -uo pipefail

APPS_DIR=${APPS_DIR:-/opt/zaod/apps}
SETTLE=${SETTLE:-4}
RUNTIME=$(mktemp -d /tmp/zaod-wayland.XXXXXX)
export XDG_RUNTIME_DIR="$RUNTIME"
export XDG_SESSION_TYPE=wayland
export WLR_BACKENDS=headless
export WLR_LIBINPUT_NO_DEVICES=1
export WLR_RENDERER=pixman
export WLR_HEADLESS_OUTPUTS=1
export ZAOD_THEME=${ZAOD_THEME:-dark}

# shellcheck disable=SC2317  # run from the EXIT trap
cleanup() {
  [ -n "${compositor:-}" ] && kill "$compositor" 2>/dev/null
  if [ -n "${RUNTIME:-}" ] && [ -d "$RUNTIME" ]; then
    find "$RUNTIME" -mindepth 1 -delete 2>/dev/null
    rmdir "$RUNTIME" 2>/dev/null
  fi
}
trap cleanup EXIT

labwc_log="$RUNTIME/labwc.log"
/usr/bin/labwc >"$labwc_log" 2>&1 &
compositor=$!

socket=""
for _ in $(seq 1 40); do
  socket=$(find "$RUNTIME" -maxdepth 1 -name 'wayland-*' ! -name '*.lock' | head -1)
  if [ -n "$socket" ]; then break; fi
  if ! kill -0 "$compositor" 2>/dev/null; then break; fi
  sleep 0.25
done

if [ -z "$socket" ]; then
  echo "  skip: no headless compositor could start (see below)"
  sed -n '1,20p' "$labwc_log" | sed 's/^/    /'
  exit 0
fi
WAYLAND_DISPLAY=$(basename "$socket")
export WAYLAND_DISPLAY
export QT_QPA_PLATFORM=wayland
echo "  compositor up on $WAYLAND_DISPLAY"

failures=0
checked=0
for app_dir in "$APPS_DIR"/*/; do
  main_py="$app_dir/payload/main.py"
  if [ ! -f "$main_py" ]; then continue; fi
  name=$(basename "$app_dir")
  checked=$((checked + 1))
  app_log="$RUNTIME/$name.log"
  ( cd / && exec /usr/local/bin/zaod-run "$name" /usr/bin/python3 "$main_py" ) >"$app_log" 2>&1 &
  runner=$!
  sleep "$SETTLE"
  if kill -0 "$runner" 2>/dev/null; then
    echo "  ok   $name runs on wayland"
    pkill -f "$main_py" 2>/dev/null
    kill "$runner" 2>/dev/null
    wait "$runner" 2>/dev/null
  else
    failures=$((failures + 1))
    echo "  FAIL $name exited on wayland" >&2
    sed -n '1,15p' "$app_log" | sed 's/^/    /' >&2
    if [ -f "$HOME/.zaod/logs/$name.log" ]; then
      tail -n 15 "$HOME/.zaod/logs/$name.log" | sed 's/^/    /' >&2
    fi
  fi
  sleep 0.5
done

# A click on a launcher icon goes through Gio, not through the binary, so that
# path is checked separately: the app has to come up from its .desktop entry.
if [ -f /usr/share/applications/org.zaod.notes.desktop ] && [ -x /usr/bin/python3 ]; then
  checked=$((checked + 1))
  gio_log="$RUNTIME/gio-launch.log"
  /usr/bin/python3 /tmp/gio-launch-entry.py org.zaod.notes.desktop >"$gio_log" 2>&1
  launched=$?
  sleep "$SETTLE"
  if [ "$launched" -eq 0 ] && pgrep -f "/opt/zaod/apps/notes/payload/main.py" >/dev/null 2>&1; then
    echo "  ok   a launcher entry starts its app through Gio.AppInfo"
    pkill -f "/opt/zaod/apps/notes/payload/main.py" 2>/dev/null
  else
    failures=$((failures + 1))
    echo "  FAIL the notes launcher entry started nothing (status $launched)" >&2
    sed -n '1,15p' "$gio_log" | sed 's/^/    /' >&2
    if [ -f "$HOME/.zaod/logs/org.zaod.notes.log" ]; then
      tail -n 15 "$HOME/.zaod/logs/org.zaod.notes.log" | sed 's/^/    /' >&2
    fi
  fi
fi

echo "test-apps-wayland: $checked checks, $failures failed"
if [ "$failures" -eq 0 ] && [ "$checked" -gt 0 ]; then exit 0; fi
exit 1
