#!/bin/bash
# Build every package and publish a signed store index.
# Usage: repo/build-store.sh path/to/store.key
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/.." && pwd)
key=${1:?usage: repo/build-store.sh path/to/store.key}
out="$root/build/out/store"

"$root/apps/build-all.sh" "$key"
python3 "$root/apps/firefox/build.py" --key "$key" --offline

# Publish from a clean directory so a package removed from the tree cannot linger.
mkdir -p "$out"
find "$out" -mindepth 1 -delete

shopt -s nullglob
for package in "$root"/build/out/apps/*.zaod; do
  case "$(basename "$package")" in
    # First-boot setup is part of the image, not something a user installs.
    # Studio stays optional: 'make studio' publishes it separately to
    # build/out/optional, and the shipped image has no Studio by default.
    # Built packages are named by short app name, e.g. oobe-1.0.0.zaod.
    oobe-*|studio-*) continue ;;
  esac
  cp "$package" "$out/"
done
shopt -u nullglob

"$root/zaod/bin/zaod" repo build "$out" --name core --key "$key"

# Publish the matching public key: an index that cannot be trusted is useless to
# an installed system, and the installer registers exactly this file.
mkdir -p "$out/keys"
PYTHONPATH="$root/zaod" python3 - "$key" "$out/keys/store.pub" <<'PUBKEY'
import sys
from pathlib import Path

from zaodlib import keys

keypair = keys.load_private_key(Path(sys.argv[1]))
Path(sys.argv[2]).write_text(keypair.export_public(), encoding="utf-8")
print(f"published public key {keypair.key_id} -> {sys.argv[2]}")
PUBKEY

printf 'store index: %s\n' "$out/index.json"
python3 - "$out/index.json" <<'SUMMARY'
import json
import sys

index = json.load(open(sys.argv[1]))
total = sum(package["size"] for package in index["packages"])
print(f"{len(index['packages'])} packages, {total / (1024 ** 2):.1f} MiB total")
SUMMARY
