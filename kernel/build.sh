#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_ROOT="${SRC_ROOT:-$ROOT_DIR/build/kernel-src}"
KERNEL_VERSION="${KERNEL_VERSION:-6.18.63}"
TARBALL="${TARBALL:-$ROOT_DIR/build/cache/linux-6.18.63.tar.xz}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/build/out/kernel}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 2)}"
# Serialize builds to prevent concurrent make processes from racing on objects.
if (( JOBS < 1 )); then
  JOBS=1
fi
if (( JOBS > 4 )); then
  JOBS=4
fi
SRC_DIR="$SRC_ROOT/linux-$KERNEL_VERSION"
CONFIG_FILE="$ROOT_DIR/kernel/zaod_defconfig"

mkdir -p "$SRC_ROOT" "$OUT_DIR" "$ROOT_DIR/kernel"
exec 9>"$OUT_DIR/build.lock"
if ! flock -n 9; then
  printf 'Another kernel build is using %s\n' "$OUT_DIR" >&2
  exit 1
fi

if [[ ! -d "$SRC_DIR" ]]; then
  if [[ ! -f "$TARBALL" ]]; then
    printf 'Kernel tarball not found: %s\n' "$TARBALL" >&2
    exit 1
  fi
  tar -xf "$TARBALL" -C "$SRC_ROOT"
fi

cd "$SRC_DIR"
if [[ "${CLEAN_BUILD:-1}" == "1" ]]; then
  make distclean >/dev/null 2>&1 || true
fi
if [[ ! -f "$CONFIG_FILE" ]]; then
  make x86_64_defconfig >/dev/null
  cp .config "$CONFIG_FILE"
fi

cp "$CONFIG_FILE" .config
make olddefconfig >/dev/null

