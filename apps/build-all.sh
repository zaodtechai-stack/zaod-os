#!/bin/bash
# Build every first-party app as a .zaod package and optionally sign it.
# Usage: apps/build-all.sh [path/to/signing.key]
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/.." && pwd)
out="$root/build/out/apps"
stage_root="$root/build/staging"
key=${1:-}
zaod_cli="$root/zaod/bin/zaod"

# Clean the output too: a package for an app that no longer builds must not
# linger in build/out/apps and keep getting published.
python3 - "$stage_root" "$out" <<'CLEAN'
import pathlib
import shutil
import sys

for argument in sys.argv[1:]:
    target = pathlib.Path(argument)
    if target.is_dir():
        shutil.rmtree(target)
CLEAN
mkdir -p "$out" "$stage_root"

for directory in "$here"/*/; do
  [ -f "$directory/MANIFEST.json" ] || continue
  # Apps with their own builder (e.g. Firefox) are packaged by that builder.
  [ -d "$directory/payload" ] || continue
  slug=$(basename "$directory")
  # Studio has its own builder and stays optional: 'make studio' writes it to
  # build/out/optional so the published store index never ships it.
  [ "$slug" = "studio" ] && continue
  stage="$stage_root/$slug"
  mkdir -p "$stage/payload/lib"
  cp "$directory/MANIFEST.json" "$stage/MANIFEST.json"
  cp "$directory/icon.svg" "$stage/icon.svg"
  cp -r "$directory/payload/." "$stage/payload/"
  cp "$here/lib/zaodapp.py" "$stage/payload/lib/zaodapp.py"
  [ -f "$stage/payload/main.py" ] && chmod +x "$stage/payload/main.py"
  version=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$stage/MANIFEST.json")
  target="$out/$slug-$version.zaod"
  if [ -n "$key" ]; then
    "$zaod_cli" pack "$stage" -o "$target" --key "$key" >/dev/null
  else
    "$zaod_cli" pack "$stage" -o "$target" >/dev/null
  fi
  printf 'built %s (%s)\n' "$(basename "$target")" "$(du -h "$target" | cut -f1)"
done
