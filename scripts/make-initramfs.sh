#!/usr/bin/env bash
# Build the Zaod initramfs.
#
# The image is assembled from scratch rather than through initramfs-tools, so
# its contents are exactly the modules the live-boot init needs: loop, the
# squashfs driver, overlayfs, iso9660 and vfat. Busybox provides the shell.
#
#   scripts/make-initramfs.sh --check     # verify inputs only, write nothing
#   scripts/make-initramfs.sh             # build build/out/initramfs.img
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -z "${KERNEL_VERSION:-}" ]]; then
  KERNEL_VERSION="$(find /lib/modules -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null | sort -V | tail -1 || true)"
fi
MODULE_ROOT="${MODULE_ROOT:-/lib/modules/$KERNEL_VERSION}"
OUT="${OUT:-build/out/initramfs.img}"
BUSYBOX="${BUSYBOX:-$(command -v busybox || echo /bin/busybox)}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

REQUIRED_MODULES=(
  kernel/fs/squashfs/squashfs.ko
  kernel/fs/overlayfs/overlay.ko
  kernel/drivers/block/loop.ko
  kernel/fs/isofs/isofs.ko
  kernel/fs/fat/fat.ko
  kernel/fs/fat/vfat.ko
  kernel/fs/nls/nls_cp437.ko
  kernel/fs/nls/nls_iso8859-1.ko
  kernel/fs/nls/nls_utf8.ko
)

fail() { printf 'make-initramfs: %s\n' "$*" >&2; exit 1; }

[[ -n "$KERNEL_VERSION" ]] || fail "no kernel modules found below /lib/modules"
[[ -d "$MODULE_ROOT" ]] || fail "module directory $MODULE_ROOT does not exist"
[[ -x "$BUSYBOX" ]] || fail "busybox is required (install the busybox-static package)"
[[ -f boot/initramfs/zaod-live ]] || fail "boot/initramfs/zaod-live is missing"

missing=()
for module in "${REQUIRED_MODULES[@]}"; do
  comp=$(find "$MODULE_ROOT" -path "*/${module}*" -print -quit 2>/dev/null || true)
  [[ -n "$comp" ]] || missing+=("$module")
done
(( ${#missing[@]} == 0 )) || fail "modules missing from $MODULE_ROOT: ${missing[*]}"

printf 'make-initramfs: kernel %s, %d required modules present\n' \
  "$KERNEL_VERSION" "${#REQUIRED_MODULES[@]}"

if (( CHECK )); then
  printf 'make-initramfs: --check done, nothing written\n'
  exit 0
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE"/{bin,sbin,proc,sys,dev,run,lib,usr/lib,etc,newroot}
cp "$BUSYBOX" "$STAGE/bin/busybox"
chmod 0755 "$STAGE/bin/busybox"
for applet in sh ls cat mount umount mkdir sleep blkid grep cut awk du cp echo switch_root \
              mknod printf dmesg modprobe find head tail sed tr chroot; do
  ln -sf busybox "$STAGE/bin/$applet"
done

mkdir -p "$STAGE/lib/modules/$KERNEL_VERSION"
for module in "${REQUIRED_MODULES[@]}"; do
  source_file=$(find "$MODULE_ROOT" -path "*/${module}*" -print -quit)
  relative="${source_file#"$MODULE_ROOT"/}"
  mkdir -p "$STAGE/lib/modules/$KERNEL_VERSION/$(dirname "$relative")"
  cp "$source_file" "$STAGE/lib/modules/$KERNEL_VERSION/$relative"
done

install -m 0755 boot/initramfs/zaod-live "$STAGE/init"
printf 'ZAODOS live initramfs, kernel %s\n' "$KERNEL_VERSION" > "$STAGE/etc/zaod-initramfs"

mkdir -p "$(dirname "$OUT")"
(
  cd "$STAGE"
  find . -print0 | sort -z | cpio --null --create --format=newc 2>/dev/null | zstd -19 -q -o "../../$OUT"
)
printf 'make-initramfs: wrote %s (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
