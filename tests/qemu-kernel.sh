#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  printf 'Usage: %s KERNEL_IMAGE ROOTFS_TARBALL KERNEL_SOURCE\n' "$0" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KERNEL_IMAGE="$1"
ROOTFS_TARBALL="$2"
KERNEL_SOURCE="$3"
OUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/build/out/kernel}"
INITROOT="$OUT_DIR/qemu-initroot"
INITRAMFS="$OUT_DIR/qemu-initramfs.cpio"
SERIAL_LOG="$OUT_DIR/qemu-kernel-serial.log"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-30}"

for input in "$KERNEL_IMAGE" "$ROOTFS_TARBALL" "$KERNEL_SOURCE/usr/gen_initramfs.sh"; do
  if [[ ! -e "$input" ]]; then
    printf 'Required input not found: %s\n' "$input" >&2
    exit 2
  fi
done

mkdir -p "$OUT_DIR"
rm -rf "$INITROOT"
mkdir -p "$INITROOT"
tar --no-same-owner -xf "$ROOTFS_TARBALL" -C "$INITROOT"
cat > "$INITROOT/init" <<'INIT'
#!/bin/sh
mount -t proc proc /proc || exit 11
mount -t sysfs sysfs /sys || exit 12
grep -q '^devtmpfs /dev devtmpfs ' /proc/mounts || mount -t devtmpfs devtmpfs /dev || exit 13
printf 'ZAOD_KERNEL_RELEASE=%s\n' "$(uname -r)" > /dev/console
grep -q '^proc /proc proc ' /proc/mounts || exit 14
grep -q '^sysfs /sys sysfs ' /proc/mounts || exit 15
grep -q '^devtmpfs /dev devtmpfs ' /proc/mounts || exit 16
echo ZAOD_INITRAMFS_MOUNTS_OK > /dev/console
exec /bin/sleep 600
INIT
chmod 0755 "$INITROOT/init"
bash "$KERNEL_SOURCE/usr/gen_initramfs.sh" -o "$INITRAMFS" -u squash -g squash "$INITROOT"

rm -f "$SERIAL_LOG"
set +e
timeout --signal=TERM "$TIMEOUT_SECONDS" qemu-system-x86_64 \
  -m 2048 -smp 2 -kernel "$KERNEL_IMAGE" -initrd "$INITRAMFS" \
  -append 'console=ttyS0,115200 rdinit=/init' -display none \
  -serial "file:$SERIAL_LOG" -monitor none -no-reboot >/dev/null 2>&1
qemu_status=$?
set -e

expected_release="$(make -s -C "$KERNEL_SOURCE" kernelrelease)"
if [[ "$qemu_status" -ne 124 ]] \
  || ! grep -q "ZAOD_KERNEL_RELEASE=$expected_release" "$SERIAL_LOG" \
  || ! grep -q 'ZAOD_INITRAMFS_MOUNTS_OK' "$SERIAL_LOG" \
  || grep -Eq 'Kernel panic|Failed to execute|No working init found|ZAOD_MOUNT' "$SERIAL_LOG"; then
  printf 'Kernel QEMU smoke test failed (status %s, expected release %s).\n' "$qemu_status" "$expected_release" >&2
  tail -n 60 "$SERIAL_LOG" >&2
  exit 1
fi

printf 'QEMU kernel release: %s\n' "$expected_release"
printf 'QEMU mounts: proc, sysfs, devtmpfs verified\n'
printf 'Serial log: %s\n' "$SERIAL_LOG"