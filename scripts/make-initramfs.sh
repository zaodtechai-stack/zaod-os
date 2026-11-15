#!/usr/bin/env bash
# Build the Zaod initramfs.
#
# The image is assembled from scratch rather than through initramfs-tools, so
# its contents are exactly the modules the live-boot init needs: loop, the
# squashfs, overlay and iso9660 drivers, vfat, the optical and USB storage
# stacks and the input stack, plus every module modules.dep says those depend
# on. Busybox provides the shell, modprobe and the rescue tools.
#
#   scripts/make-initramfs.sh --check     # verify inputs only, write nothing
#   scripts/make-initramfs.sh             # build build/out/initramfs.img
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

KERNEL_OUT="${KERNEL_OUT:-build/out/kernel}"
MODULES_ARCHIVE="$KERNEL_OUT/modules.tar.gz"
KERNEL_CONFIG="$KERNEL_OUT/config"
OUT="${OUT:-build/out/initramfs.img}"
BUSYBOX="${BUSYBOX:-$(command -v busybox || echo /bin/busybox)}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

fail() { printf 'make-initramfs: %s\n' "$*" >&2; exit 1; }

STAGE=""
LISTING=""
DEP_LIST=""
EXTRACT_LIST=""
cleanup() {
  [[ -n "$STAGE" ]] && rm -rf "$STAGE"
  [[ -n "$LISTING" ]] && rm -f "$LISTING"
  [[ -n "$DEP_LIST" ]] && rm -f "$DEP_LIST"
  [[ -n "$EXTRACT_LIST" ]] && rm -f "$EXTRACT_LIST"
  return 0
}
trap cleanup EXIT

# Drivers the live init needs to see the media, mount the image and keep a
# keyboard usable in the rescue shell. Each one is also modprobed by
# boot/initramfs/zaod-live; this list is what puts them in the image.
BOOT_MODULES=(
  loop
  squashfs
  overlay
  isofs
  vfat
  fat
  nls_cp437
  nls_iso8859-1
  nls_utf8
  sr_mod
  cdrom
  usb-storage
  xhci-hcd
  ehci-hcd
  ohci-hcd
  uhci-hcd
  usbhid
  hid-generic
)

# Config options that must be at least modular, so a kernel that moved one of
# them into the built-in set is reported rather than silently producing an
# image that cannot mount the media.
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

[[ -s "$MODULES_ARCHIVE" ]] || fail "the kernel modules archive is missing: $MODULES_ARCHIVE"
[[ -s "$KERNEL_CONFIG" ]] || fail "the kernel config is missing: $KERNEL_CONFIG"
[[ -x "$BUSYBOX" ]] || fail "busybox is required (install the busybox-static package)"
[[ -f boot/initramfs/zaod-live ]] || fail "boot/initramfs/zaod-live is missing"

# List the archive exactly once. Re-reading it for every driver was slow, and a
# listing piped into `grep -q` or `head -n 1` lets those exit early, which kills
# tar with SIGPIPE; `pipefail` then turned that broken pipe into a bogus
# "modules.dep is missing" failure. A file is read instead, once.
LISTING="$(mktemp)"
tar -tzf "$MODULES_ARCHIVE" > "$LISTING" \
  || fail "cannot list $MODULES_ARCHIVE (corrupt archive?)"

if [[ -z "${KERNEL_VERSION:-}" ]]; then
  mapfile -t kernel_releases < <(
    sed -n 's#^\./lib/modules/\([^/]*\)/.*#\1#p' "$LISTING" | LC_ALL=C sort -u
  )
  KERNEL_VERSION="${kernel_releases[0]:-}"
fi
[[ -n "$KERNEL_VERSION" ]] || fail "no kernel release found in $MODULES_ARCHIVE"

MODULE_PREFIX="./lib/modules/$KERNEL_VERSION/"

# A module name without its directory and without its compression suffix, so
# .ko, .ko.zst, .ko.xz and .ko.gz all resolve to the same key.
module_stem() {
  local base="${1##*/}"
  case "$base" in
    *.zst | *.xz | *.gz) base="${base%.*}" ;;
  esac
  case "$base" in
    *.ko) printf '%s\n' "${base%.ko}" ;;
    *) return 1 ;;
  esac
}

# index: module stem -> the member path the archive actually stores
declare -A MEMBER=()
while IFS= read -r member; do
  sub="${member#"$MODULE_PREFIX"}"
  [[ "$sub" == "$member" ]] && continue
  stem="$(module_stem "$sub")" || continue
  [[ -n "${MEMBER[$stem]:-}" ]] || MEMBER["$stem"]="$member"
done < "$LISTING"

# ---------------------------------------------------------------- sanity gates
# Without modules.dep nothing below can be resolved, so this is reported on
# its own rather than as a wall of missing modules.
DEP_MEMBER="$MODULE_PREFIX""modules.dep"
grep -Fqx -- "$DEP_MEMBER" "$LISTING" \
  || fail "modules.dep is missing from $MODULES_ARCHIVE (pack it after depmod has run)"

