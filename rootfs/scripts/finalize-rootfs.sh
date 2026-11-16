#!/usr/bin/env bash
set -euo pipefail

INPUT_DIR=/tmp/zaod-inputs
KERNEL_RELEASE="${ZAOD_KERNEL_RELEASE:?ZAOD_KERNEL_RELEASE is required}"
MODULES_ARCHIVE="$INPUT_DIR/modules.tar.gz"
FIRMWARE_ARCHIVE="$INPUT_DIR/firmware.tar.xz"
FIRMWARE_STAGE=/tmp/zaod-firmware

for input in "$INPUT_DIR/vmlinuz" "$INPUT_DIR/System.map" "$MODULES_ARCHIVE" "$FIRMWARE_ARCHIVE" "$INPUT_DIR/firmware-source-commit.txt"; do
  if [[ ! -s "$input" ]]; then
    printf 'Required Phase 2 input is missing: %s\n' "$input" >&2
    exit 1
  fi
done

mkdir -p /boot /lib/firmware /etc/systemd/system/multi-user.target.wants \
  /etc/skel/.config/zaod /usr/share/zaod/licenses/linux-firmware \
  /run /proc /sys /dev /tmp
chmod 1777 /tmp
install -m 0644 "$INPUT_DIR/vmlinuz" "/boot/vmlinuz-$KERNEL_RELEASE"
install -m 0644 "$INPUT_DIR/System.map" "/boot/System.map-$KERNEL_RELEASE"
# Same merged-/usr trap as scripts/build-rootfs.sh: the archive carries a ./lib/
# entry that would replace the lib -> usr/lib symlink with a real directory.
tar -xzf "$MODULES_ARCHIVE" -C / --keep-directory-symlink --no-same-owner

depmod -a -b / "$KERNEL_RELEASE"
rm -rf "$FIRMWARE_STAGE"
mkdir -p "$FIRMWARE_STAGE"
tar -xJf "$FIRMWARE_ARCHIVE" -C "$FIRMWARE_STAGE"
mkdir -p /lib/firmware
for family in amdgpu ath3k-1.fw ath9k_htc ath10k ath11k brcm i915 intel mediatek radeon rtl_bt rtl_nic rtlwifi rtw88 rtw89; do
  if [[ -e "$FIRMWARE_STAGE/$family" ]]; then
    cp -a "$FIRMWARE_STAGE/$family" /lib/firmware/
  fi
done
for notice in LICENSE LICENSE-CRITERIA.md LICENSES WHENCE; do
  if [[ -e "$FIRMWARE_STAGE/$notice" ]]; then
    cp -a "$FIRMWARE_STAGE/$notice" /usr/share/zaod/licenses/linux-firmware/
  fi
done
printf '%s\n' "$(<"$INPUT_DIR/firmware-source-commit.txt")" \
  > /usr/share/zaod/licenses/linux-firmware/source-commit.txt

rm -f "/boot/initrd.img-$KERNEL_RELEASE"
update-initramfs -c -k "$KERNEL_RELEASE"
locale-gen en_US.UTF-8
ln -snf /usr/share/zoneinfo/Etc/UTC /etc/localtime
printf '%s\n' 'Etc/UTC' > /etc/timezone
printf '%s\n' 'zaod' > /etc/hostname
: > /etc/machine-id
getent group zaod-admins >/dev/null || groupadd --system zaod-admins
systemctl --root=/ enable NetworkManager.service earlyoom.service systemd-timesyncd.service

{
  printf 'Zaod OS version: 0.3.0\n'
  printf 'Debian release: %s\n' "$(< /etc/debian_version)"
  printf 'Kernel release: %s\n' "$KERNEL_RELEASE"
  printf 'Linux firmware commit: %s\n' "$(< /usr/share/zaod/licenses/linux-firmware/source-commit.txt)"
} > /usr/share/zaod/versions.txt

/usr/local/sbin/zaod-remove-distro-packages
rm -rf "$FIRMWARE_STAGE" "$INPUT_DIR"
rm -f /usr/local/sbin/zaod-finalize-rootfs /usr/local/sbin/zaod-remove-distro-packages
