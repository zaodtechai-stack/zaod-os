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

KERNEL_OUT="${KERNEL_OUT:-build/out/kernel}"
MODULES_ARCHIVE="$KERNEL_OUT/modules.tar.gz"
KERNEL_CONFIG="$KERNEL_OUT/config"
if [[ -z "${KERNEL_VERSION:-}" && -f "$MODULES_ARCHIVE" ]]; then
  KERNEL_VERSION="$(tar -tzf "$MODULES_ARCHIVE" \
    | sed -n 's#^\./lib/modules/\([^/]*\)/.*#\1#p' | LC_ALL=C sort -u | head -n 1)"
fi
MODULE_ROOT="${MODULE_ROOT:-$KERNEL_OUT/modules-root}"
OUT="${OUT:-build/out/initramfs.img}"
BUSYBOX="${BUSYBOX:-$(command -v busybox || echo /bin/busybox)}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

REQUIRED_CONFIG=(
  CONFIG_SQUASHFS
  CONFIG_OVERLAY_FS
  CONFIG_BLK_DEV_LOOP
  CONFIG_ISO9660_FS
  CONFIG_VFAT_FS
  CONFIG_USB_XHCI_HCD
  CONFIG_USB_STORAGE
  CONFIG_DEVTMPFS
)

fail() { printf 'make-initramfs: %s\n' "$*" >&2; exit 1; }

[[ -n "$KERNEL_VERSION" ]] || fail "no kernel release found in $MODULES_ARCHIVE"
[[ -s "$MODULES_ARCHIVE" ]] || fail "Phase 2 modules archive is missing: $MODULES_ARCHIVE"
[[ -s "$KERNEL_CONFIG" ]] || fail "Phase 2 kernel config is missing: $KERNEL_CONFIG"
[[ -x "$BUSYBOX" ]] || fail "busybox is required (install the busybox-static package)"
[[ -f boot/initramfs/zaod-live ]] || fail "boot/initramfs/zaod-live is missing"

# Kernels differ in module directory layout and in whether .ko files are
# compressed, so a module is found by basename anywhere in the tree. Most
# options map to their lowercased option name; the exceptions are the ones
# whose module is not named after the option (Debian, Ubuntu and upstream all
# agree on these names).
module_basename() {
  case "$1" in
    CONFIG_ISO9660_FS) printf '%s\n' 'isofs' ;;
    CONFIG_OVERLAY_FS) printf '%s\n' 'overlay' ;;
    CONFIG_BLK_DEV_LOOP) printf '%s\n' 'loop' ;;
    CONFIG_VFAT_FS) printf '%s\n' 'vfat' ;;
    CONFIG_USB_STORAGE) printf '%s\n' 'usb-storage' ;;
    CONFIG_USB_XHCI_HCD) printf '%s\n' 'xhci-hcd' ;;
    CONFIG_SQUASHFS) printf '%s\n' 'squashfs' ;;
    *) printf '%s\n' "${1#CONFIG_}" | tr '[:upper:]_' '[:lower:]-' ;;
  esac
}

module_lookup() {
  # $1 module basename, with or without a compressed suffix on disk
  tar -tzf "$MODULES_ARCHIVE" \
    | sed -n "s#^\./lib/modules/$KERNEL_VERSION/\(.*/\)\{0,1\}$1\.ko\(\.\(zst\|xz\|gz\)\)\{0,1\}\$#\1$1.ko#p" \
    | head -n 1
}

# Collect every problem before failing: one CI run should report all of them.
problems=()
modular_count=0
for option in "${REQUIRED_CONFIG[@]}"; do
  setting="$(sed -n "s/^${option}=//p" "$KERNEL_CONFIG" | head -n 1)"
  if [[ "$setting" != y && "$setting" != m ]]; then
    problems+=("$option must be built-in or modular in $KERNEL_CONFIG (found: ${setting:-unset})")
    continue
  fi
  [[ "$setting" == m ]] || continue
  basename="$(module_basename "$option")"
  if [[ -z "$(module_lookup "$basename")" ]]; then
    problems+=("module $basename for $option is missing from $MODULES_ARCHIVE")
    continue
  fi
  modular_count=$((modular_count + 1))
done

# The live init mounts devtmpfs itself (boot/initramfs/zaod-live), so a kernel
# that leaves CONFIG_DEVTMPFS_MOUNT unset, as Debian's does, is fine.
if [[ -z "$(sed -n 's/^CONFIG_DEVTMPFS_MOUNT=//p' "$KERNEL_CONFIG" | head -n 1)" ]]; then
  printf 'make-initramfs: note: CONFIG_DEVTMPFS_MOUNT is unset; the live init mounts devtmpfs itself\n'
fi

if (( ${#problems[@]} )); then
  printf 'make-initramfs: %s\n' "${problems[@]}" >&2
  exit 1
fi
tar -tzf "$MODULES_ARCHIVE" | grep -Fqx "./lib/modules/$KERNEL_VERSION/modules.dep" \
  || fail "modules.dep is missing from $MODULES_ARCHIVE"

printf 'make-initramfs: kernel %s, config ok, %d modular boot drivers\n' \
  "$KERNEL_VERSION" "$modular_count"

if (( CHECK )); then
  printf 'make-initramfs: --check done, nothing written\n'
  exit 0
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE"/{bin,sbin,proc,sys,dev,run,lib,usr/lib,etc,newroot}
tar -xzf "$MODULES_ARCHIVE" -C "$STAGE"
cp "$BUSYBOX" "$STAGE/bin/busybox"
chmod 0755 "$STAGE/bin/busybox"
for applet in sh ls cat mount umount mkdir sleep blkid grep cut awk du cp echo switch_root \
              mknod printf dmesg modprobe find head tail sed tr chroot; do
  ln -sf busybox "$STAGE/bin/$applet"
done
install -m 0755 boot/initramfs/zaod-live "$STAGE/init"
printf 'ZAODOS live initramfs, kernel %s\n' "$KERNEL_VERSION" > "$STAGE/etc/zaod-initramfs"

mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
(
  cd "$STAGE"
  find . -print0 | sort -z | cpio --null --create --format=newc 2>/dev/null | zstd -19 -q -o "$OUT"
)
printf 'make-initramfs: wrote %s (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
