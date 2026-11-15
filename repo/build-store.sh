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

mkdir -p "$out"
cp "$root"/build/out/apps/*.zaod "$out/"
"$root/zaod/bin/zaod" repo build "$out" --name core --key "$key"
printf 'store index: %s\n' "$out/index.json"
python3 - "$out/index.json" <<'SUMMARY'
import json
import sys

index = json.load(open(sys.argv[1]))
total = sum(package["size"] for package in index["packages"])
print(f"{len(index['packages'])} packages, {total / (1024 ** 2):.1f} MiB total")
SUMMARY
