#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s [--uefi] [--expect REGEX] IMAGE\n' "$0" >&2
}

UEFI=0
EXPECT=''
while [[ $# -gt 0 ]]; do
  case "$1" in
    --uefi)
      UEFI=1
      shift
      ;;
    --expect)
      if [[ $# -lt 2 ]]; then
        usage
        exit 2
      fi
      EXPECT=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      usage
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

IMAGE=$1
if [[ ! -f "$IMAGE" ]]; then
  printf 'Image not found: %s\n' "$IMAGE" >&2
  exit 2
fi
if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  printf '%s\n' 'qemu-system-x86_64 is required.' >&2
  exit 2
fi

OUTPUT_DIR=${OUTPUT_DIR:-build/qemu}
TIMEOUT_SECONDS=${TIMEOUT_SECONDS:-120}
mkdir -p "$OUTPUT_DIR"
SERIAL_LOG=$OUTPUT_DIR/serial.log
SCREENSHOT=$OUTPUT_DIR/screenshot.ppm
QMP_SOCKET=$OUTPUT_DIR/qmp.sock
rm -f "$SERIAL_LOG" "$SCREENSHOT" "$QMP_SOCKET"

QEMU_ARGS=(-m 2048 -smp 2 -display none -serial "file:$SERIAL_LOG"
  -qmp "unix:$QMP_SOCKET,server=on,wait=off")
if [[ "$IMAGE" == *.iso ]]; then
  QEMU_ARGS+=(-cdrom "$IMAGE" -boot d)
else
  QEMU_ARGS+=(-drive "file=$IMAGE,format=raw,if=virtio")
fi

if [[ "$UEFI" -eq 1 ]]; then
  OVMF_CODE=${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE.fd}
  if [[ ! -f "$OVMF_CODE" ]]; then
    printf 'OVMF firmware not found: %s\n' "$OVMF_CODE" >&2
    exit 2
  fi
  QEMU_ARGS+=(-bios "$OVMF_CODE")
fi

timeout --signal=TERM "$TIMEOUT_SECONDS" qemu-system-x86_64 "${QEMU_ARGS[@]}" &
QEMU_PID=$!
cleanup() {
  kill "$QEMU_PID" >/dev/null 2>&1 || true
  wait "$QEMU_PID" >/dev/null 2>&1 || true
  rm -f "$QMP_SOCKET"
}
trap cleanup EXIT

deadline=$((SECONDS + TIMEOUT_SECONDS))
while [[ ! -S "$QMP_SOCKET" && "$SECONDS" -lt "$deadline" ]]; do
  if ! kill -0 "$QEMU_PID" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

if [[ ! -S "$QMP_SOCKET" ]]; then
  printf '%s\n' 'QEMU did not create its QMP socket before timeout.' >&2
  exit 1
fi

python3 tests/qmp_screendump.py "$QMP_SOCKET" "$SCREENSHOT"
if [[ ! -s "$SCREENSHOT" ]]; then
  printf '%s\n' 'QEMU screenshot was not created.' >&2
  exit 1
fi

if [[ -n "$EXPECT" ]]; then
  while [[ "$SECONDS" -lt "$deadline" ]]; do
    if grep -Eq "$EXPECT" "$SERIAL_LOG"; then
      printf 'Matched boot marker: %s\n' "$EXPECT"
      printf 'Serial log: %s\nScreenshot: %s\n' "$SERIAL_LOG" "$SCREENSHOT"
      exit 0
    fi
    if ! kill -0 "$QEMU_PID" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  printf 'Boot marker not seen before timeout: %s\n' "$EXPECT" >&2
  cat "$SERIAL_LOG" >&2
  exit 1
fi

printf 'QEMU launched; serial log: %s; screenshot: %s\n' "$SERIAL_LOG" "$SCREENSHOT"