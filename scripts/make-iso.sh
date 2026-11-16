#!/usr/bin/env bash
# Assemble the hybrid UEFI/BIOS ISO.
#
#   scripts/make-iso.sh --check     # verify every input exists, write nothing
#   scripts/make-iso.sh             # build build/out/zaod-os-VERSION-x86_64.iso
#
# The EFI system partition is a FAT image built with mtools (mformat/mcopy), so
# no privileged loop device or partitioning step is involved.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VERSION="${VERSION:-0.4.0}"
ARCH="${ARCH:-x86_64}"
VOLUME_LABEL="${VOLUME_LABEL:-ZAODOS}"
OUT_DIR="${OUT_DIR:-build/out}"
ISO_NAME="zaod-os-${VERSION}-${ARCH}.iso"
ISO_PATH="$OUT_DIR/$ISO_NAME"
SQUASHFS="${SQUASHFS:-$OUT_DIR/zaod-rootfs.squashfs}"
INITRAMFS="${INITRAMFS:-$OUT_DIR/initramfs.img}"
VMLINUZ="${VMLINUZ:-$OUT_DIR/kernel/vmlinuz}"
GRUB_PC_DIR="${GRUB_PC_DIR:-/usr/lib/grub/i386-pc}"
GRUB_EFI="${GRUB_EFI:-/usr/lib/grub/x86_64-efi}"
# The hybrid MBR that makes the same image a bootable USB stick. Without it the
# medium only carries an El Torito catalog, which a disk firmware never reads.
HYBRID_MBR="${HYBRID_MBR:-$GRUB_PC_DIR/boot_hybrid.img}"
PARTITION_OFFSET="${PARTITION_OFFSET:-16}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

fail() { printf 'make-iso: %s\n' "$*" >&2; exit 1; }

required=(xorriso mformat mcopy grub-mkimage)
for tool in "${required[@]}"; do
  command -v "$tool" >/dev/null || fail "missing build tool: $tool (install xorriso, mtools, grub-common)"
done

required_files=("$SQUASHFS" "$INITRAMFS" "$VMLINUZ" boot/grub/grub.cfg)
for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || fail "missing input: $path"
done
[[ -d "$GRUB_PC_DIR" ]] || fail "missing $GRUB_PC_DIR (install grub-pc-bin)"
[[ -d "$GRUB_EFI" ]] || fail "missing $GRUB_EFI (install grub-efi-amd64-bin)"
[[ -f "$HYBRID_MBR" ]] || fail "missing $HYBRID_MBR (install grub-pc-bin)"

printf 'make-iso: inputs ok\n  label     %s\n  squashfs  %s (%s)\n  initramfs %s (%s)\n  kernel    %s\n' \
  "$VOLUME_LABEL" "$SQUASHFS" "$(du -h "$SQUASHFS" | cut -f1)" \
  "$INITRAMFS" "$(du -h "$INITRAMFS" | cut -f1)" "$VMLINUZ"

if (( CHECK )); then
  printf 'make-iso: --check done, nothing written\n'
  exit 0
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE"/{boot/zaod,boot/grub/i386-pc,boot/grub/fonts,EFI/BOOT}
install -m 0644 "$VMLINUZ" "$STAGE/boot/vmlinuz"
install -m 0644 "$INITRAMFS" "$STAGE/boot/initramfs.img"
install -m 0644 "$SQUASHFS" "$STAGE/boot/zaod/zaod-os-${ARCH}.squashfs"
install -m 0644 boot/grub/grub.cfg "$STAGE/boot/grub/grub.cfg"

cp -r "$GRUB_PC_DIR"/* "$STAGE/boot/grub/i386-pc/"
if [[ -f /usr/share/grub/unicode.pf2 ]]; then
  install -m 0644 /usr/share/grub/unicode.pf2 "$STAGE/boot/grub/fonts/unicode.pf2"
fi
# i386-pc-eltorito is the only target that produces a valid BIOS boot image:
# cdboot.img (2048 bytes, the part El Torito actually loads) followed by the
# GRUB core, which cdboot finds through the boot info table. Building with
# plain i386-pc yields core.img alone, El Torito truncates it at 2048 bytes and
# the firmware dies with "GRUB loading Error" on every machine.
grub-mkimage -O i386-pc-eltorito -o "$STAGE/boot/grub/i386-pc/eltorito.img" -p /boot/grub \
  biosdisk iso9660 part_msdos part_gpt fat search search_label normal linux all_video gfxterm
if ! cmp -s -n 2048 "$GRUB_PC_DIR/cdboot.img" "$STAGE/boot/grub/i386-pc/eltorito.img"; then
  fail "the BIOS boot image is not an El Torito stub; it would not boot from CD or USB"
fi

grub-mkimage -O x86_64-efi -o "$STAGE/EFI/BOOT/BOOTX64.EFI" -p /boot/grub \
  part_msdos part_gpt fat iso9660 search search_label normal linux all_video gfxterm efi_gop

# EFI system partition image, FAT formatted through mtools, no loop device.
EFI_IMG="$STAGE/boot/efiboot.img"
dd if=/dev/zero of="$EFI_IMG" bs=1M count=8 status=none
mformat -i "$EFI_IMG" ::
mmd -i "$EFI_IMG" ::/EFI ::/EFI/BOOT
mcopy -i "$EFI_IMG" "$STAGE/EFI/BOOT/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI

mkdir -p "$OUT_DIR"
xorriso -as mkisofs \
  -iso-level 3 \
  -full-iso9660-filenames \
  -volid "$VOLUME_LABEL" \
  -appid "Zaod OS $VERSION" -publisher "Zaod OS" \
  -eltorito-boot boot/grub/i386-pc/eltorito.img \
  -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
  -eltorito-alt-boot -e boot/efiboot.img -no-emul-boot \
  -isohybrid-mbr "$HYBRID_MBR" -partition_offset "$PARTITION_OFFSET" \
  -isohybrid-gpt-basdat \
  -output "$ISO_PATH" "$STAGE" >/dev/null

# An image with only an El Torito catalog boots as a CD and is rejected by every
# USB firmware, which is exactly the defect this adds the partition table for.
# Assert it here so it cannot regress silently.
if ! xorriso -indev "$ISO_PATH" -report_system_area plain 2>/dev/null | grep -q 'MBR partition'; then
  fail "the image carries no MBR partition table, so it would not boot from USB"
fi

sha256sum "$ISO_PATH" | tee "$ISO_PATH.sha256"
printf 'make-iso: volume label reported by the image:\n'
xorriso -indev "$ISO_PATH" -pvd_info 2>/dev/null | grep -i 'Volume id' || true
printf 'make-iso: wrote %s (%s)\n' "$ISO_PATH" "$(du -h "$ISO_PATH" | cut -f1)"
