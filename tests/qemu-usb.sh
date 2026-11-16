#!/usr/bin/env bash
# Boot a Zaod ISO the way a person boots a USB stick: dd it onto a raw disk and
# attach that disk as USB mass storage, under both firmware families.
#
#   tests/qemu-usb.sh build/out/zaod-os-0.4.0-x86_64.iso [OUTDIR]
#
# Fails unless every mode reaches the live system without a panic. The serial
# log of each mode is kept, so a failure can be read instead of guessed at.
set -euo pipefail

ISO="${1:-}"
OUTDIR="${2:-build/out/usb-boot}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-2400}"

[[ -f "$ISO" ]] || { printf 'usage: %s ISO [OUTDIR]\n' "$0" >&2; exit 2; }
command -v qemu-system-x86_64 >/dev/null || { printf 'qemu is not installed\n' >&2; exit 2; }

mkdir -p "$OUTDIR"
KERNEL_RELEASE="${KERNEL_RELEASE:-6.18.}"
STICK="$OUTDIR/usb-stick.img"

iso_mb=$(( ($(stat -c %s "$ISO") / 1024 / 1024) + 64 ))
printf 'writing %s onto a %s MB USB-like disk\n' "$ISO" "$iso_mb"
rm -f "$STICK"
dd if=/dev/zero of="$STICK" bs=1M count="$iso_mb" status=none
dd if="$ISO" of="$STICK" bs=4M conv=fsync status=none

run_mode() {
  local mode="$1" log="$OUTDIR/serial-$1.log"
  local -a firmware=()
  case "$mode" in
    uefi)
      local vars="$OUTDIR/OVMF_VARS-$mode.fd"
      [[ -f "$vars" ]] || cp "${OVMF_VARS:-/usr/share/OVMF/OVMF_VARS_4M.fd}" "$vars"
      firmware=(-drive "if=pflash,format=raw,readonly=on,file=${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
                -drive "if=pflash,format=raw,file=$vars")
      ;;
    bios)
      firmware=()
      ;;
  esac

  printf 'booting "%s" from an emulated USB stick (serial: %s)\n' "$mode" "$log"
  rm -f "$log"
  set +e
  timeout --signal=TERM "$TIMEOUT_SECONDS" qemu-system-x86_64 \
    -machine q35 -m 4096 -smp 2 \
    "${firmware[@]}" \
    -device qemu-xhci,id=xhci \
    -drive id=stick,file="$STICK",format=raw,if=none,cache=none \
    -device usb-storage,drive=stick,bus=xhci.0 \
    -vga std -display none -monitor none -no-reboot \
    -serial "file:$log" >/dev/null 2>&1
  local status=$?
  set -e
  # 124 is the timeout firing, which is the expected end of a run that reached
  # the live system and then sat there.
  if [[ "$status" -ne 124 && "$status" -ne 0 ]]; then
    printf 'qemu exited with %s in %s mode\n' "$status" "$mode" >&2
  fi
  return 0
}

check_mode() {
  local mode="$1" log="$OUTDIR/serial-$1.log" failed=0
  # The kernel prints "Linux version" at KERN_INFO, which a console loglevel below
  # 6 hides, so the release is proven by the live init reporting uname -r instead.
  local -a wanted=(
    "kernel ${KERNEL_RELEASE}"
    "[zaod] using boot media /dev/sd"
    "squashfs:"
    "handing over to the live system"
  )
  for needle in "${wanted[@]}"; do
    if ! grep -Fq "$needle" "$log"; then
      printf '  FAIL %-4s missing: %s\n' "$mode" "$needle" >&2
      failed=1
    fi
  done
  if grep -Eq 'Kernel panic|cannot find the ZAODOS|Attempted to kill init|unexpected failure while booting' "$log"; then
    printf '  FAIL %-4s the kernel log contains a boot failure:\n' "$mode" >&2
    grep -En 'Kernel panic|cannot find the ZAODOS|Attempted to kill init|unexpected failure while booting' "$log" | head -n 5 >&2
    failed=1
  fi
  grep -Fq "kernel ${KERNEL_RELEASE}" "$log" \
    && printf '  ok   %-4s kernel %s\n' "$mode" "$(grep -ao "kernel ${KERNEL_RELEASE}[^,]*" "$log" | head -n 1 | sed 's/^kernel //')"
  return "$failed"
}

failures=0
for mode in uefi bios; do
  if [[ "$mode" == uefi && ! -f "${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}" ]]; then
    printf 'skipping uefi: %s is missing\n' "${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
    continue
  fi
  run_mode "$mode"
  check_mode "$mode" || failures=$((failures + 1))
done

if (( failures )); then
  printf 'USB boot test: %d mode(s) failed\n' "$failures" >&2
  exit 1
fi
printf 'USB boot test: PASS (firmware modes tested from a raw USB disk)\n'