problems=()
modular_count=0
for option in "${REQUIRED_CONFIG[@]}"; do
  setting="$(sed -n "s/^${option}=//p" "$KERNEL_CONFIG" | head -n 1)"
  if [[ "$setting" != y && "$setting" != m ]]; then
    problems+=("$option must be built-in or modular in $KERNEL_CONFIG (found: ${setting:-unset})")
    continue
  fi
  [[ "$setting" == m ]] || continue
  case "$option" in
    CONFIG_SQUASHFS) stem="squashfs" ;;
    CONFIG_OVERLAY_FS) stem="overlay" ;;
    CONFIG_BLK_DEV_LOOP) stem="loop" ;;
    CONFIG_ISO9660_FS) stem="isofs" ;;
    CONFIG_VFAT_FS) stem="vfat" ;;
    CONFIG_USB_STORAGE) stem="usb-storage" ;;
    CONFIG_USB_XHCI_HCD) stem="xhci-hcd" ;;
    *) stem="$(printf '%s' "${option#CONFIG_}" | tr '[:upper:]_' '[:lower:]-')" ;;
  esac
  if [[ -z "${MEMBER[$stem]:-}" ]]; then
    problems+=("module $stem for $option is missing from $MODULES_ARCHIVE")
    continue
  fi
  modular_count=$((modular_count + 1))
done

declare -A REPORTED=()
for text in "${problems[@]}"; do
  for stem in "${BOOT_MODULES[@]}"; do
    [[ "$text" == *"module $stem "?* ]] && REPORTED["$stem"]=1
  done
done
for stem in "${BOOT_MODULES[@]}"; do
  [[ -n "${REPORTED[$stem]:-}" ]] && continue
  [[ -n "${MEMBER[$stem]:-}" ]] \
    || problems+=("the boot module $stem is not in $MODULES_ARCHIVE")
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

# ------------------------------------------------- dependency-aware selection
DEP_LIST="$(mktemp)"
tar -xzOf "$MODULES_ARCHIVE" "$DEP_MEMBER" > "$DEP_LIST" \
  || fail "cannot read $DEP_MEMBER out of $MODULES_ARCHIVE"

declare -A DEPENDS=()
while IFS= read -r line; do
  [[ "$line" == *:* ]] || continue
  key_stem="$(module_stem "${line%%:*}")" || continue
  DEPENDS["$key_stem"]="${line#*:}"
done < "$DEP_LIST"

declare -A NEEDED=()
QUEUE=()
enqueue() {
  local stem="$1"
  [[ -n "$stem" ]] || return 0
  [[ -n "${NEEDED[$stem]:-}" ]] && return 0
  NEEDED["$stem"]=1
  QUEUE+=("$stem")
  return 0
}

for stem in "${BOOT_MODULES[@]}"; do enqueue "$stem"; done

index=0
while (( index < ${#QUEUE[@]} )); do
  current="${QUEUE[index]}"
  index=$((index + 1))
  # modules.dep lists dependencies space separated; the split is intended.
  # shellcheck disable=SC2086
  for dependency in ${DEPENDS[$current]:-}; do
    enqueue "$(module_stem "$dependency" || true)"
  done
done

# Modules modprobe resolves by alias rather than by name never appear in
# modules.dep, so anything still unresolved adds that module's own closure.
EXTRACT_LIST="$(mktemp)"
unresolved=0
for stem in "${!NEEDED[@]}"; do
  if [[ -n "${MEMBER[$stem]:-}" ]]; then
    printf '%s\n' "${MEMBER[$stem]}" >> "$EXTRACT_LIST"
  else
    unresolved=$((unresolved + 1))
  fi
done

METADATA=()
for name in modules.dep modules.alias modules.builtin modules.order; do
  grep -Fqx -- "$MODULE_PREFIX$name" "$LISTING" && METADATA+=("$MODULE_PREFIX$name")
done

printf 'make-initramfs: kernel %s, config ok, %d modular boot drivers, %d modules selected\n' \
  "$KERNEL_VERSION" "$modular_count" "${#NEEDED[@]}"

if (( CHECK )); then
  printf 'make-initramfs: --check done, nothing written\n'
  exit 0
fi

# --------------------------------------------------------------- image build
STAGE="$(mktemp -d)"
mkdir -p "$STAGE"/{bin,sbin,proc,sys,dev,run,lib,usr/lib,etc,newroot}

if (( unresolved )); then
  # A module resolved through an alias or a split packaging is safer to carry
  # whole than to leave out: the image gets bigger, never unbootable.
  printf 'make-initramfs: note: %d selected modules are named only by alias, carrying the whole module tree\n' \
    "$unresolved"
  tar -xzf "$MODULES_ARCHIVE" -C "$STAGE"
else
  tar -xzf "$MODULES_ARCHIVE" -C "$STAGE" -T "$EXTRACT_LIST"
  if (( ${#METADATA[@]} )); then
    tar -xzf "$MODULES_ARCHIVE" -C "$STAGE" "${METADATA[@]}"
  fi
fi

cp "$BUSYBOX" "$STAGE/bin/busybox"
chmod 0755 "$STAGE/bin/busybox"
for applet in sh ls cat mount umount mkdir sleep blkid grep cut awk du cp echo switch_root \
              mknod printf dmesg modprobe insmod lsmod rmmod find head tail sed tr chroot \
              sync reboot poweroff wc ln dirname basename tee; do
  ln -sf busybox "$STAGE/bin/$applet"
done
# The kernel autoloads a module by running /sbin/modprobe, so that path has to
# exist inside the image and not only /bin.
ln -sf ../bin/busybox "$STAGE/sbin/modprobe"
ln -sf ../bin/busybox "$STAGE/sbin/insmod"

install -m 0755 boot/initramfs/zaod-live "$STAGE/init"
printf 'ZAODOS live initramfs, kernel %s\n' "$KERNEL_VERSION" > "$STAGE/etc/zaod-initramfs"

mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
(
  cd "$STAGE"
  find . -print0 | sort -z | cpio --null --create --format=newc 2>/dev/null | zstd -19 -q -o "$OUT"
)
printf 'make-initramfs: wrote %s (%s)\n' "$OUT" "$(du -h "$OUT" | cut -f1)"