./scripts/config --enable CONFIG_EFI
./scripts/config --enable CONFIG_EFI_STUB
./scripts/config --enable CONFIG_EFI_PARTITION
./scripts/config --enable CONFIG_FB
./scripts/config --enable CONFIG_FB_EFI
./scripts/config --enable CONFIG_FRAMEBUFFER_CONSOLE
./scripts/config --enable CONFIG_DRM
./scripts/config --module CONFIG_DRM_I915
./scripts/config --module CONFIG_DRM_AMDGPU
./scripts/config --module CONFIG_DRM_RADEON
./scripts/config --module CONFIG_DRM_VIRTIO_GPU
./scripts/config --enable CONFIG_DRM_SIMPLEDRM
./scripts/config --enable CONFIG_FB_VESA
./scripts/config --enable CONFIG_SATA_AHCI
./scripts/config --enable CONFIG_ATA
./scripts/config --module CONFIG_NVME_CORE
./scripts/config --module CONFIG_BLK_DEV_NVME
./scripts/config --enable CONFIG_USB_XHCI_HCD
./scripts/config --enable CONFIG_USB_EHCI_HCD
./scripts/config --module CONFIG_USB_STORAGE
# A USB 3 enclosure or stick that only speaks UAS would otherwise be dead on
# the live medium; with UAS built in every mass-storage bridge is covered.
./scripts/config --enable CONFIG_USB_UAS
./scripts/config --enable CONFIG_USB_HID
./scripts/config --enable CONFIG_EXT4_FS
./scripts/config --enable CONFIG_VFAT_FS
./scripts/config --enable CONFIG_SQUASHFS
./scripts/config --enable CONFIG_SQUASHFS_ZSTD
./scripts/config --enable CONFIG_OVERLAY_FS
./scripts/config --module CONFIG_ISO9660_FS
./scripts/config --module CONFIG_FUSE_FS
./scripts/config --enable CONFIG_BLK_DEV_LOOP
./scripts/config --enable CONFIG_TMPFS
./scripts/config --enable CONFIG_DEVTMPFS
./scripts/config --enable CONFIG_DEVTMPFS_MOUNT
./scripts/config --enable CONFIG_INPUT_EVDEV
./scripts/config --enable CONFIG_INPUT_TOUCHSCREEN
./scripts/config --module CONFIG_I2C_HID_ACPI
./scripts/config --module CONFIG_E1000E
./scripts/config --module CONFIG_IGC
./scripts/config --enable CONFIG_R8169
./scripts/config --module CONFIG_IWLWIFI
./scripts/config --module CONFIG_RTW88
./scripts/config --module CONFIG_RTW88_8822BE
./scripts/config --module CONFIG_RTW88_8822CE
./scripts/config --module CONFIG_RTW88_8723DE
./scripts/config --module CONFIG_RTW88_8821CE
./scripts/config --module CONFIG_RTW89
./scripts/config --module CONFIG_RTW89_8851BE
./scripts/config --module CONFIG_RTW89_8852AE
./scripts/config --module CONFIG_RTW89_8852BE
./scripts/config --module CONFIG_RTW89_8852CE
./scripts/config --module CONFIG_ATH9K
./scripts/config --module CONFIG_ATH10K
./scripts/config --module CONFIG_ATH10K_PCI
./scripts/config --module CONFIG_ATH11K
./scripts/config --module CONFIG_ATH11K_PCI
./scripts/config --module CONFIG_BRCMFMAC
./scripts/config --enable CONFIG_BRCMFMAC_PCIE
./scripts/config --enable CONFIG_BRCMFMAC_SDIO
./scripts/config --enable CONFIG_BRCMFMAC_USB
./scripts/config --enable CONFIG_MAC80211
./scripts/config --enable CONFIG_CFG80211
./scripts/config --enable CONFIG_BT
./scripts/config --enable CONFIG_MMC
./scripts/config --enable CONFIG_BT_HCIBTUSB
./scripts/config --enable CONFIG_BT_HCIBTUSB_MTK
./scripts/config --enable CONFIG_BT_HCIBTUSB_RTL
./scripts/config --enable CONFIG_VIRTIO_NET
./scripts/config --enable CONFIG_SOUND
./scripts/config --enable CONFIG_SND_SOC
./scripts/config --module CONFIG_SND_HDA_INTEL
./scripts/config --module CONFIG_SND_HDA_CODEC_REALTEK
./scripts/config --module CONFIG_SND_USB_AUDIO
./scripts/config --enable CONFIG_ACPI
./scripts/config --enable CONFIG_CPU_FREQ
./scripts/config --enable CONFIG_X86_INTEL_PSTATE
./scripts/config --enable CONFIG_X86_AMD_PSTATE
./scripts/config --enable CONFIG_THERMAL
./scripts/config --enable CONFIG_ACPI_BATTERY
./scripts/config --enable CONFIG_BACKLIGHT_CLASS_DEVICE
./scripts/config --enable CONFIG_MOUSE_PS2_SYNAPTICS
./scripts/config --enable CONFIG_MOUSE_PS2_ELANTECH
./scripts/config --enable CONFIG_SND_SOC_SOF_TOPLEVEL
./scripts/config --enable CONFIG_SND_SOC_SOF_INTEL_TOPLEVEL
./scripts/config --module CONFIG_SND_SOC_SOF_AMD_TOPLEVEL
./scripts/config --module CONFIG_SND_SOC_SOF_PCI
./scripts/config --module CONFIG_SND_SOC_SOF_ACPI
./scripts/config --enable CONFIG_USER_NS
./scripts/config --enable CONFIG_CGROUPS
./scripts/config --enable CONFIG_SECCOMP
./scripts/config --enable CONFIG_ZRAM
./scripts/config --enable CONFIG_ZRAM_BACKEND_ZSTD
./scripts/config --enable CONFIG_ZRAM_DEF_COMP_ZSTD
./scripts/config --enable CONFIG_VIRTIO_BLK
./scripts/config --enable CONFIG_VIRTIO_PCI
./scripts/config --enable CONFIG_VIRTIO_BALLOON
./scripts/config --enable CONFIG_VIRTIO_CONSOLE
./scripts/config --enable CONFIG_VIRTIO_INPUT
./scripts/config --module CONFIG_VIRTIO_FS
./scripts/config --disable CONFIG_ZSWAP
./scripts/config --set-str CONFIG_LOCALVERSION "-zaod"
./scripts/config --enable CONFIG_STACKPROTECTOR_STRONG
./scripts/config --enable CONFIG_HARDENED_USERCOPY
./scripts/config --set-val CONFIG_KPTR_RESTRICT 2
./scripts/config --enable CONFIG_INIT_ON_ALLOC_DEFAULT_ON
./scripts/config --enable CONFIG_FORTIFY_SOURCE
./scripts/config --enable CONFIG_RANDOMIZE_BASE
./scripts/config --disable CONFIG_DEBUG_INFO

