#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_URL="https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git"
REPO_COMMIT="2b2c1f39d7ae274bfe56d829e62d3993249e3a82"
SRC_DIR="${FIRMWARE_SRC_DIR:-$ROOT_DIR/build/cache/linux-firmware-src}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/build/out/kernel}"
ARCHIVE="$OUT_DIR/firmware.tar.xz"

mkdir -p "$(dirname "$SRC_DIR")" "$OUT_DIR"
if [[ ! -d "$SRC_DIR/.git" ]]; then
  git clone --filter=blob:none --no-checkout --depth=1 --branch=main "$REPO_URL" "$SRC_DIR"
fi

git -C "$SRC_DIR" sparse-checkout init --no-cone
git -C "$SRC_DIR" sparse-checkout set --no-cone \
  /LICENSE /LICENSE-CRITERIA.md /LICENSES/ /WHENCE /amdgpu/ /ath3k-1.fw \
  /ath9k_htc/ /ath10k/ /ath11k/ /brcm/ /i915/ /intel/ /mediatek/ \
  /radeon/ /rtl_bt/ /rtl_nic/ /rtlwifi/ /rtw88/ /rtw89/
if ! git -C "$SRC_DIR" cat-file -e "$REPO_COMMIT^{commit}" 2>/dev/null; then
  git -C "$SRC_DIR" fetch --filter=blob:none --depth=1 origin "$REPO_COMMIT"
fi
git -C "$SRC_DIR" checkout --detach "$REPO_COMMIT"

actual_commit="$(git -C "$SRC_DIR" rev-parse HEAD)"
if [[ "$actual_commit" != "$REPO_COMMIT" ]]; then
  printf 'Firmware revision mismatch: %s\n' "$actual_commit" >&2
  exit 1
fi

printf '%s\n' "$actual_commit" > "$OUT_DIR/firmware-source-commit.txt"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
  --wildcards -cJf "$ARCHIVE" -C "$SRC_DIR" \
  LICENSE LICENSE-CRITERIA.md LICENSES WHENCE amdgpu ath3k-1.fw ath9k_htc \
  ath10k ath11k brcm i915 intel mediatek radeon rtl_bt rtl_nic rtlwifi rtw88 rtw89
sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
ls -lh "$ARCHIVE"
printf 'Firmware source commit: %s\n' "$actual_commit"
printf 'Firmware archive: %s\n' "$ARCHIVE"