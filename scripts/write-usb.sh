#!/usr/bin/env bash
# Write a Zaod ISO to a USB stick, with the safety checks that matter:
#
#   * the target must be a whole block device, never a partition
#   * nothing on the target may be mounted, including any of its partitions
#   * the ISO must carry the ZAODOS volume label
#   * the target must be large enough
#   * an explicit --yes is required, and the device path is echoed first
#
#   scripts/write-usb.sh --iso build/out/zaod-os-0.4.0-x86_64.iso --device /dev/sdX
#
# EVERYTHING ON THE TARGET DEVICE IS DESTROYED. There is no undo.
set -euo pipefail

ISO=""
DEVICE=""
CONFIRMED=0
CHECK=0

usage() {
  printf 'usage: %s --iso PATH --device /dev/sdX [--yes] [--check]\n' "$0" >&2
  exit 2
}

while (( $# )); do
  case "$1" in
    --iso) ISO="${2:-}"; shift 2 ;;
    --device) DEVICE="${2:-}"; shift 2 ;;
    --yes) CONFIRMED=1; shift ;;
    --check) CHECK=1; shift ;;
    -h|--help) usage ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage ;;
  esac
done

fail() { printf 'write-usb: %s\n' "$*" >&2; exit 1; }

[[ -n "$ISO" ]] || fail "--iso is required"
[[ -n "$DEVICE" ]] || fail "--device is required"
[[ -f "$ISO" ]] || fail "no such ISO: $ISO"
[[ -b "$DEVICE" ]] || fail "$DEVICE is not a block device"

# A partition has a trailing digit; a whole disk does not.
[[ "$DEVICE" =~ [0-9]$ ]] && fail "$DEVICE looks like a partition; pass the whole disk, for example /dev/sdb"
[[ "$DEVICE" == /dev/loop* || "$DEVICE" == /dev/sr* ]] && fail "$DEVICE is a virtual or optical device"

LABEL="$(blkid -o value -s LABEL "$ISO" 2>/dev/null || true)"
[[ "$LABEL" == "ZAODOS" ]] || fail "$ISO does not carry the ZAODOS volume label (found: ${LABEL:-none})"

ISO_BYTES="$(stat -c %s "$ISO")"
DEVICE_BYTES="$(blockdev --getsize64 "$DEVICE")"
(( DEVICE_BYTES > ISO_BYTES )) || fail "$DEVICE is too small: $((DEVICE_BYTES / 1024 / 1024)) MB available, $((ISO_BYTES / 1024 / 1024)) MB needed"

MOUNTED="$(lsblk -nrpo NAME,MOUNTPOINT "$DEVICE" | awk '$2 != "" {print $1" -> "$2}')"
[[ -z "$MOUNTED" ]] || fail "$DEVICE has mounted partitions, unmount them first:
$MOUNTED"

printf 'write-usb: about to overwrite %s (%s)\n' \
  "$DEVICE" "$(lsblk -dnro SIZE,MODEL "$DEVICE")"
printf 'write-usb: with %s (%s)\n' "$ISO" "$(du -h "$ISO" | cut -f1)"
printf 'write-usb: every existing partition and file on it will be destroyed\n'

if (( CHECK )); then
  printf 'write-usb: --check done, nothing written\n'
  exit 0
fi

if (( ! CONFIRMED )); then
  printf 'Type the device path again to confirm: '
  read -r reply
  [[ "$reply" == "$DEVICE" ]] || fail "confirmation did not match, nothing was written"
fi

printf 'write-usb: writing, this can take several minutes\n'
dd if="$ISO" of="$DEVICE" bs=4M conv=fsync status=progress
sync

AFTER="$(blkid -o value -s LABEL "$DEVICE" 2>/dev/null || true)"
[[ "$AFTER" == "ZAODOS" ]] || fail "written, but the volume label reads '${AFTER:-none}' instead of ZAODOS; the copy may be incomplete"
printf 'write-usb: done. %s now carries a bootable Zaod OS image labelled %s\n' "$DEVICE" "$AFTER"
