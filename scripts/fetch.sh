#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="${DEST_DIR:-build/cache}"
KERNEL_VERSION="${KERNEL_VERSION:-6.18.63}"
BASE_URL="https://cdn.kernel.org/pub/linux/kernel/v6.x"

mkdir -p "$DEST_DIR"

curl -fL --retry 3 --retry-delay 2 "$BASE_URL/linux-$KERNEL_VERSION.tar.xz" -o "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
curl -fL --retry 3 --retry-delay 2 "$BASE_URL/sha256sums.asc" -o "$DEST_DIR/sha256sums.asc"

gpg --batch --keyserver hkp://keyserver.ubuntu.com --recv-keys B8868C80BA62A1FFFAF5FDA9632D3A06589DA6B1 >/dev/null 2>&1

gpg --batch --verify "$DEST_DIR/sha256sums.asc" >/dev/null
EXPECTED_SUM="$(grep -E "linux-$KERNEL_VERSION.tar.xz" "$DEST_DIR/sha256sums.asc" | awk '{print $1}')"
ACTUAL_SUM="$(sha256sum "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz" | awk '{print $1}')"

if [[ "$ACTUAL_SUM" != "$EXPECTED_SUM" ]]; then
  printf 'Checksum mismatch for linux-%s.tar.xz\nExpected: %s\nActual: %s\n' "$KERNEL_VERSION" "$EXPECTED_SUM" "$ACTUAL_SUM" >&2
  exit 1
fi

sha256sum "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz" > "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz.sha256"

ls -lh "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
printf 'Kernel tarball verified and recorded: %s\n' "$DEST_DIR/linux-$KERNEL_VERSION.tar.xz"
