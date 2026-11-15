#!/usr/bin/env bash
# Assemble a release directory: artifacts, SHA256SUMS, release.json and notes.
#
#   scripts/release.sh 1.0.0 --key build/keys/release.key
#   scripts/release.sh 1.0.0 --store-only
#
# The ISO is required unless --store-only is given, because a release without an
# image is a mistake rather than a variant.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/.." && pwd)

version=""
key=""
store_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --key) key="${2:?--key needs a path}"; shift 2 ;;
    --store-only) store_only=true; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) version="$1"; shift ;;
  esac
done

if [ -z "$version" ]; then
  echo "usage: scripts/release.sh VERSION [--key KEY] [--store-only]" >&2
  exit 2
fi

out="$root/build/release/$version"
mkdir -p "$out"
find "$out" -mindepth 1 -delete
# -delete removes the store directory too, so recreate it afterwards.
mkdir -p "$out/store"

if [ "$store_only" = false ]; then
  iso="$root/build/out/zaod-os-$version-amd64.iso"
  if [ ! -f "$iso" ]; then
    echo "error: no ISO at $iso" >&2
    echo "       build the image first with 'make iso', or use --store-only for a store release" >&2
    exit 2
  fi
  cp "$iso" "$out/"
fi

shopt -s nullglob
packages=("$root"/build/out/apps/*.zaod)
shopt -u nullglob
if [ ${#packages[@]} -eq 0 ]; then
  echo "error: no packages in build/out/apps; run 'make store-index' first" >&2
  exit 2
fi
cp "${packages[@]}" "$out/store/"
# Re-sign the index with the release key, so the index, its signature and the
# shipped public key all belong together.
if [ -n "$key" ]; then
  "$root/zaod/bin/zaod" repo build "$root/build/out/store" --name "${REPO_NAME:-official}" --key "$key" >/dev/null
fi
for extra in index.json index.json.sig; do
  if [ -f "$root/build/out/store/$extra" ]; then
    cp "$root/build/out/store/$extra" "$out/store/"
  elif [ -f "$root/repo/build/$extra" ]; then
    cp "$root/repo/build/$extra" "$out/store/"
  else
    echo "error: $extra is missing; run 'make store-index ZAOD_KEY=...' first" >&2
    exit 2
  fi
done
# Ship the store public key: an installed system cannot verify index.json.sig
# without it, and installer/modules/zaod-repo.conf expects keys/store.pub.
if [ -f "$root/build/out/store/keys/store.pub" ]; then
  mkdir -p "$out/store/keys"
  cp "$root/build/out/store/keys/store.pub" "$out/store/keys/store.pub"
fi
mkdir -p "$out/store/keys"
if [ -n "$key" ] && [ -f "${key%.key}.pub" ]; then
  cp "${key%.key}.pub" "$out/store/keys/store.pub"
fi
# Packages are signed by whoever built them, so ship those public keys as well;
# the signed index still pins every package hash.
for pub in "$root"/build/out/apps/*.pub; do
  [ -f "$pub" ] && cp "$pub" "$out/store/keys/$(basename "$pub")"
done

python3 - "$root" "$out" "$version" "$key" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root, out, version, key_path = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
sys.path.insert(0, str(root / "zaod"))

from zaodlib import keys, util  # noqa: E402

offer = [
    f"Zaod OS {version} source offer",
    "",
    "The complete corresponding source for every binary in this release is available:",
    "",
    f"  git clone https://github.com/zaodtechai-stack/zaod-os && git checkout v{version}",
    "",
    "Third-party components and their source locations are listed in docs/licenses.md:",
    "- Linux kernel: pinned tarball fetched by `make fetch`",
    "- Debian base packages: Debian archive source for the pinned suite",
    "- Plasma, Qt, Python, PySide6: upstream source packages of the pinned versions",
    "- Firefox ESR: the unmodified Mozilla tarball plus distribution/policies.json",
    "",
    "This offer is valid for as long as this release is distributed.",
]
(out / "SOURCE-OFFER.txt").write_text("\n".join(offer) + "\n", encoding="utf-8")

artifacts = []
for path in sorted(out.rglob("*")):
    if path.is_file():
        artifacts.append(
            {
                "name": str(path.relative_to(out)),
                "sha256": util.sha256_file(path),
                "size": path.stat().st_size,
            }
        )

sums = "".join(f"{item['sha256']}  {item['name']}\n" for item in artifacts)
(out / "SHA256SUMS").write_text(sums, encoding="utf-8")

document = {
    "version": version,
    "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "artifacts": artifacts,
}
document_bytes = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
(out / "release.json").write_bytes(document_bytes)

if key_path:
    key = keys.load_private_key(Path(key_path))
    signature = keys.signature_document(key, document_bytes)
    (out / "release.json.sig").write_text(
        json.dumps(signature, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"signed with {key.key_id}")
else:
    print("release.json is unsigned (no --key given)")

packages = [item["name"] for item in artifacts if item["name"].endswith(".zaod")]
notes = [
    f"# Zaod OS {version}",
    "",
    f"- Released: {document['created']}",
    f"- ISO: zaod-os-{version}-amd64.iso (UEFI first, legacy BIOS best effort)",
    f"- Store packages in this release: {len(packages)}",
    "",
    "## Verify",
    "",
    "```",
    "sha256sum -c SHA256SUMS",
    "zaod key trust store/keys/store.pub",
    "```",
    "",
    "## Packages",
    "",
]
notes += [f"- `{name}`" for name in packages]
(out / "RELEASE-NOTES.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
print(f"wrote {len(artifacts)} artifacts to {out}")
PY

echo "release $version ready in $out"
