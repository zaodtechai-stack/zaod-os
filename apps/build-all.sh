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

python3 - "$stage_root" <<'CLEAN'
import pathlib
import shutil
import sys

target = pathlib.Path(sys.argv[1])
if target.is_dir():
    shutil.rmtree(target)
CLEAN
mkdir -p "$out" "$stage_root"

for directory in "$here"/*/; do
  [ -f "$directory/MANIFEST.json" ] || continue
  slug=$(basename "$directory")
  stage="$stage_root/$slug"
  mkdir -p "$stage/payload/lib"
  cp "$directory/MANIFEST.json" "$stage/MANIFEST.json"
  cp "$directory/icon.svg" "$stage/icon.svg"
  cp -r "$directory/payload/." "$stage/payload/"
  cp "$here/lib/zaodapp.py" "$stage/payload/lib/zaodapp.py"
  version=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$stage/MANIFEST.json")
  target="$out/$slug-$version.zaod"
  if [ -n "$key" ]; then
    "$zaod_cli" pack "$stage" -o "$target" --key "$key" >/dev/null
  else
    "$zaod_cli" pack "$stage" -o "$target" >/dev/null
  fi
  printf 'built %s (%s)\n' "$(basename "$target")" "$(du -h "$target" | cut -f1)"
done
