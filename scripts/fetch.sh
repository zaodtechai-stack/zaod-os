#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="${DEST_DIR:-build/cache}"
KERNEL_VERSION="${KERNEL_VERSION:-6.18.63}"
KEY_FPR="B8868C80BA62A1FFFAF5FDA9632D3A06589DA6B1"
BASE_URL="${BASE_URL:-https://cdn.kernel.org/pub/linux/kernel/v6.x}"

mkdir -p "$DEST_DIR"

curl -fL --retry 3 --retry-delay 2 "$BASE_URL/linux-$KERNEL_VERSION.tar.xz" -o "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
curl -fL --retry 3 --retry-delay 2 "$BASE_URL/sha256sums.asc" -o "$DEST_DIR/sha256sums.asc"

# The kernel.org checksum autosigner key is needed to verify sha256sums.asc.
# The hkp/hkps keyserver protocol uses port 11371 and is blocked on many CI
# networks, so fall back to the same keyserver's HTTPS web API.
if ! gpg --batch --list-keys "$KEY_FPR" >/dev/null 2>&1; then
  gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$KEY_FPR" >/dev/null 2>&1 || true
fi
if ! gpg --batch --list-keys "$KEY_FPR" >/dev/null 2>&1; then
  key_file="$(mktemp)"
  if curl -fsSL --retry 3 --retry-delay 2 \
    "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$KEY_FPR" -o "$key_file"; then
    gpg --batch --import "$key_file" >/dev/null 2>&1 || true
  fi
  rm -f "$key_file"
fi
if ! gpg --batch --list-keys "$KEY_FPR" >/dev/null 2>&1; then
  printf 'Cannot obtain the kernel.org checksum autosigner key %s\n' "$KEY_FPR" >&2
  printf 'Import it manually (gpg --import key.asc) and re-run make fetch.\n' >&2
  exit 1
fi

gpg --batch --verify "$DEST_DIR/sha256sums.asc" >/dev/null 2>&1
EXPECTED_SUM="$(grep -E "linux-$KERNEL_VERSION\.tar\.xz" "$DEST_DIR/sha256sums.asc" | awk '{print $1}' | head -n 1)"
if [[ -z "$EXPECTED_SUM" ]]; then
  printf 'linux-%s.tar.xz is not listed in the signed sha256sums.asc\n' "$KERNEL_VERSION" >&2
  exit 1
fi
ACTUAL_SUM="$(sha256sum "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz" | awk '{print $1}')"

if [[ "$ACTUAL_SUM" != "$EXPECTED_SUM" ]]; then
  printf 'Checksum mismatch for linux-%s.tar.xz\nExpected: %s\nActual: %s\n' "$KERNEL_VERSION" "$EXPECTED_SUM" "$ACTUAL_SUM" >&2
  exit 1
fi

sha256sum "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz" > "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz.sha256"

ls -lh "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
printf 'Kernel tarball verified and recorded: %s\n' "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
printf 'PGP: sha256sums.asc signature by %s is valid; archive matches the signed checksum.\n' "$KEY_FPR"
