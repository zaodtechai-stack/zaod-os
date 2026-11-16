#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_URL="https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git"
# The same repository behind the kernel.org CDN. A runner that cannot reach
# git.kernel.org (that happens: a clone sat on "Failed to connect ... port 443"
# for 135 s and failed a release after the source archive had already been
# verified) then gets a second transport instead of a dead job.
REPO_MIRROR_URL="https://mirrors.edge.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git"
REPO_COMMIT="2b2c1f39d7ae274bfe56d829e62d3993249e3a82"
SRC_DIR="${FIRMWARE_SRC_DIR:-$ROOT_DIR/build/cache/linux-firmware-src}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/build/out/kernel}"
ARCHIVE="$OUT_DIR/firmware.tar.xz"

mkdir -p "$(dirname "$SRC_DIR")" "$OUT_DIR"

clone_firmware() {
  local attempt url
  for attempt in 1 2 3; do
    for url in "$REPO_URL" "$REPO_MIRROR_URL"; do
      if git clone --filter=blob:none --no-checkout --depth=1 --branch=main \
           "$url" "$SRC_DIR"; then
        printf 'Firmware source cloned from %s\n' "$url"
        return 0
      fi
      rm -rf -- "$SRC_DIR"
      printf 'Firmware clone from %s failed (attempt %s/3)\n' "$url" "$attempt" >&2
    done
    sleep "$(( attempt * 15 ))"
  done
  return 1
}

if [[ ! -d "$SRC_DIR/.git" ]]; then
  clone_firmware || { printf 'cannot reach any linux-firmware mirror\n' >&2; exit 1; }
fi

git -C "$SRC_DIR" sparse-checkout init --no-cone
git -C "$SRC_DIR" sparse-checkout set --no-cone \
  /LICENSE /LICENSE-CRITERIA.md /LICENSES/ /WHENCE /amdgpu/ /ath3k-1.fw \
  /ath9k_htc/ /ath10k/ /ath11k/ /brcm/ /i915/ /intel/ /mediatek/ \
  /radeon/ /rtl_bt/ /rtl_nic/ /rtlwifi/ /rtw88/ /rtw89/
if ! git -C "$SRC_DIR" cat-file -e "$REPO_COMMIT^{commit}" 2>/dev/null; then
  fetched=0
  for attempt in 1 2 3; do
    if git -C "$SRC_DIR" fetch --filter=blob:none --depth=1 origin "$REPO_COMMIT"; then
      fetched=1
      break
    fi
    printf 'Firmware fetch of %s failed (attempt %s/3)\n' "$REPO_COMMIT" "$attempt" >&2
    sleep "$(( attempt * 15 ))"
  done
  (( fetched )) || { printf 'cannot fetch the pinned firmware commit\n' >&2; exit 1; }
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