make olddefconfig >/dev/null
cp .config "$ROOT_DIR/kernel/zaod_defconfig"
python3 "$ROOT_DIR/tests/check_kernel_config.py" "$CONFIG_FILE"
if [[ "${CONFIG_ONLY:-0}" == "1" ]]; then
  printf 'Kernel configuration validated: %s\n' "$CONFIG_FILE"
  exit 0
fi

BUILD_START=$SECONDS
if command -v ccache >/dev/null 2>&1; then
  export CCACHE_DIR="${CCACHE_DIR:-$ROOT_DIR/build/cache/ccache}"
  export CC="ccache gcc"
fi
make -j"$JOBS" bzImage modules > "$OUT_DIR/build.log" 2>&1 || {
  tail -n 80 "$OUT_DIR/build.log"
  exit 1
}

cp arch/x86/boot/bzImage "$OUT_DIR/vmlinuz"
cp System.map "$OUT_DIR/System.map"
cp .config "$OUT_DIR/config"

KERNEL_RELEASE="$(make -s kernelrelease)"
rm -rf "$OUT_DIR/modules-root"
mkdir -p "$OUT_DIR/modules-root"
make modules_install INSTALL_MOD_PATH="$OUT_DIR/modules-root" INSTALL_MOD_STRIP=1 >/dev/null

# `make modules_install` runs depmod, but a host without kmod (or a depmod
# that refuses a newer module format) leaves an archive with no modules.dep,
# and the initramfs builder cannot resolve a single driver without it. Run it
# here and refuse to hand over an archive the next stage cannot use.
MODULES_DIR="$OUT_DIR/modules-root/lib/modules/$KERNEL_RELEASE"
if [[ ! -s "$MODULES_DIR/modules.dep" ]]; then
  printf 'modules.dep is absent after modules_install; running depmod for %s\n' "$KERNEL_RELEASE"
  if ! depmod -b "$OUT_DIR/modules-root" "$KERNEL_RELEASE"; then
    printf 'depmod failed for %s; the modules archive would be unusable\n' "$KERNEL_RELEASE" >&2
    exit 1
  fi
fi
[[ -s "$MODULES_DIR/modules.dep" ]] || {
  printf 'modules.dep is still missing from %s\n' "$MODULES_DIR" >&2
  exit 1
}

find "$OUT_DIR/modules-root/lib/modules/$KERNEL_RELEASE" -type f -name '*.ko*' -printf '%P\n' \
  | sort > "$OUT_DIR/modules.list"

tar -C "$OUT_DIR/modules-root" -cf "$OUT_DIR/modules.tar" .
GZIP=-9 tar -C "$OUT_DIR/modules-root" -czf "$OUT_DIR/modules.tar.gz" .

printf 'Build time: %ss\n' "$((SECONDS - BUILD_START))"
printf 'Kernel release: %s\n' "$KERNEL_RELEASE"
printf 'Kernel image: %s\n' "$OUT_DIR/vmlinuz"
printf 'Kernel config: %s\n' "$OUT_DIR/config"
printf 'Modules archive: %s\n' "$OUT_DIR/modules.tar.gz"
printf 'Module list: %s (%s modules)\n' "$OUT_DIR/modules.list" "$(wc -l < "$OUT_DIR/modules.list")"
