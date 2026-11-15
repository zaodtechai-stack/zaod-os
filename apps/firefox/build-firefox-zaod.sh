#!/usr/bin/env bash
# Repackage Firefox ESR as a signed .zaod package.
#
#   apps/firefox/build-firefox-zaod.sh --check     # verify inputs, write nothing
#   apps/firefox/build-firefox-zaod.sh             # download, verify, pack
#
# The upstream tarball is never trusted on its name alone: it is checked against
# Mozilla's own SHA512SUMS before anything is unpacked.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

VERSION="${VERSION:-153.7.0esr}"
CHANNEL="${CHANNEL:-stable}"
CACHE_DIR="${CACHE_DIR:-build/cache}"
WORK="${WORK:-build/firefox}"
OUT_DIR="${OUT_DIR:-build/apps}"
BASE_URL="https://ftp.mozilla.org/pub/firefox/releases"
TARBALL="firefox-${VERSION}.tar.xz"
ARCHIVE_URL="$BASE_URL/$VERSION/linux-x86_64/en-US/$TARBALL"
SUMS_URL="$BASE_URL/$VERSION/SHA512SUMS"
SIGNING_KEY="${SIGNING_KEY:-}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

say() { printf '\033[1;36m[firefox]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[firefox] %s\033[0m\n' "$*" >&2; exit 1; }

for tool in curl sha512sum tar python3; do
  command -v "$tool" >/dev/null || fail "$tool is required"
done
[[ -f apps/firefox/policies.json ]] || fail "apps/firefox/policies.json is missing"
[[ -f apps/firefox/os.zaod.firefox.desktop ]] || fail "the desktop entry is missing"
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' apps/firefox/policies.json \
  || fail "policies.json is not valid JSON"

printf '[firefox] version %s, channel %s\n  archive %s\n  sums    %s\n' \
  "$VERSION" "$CHANNEL" "$ARCHIVE_URL" "$SUMS_URL"

if (( CHECK )); then
  printf '[firefox] --check done, nothing downloaded\n'
  exit 0
fi

mkdir -p "$CACHE_DIR" "$OUT_DIR"
say "fetching the checksum list"
curl -fsSL "$SUMS_URL" -o "$CACHE_DIR/$VERSION.SHA512SUMS" \
  || fail "cannot fetch $SUMS_URL"

escaped_version="${VERSION//./\\.}"
expected="$(grep -E "linux-x86_64/en-US/firefox-${escaped_version}\.tar\.xz$" \
  "$CACHE_DIR/$VERSION.SHA512SUMS" | awk '{print $1}')"
[[ -n "$expected" ]] || fail "$TARBALL is not listed in SHA512SUMS for $VERSION"

if [[ ! -f "$CACHE_DIR/$TARBALL" ]]; then
  say "downloading $TARBALL (about 82 MB)"
  curl -fL --progress-bar "$ARCHIVE_URL" -o "$CACHE_DIR/$TARBALL.part" \
    || fail "download failed"
  mv "$CACHE_DIR/$TARBALL.part" "$CACHE_DIR/$TARBALL"
fi

actual="$(sha512sum "$CACHE_DIR/$TARBALL" | awk '{print $1}')"
[[ "$actual" == "$expected" ]] \
  || fail "SHA-512 mismatch for $TARBALL (expected $expected, got $actual)"
say "SHA-512 verified"

[[ -d "$WORK" ]] && chmod -R u+w "$WORK" && rm -rf "$WORK"
mkdir -p "$WORK/payload"
say "unpacking into the payload tree"
tar -xJf "$CACHE_DIR/$TARBALL" -C "$WORK/payload"
[[ -x "$WORK/payload/firefox/firefox" ]] || fail "the archive does not contain firefox/firefox"

mkdir -p "$WORK/payload/firefox/distribution"
install -m 0644 apps/firefox/policies.json "$WORK/payload/firefox/distribution/policies.json"
printf 'Zaod OS Firefox build %s\nSource: %s\nSHA-512: %s\n' \
  "$VERSION" "$ARCHIVE_URL" "$expected" > "$WORK/payload/firefox/ZAOD-PROVENANCE.txt"

install -m 0644 apps/firefox/os.zaod.firefox.desktop "$WORK/os.zaod.firefox.desktop"
if [[ -f "$WORK/payload/firefox/browser/chrome/icons/default/default128.png" ]]; then
  install -m 0644 "$WORK/payload/firefox/browser/chrome/icons/default/default128.png" "$WORK/icon.png"
else
  printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>\n' > "$WORK/icon.svg"
fi

python3 - "$WORK" "$VERSION" "$CHANNEL" <<'PY'
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
version = sys.argv[2]
channel = sys.argv[3]
manifest = {
    "format": 1,
    "id": "os.zaod.firefox",
    "name": "Firefox",
    "version": version.split("esr")[0],
    "kind": "app",
    "arch": "x86_64",
    "min_os": "1.0.0",
    "description": "Firefox ESR, repackaged for Zaod OS with telemetry, Pocket and "
    "studies disabled and the password manager off.",
    "license": "MPL-2.0",
    "author": {"name": "Mozilla", "email": "security@mozilla.org"},
    "entry": {"exec": "payload/firefox/firefox"},
    "categories": ["network", "web"],
    "mime_types": ["text/html", "x-scheme-handler/http", "x-scheme-handler/https"],
    "icon": "icon.png",
    "permissions": {
        "network": True,
        "audio": True,
        "devices": ["dri"],
        "home_read": True,
        "home_write": True,
    },
}
(work / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"[firefox] manifest written for {manifest['id']} {manifest['version']} on {channel}")
PY

PACK_ARGS=(pack "$WORK" -o "$OUT_DIR/os.zaod.firefox-${VERSION}.zaod")
if [[ -n "$SIGNING_KEY" ]]; then
  [[ -f "$SIGNING_KEY" ]] || fail "signing key $SIGNING_KEY does not exist"
  PACK_ARGS+=(--sign-with "$SIGNING_KEY")
else
  say "warning: no SIGNING_KEY set, writing an unsigned package"
fi

python3 -m zaod.cli "${PACK_ARGS[@]}"
say "wrote $OUT_DIR/os.zaod.firefox-${VERSION}.zaod"
