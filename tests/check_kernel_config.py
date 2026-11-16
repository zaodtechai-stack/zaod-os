#!/usr/bin/env python3
"""Validate the Zaod kernel config against the Phase 2 requirements."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = {
    "CONFIG_EFI": "y",
    "CONFIG_EFI_STUB": "y",
        "CONFIG_FB": "y",
    "CONFIG_FB_EFI": "y",
    "CONFIG_FRAMEBUFFER_CONSOLE": "y",
    "CONFIG_DRM": "y",
    "CONFIG_DRM_I915": "m",
    "CONFIG_DRM_AMDGPU": "m",
    "CONFIG_DRM_RADEON": "m",
    "CONFIG_DRM_VIRTIO_GPU": "m",
    "CONFIG_DRM_SIMPLEDRM": "y",
    "CONFIG_SATA_AHCI": "y",
    "CONFIG_NVME_CORE": "m",
    "CONFIG_BLK_DEV_NVME": "m",
    "CONFIG_USB_XHCI_HCD": "y",
    "CONFIG_USB_EHCI_HCD": "y",
    "CONFIG_USB_STORAGE": "m",
    "CONFIG_USB_HID": "y",
    "CONFIG_EXT4_FS": "y",
    "CONFIG_VFAT_FS": "y",
    "CONFIG_SQUASHFS": "y",
    "CONFIG_SQUASHFS_ZSTD": "y",
    "CONFIG_OVERLAY_FS": "y",
    "CONFIG_ISO9660_FS": "m",
    "CONFIG_BLK_DEV_LOOP": "y",
    "CONFIG_TMPFS": "y",
    "CONFIG_DEVTMPFS": "y",
    "CONFIG_DEVTMPFS_MOUNT": "y",
    "CONFIG_INPUT_EVDEV": "y",
    "CONFIG_E1000E": "m",
    "CONFIG_IGC": "m",
    "CONFIG_R8169": "y",
    "CONFIG_IWLWIFI": "m",
    "CONFIG_RTW88": "m",
    "CONFIG_RTW88_8822BE": "m",
    "CONFIG_RTW88_8822CE": "m",
    "CONFIG_RTW88_8723DE": "m",
    "CONFIG_RTW88_8821CE": "m",
    "CONFIG_RTW89": "m",
    "CONFIG_RTW89_8851BE": "m",
    "CONFIG_RTW89_8852AE": "m",
    "CONFIG_RTW89_8852BE": "m",
    "CONFIG_RTW89_8852CE": "m",
    "CONFIG_ATH9K": "m",
    "CONFIG_ATH10K": "m",
    "CONFIG_ATH10K_PCI": "m",
    "CONFIG_ATH11K": "m",
    "CONFIG_ATH11K_PCI": "m",
    "CONFIG_BRCMFMAC": "m",
    "CONFIG_BRCMFMAC_PCIE": "y",
    "CONFIG_BRCMFMAC_SDIO": "y",
    "CONFIG_BRCMFMAC_USB": "y",
    "CONFIG_CFG80211": "y",
    "CONFIG_MMC": "y",
    "CONFIG_MAC80211": "y",
    "CONFIG_BT": "y",
    "CONFIG_BT_HCIBTUSB": "y",
    "CONFIG_BT_HCIBTUSB_MTK": "y",
    "CONFIG_BT_HCIBTUSB_RTL": "y",
    "CONFIG_VIRTIO_NET": "y",
    "CONFIG_SOUND": "y",
    "CONFIG_SND_HDA_INTEL": "m",
    "CONFIG_SND_HDA_CODEC_REALTEK": "m",
    "CONFIG_SND_USB_AUDIO": "m",
    "CONFIG_ACPI": "y",
    "CONFIG_CPU_FREQ": "y",
    "CONFIG_X86_INTEL_PSTATE": "y",
    "CONFIG_X86_AMD_PSTATE": "y",
    "CONFIG_THERMAL": "y",
    "CONFIG_ACPI_BATTERY": "y",
    "CONFIG_BACKLIGHT_CLASS_DEVICE": "y",
    "CONFIG_USER_NS": "y",
    "CONFIG_CGROUPS": "y",
    "CONFIG_SECCOMP": "y",
    "CONFIG_ZRAM": "y",
    "CONFIG_VIRTIO_BLK": "y",
    "CONFIG_VIRTIO_PCI": "y",
    "CONFIG_VIRTIO_CONSOLE": "y",
    "CONFIG_VIRTIO_INPUT": "y",
    "CONFIG_VIRTIO_FS": "m",
    "CONFIG_I2C_HID_ACPI": "m",
    "CONFIG_MOUSE_PS2_SYNAPTICS": "y",
    "CONFIG_MOUSE_PS2_ELANTECH": "y",
    "CONFIG_ZRAM_BACKEND_ZSTD": "y",
    "CONFIG_ZRAM_DEF_COMP_ZSTD": "y",
    "CONFIG_SND_SOC_SOF_TOPLEVEL": "y",
    "CONFIG_SND_SOC_SOF_INTEL_TOPLEVEL": "y",
    "CONFIG_SND_SOC_SOF_AMD_TOPLEVEL": "m",
    "CONFIG_SND_SOC_SOF_PCI": "m",
    "CONFIG_SND_SOC_SOF_ACPI": "m",
    "CONFIG_KVM_GUEST": "y",
    "CONFIG_STACKPROTECTOR_STRONG": "y",
    "CONFIG_HARDENED_USERCOPY": "y",
    "CONFIG_FORTIFY_SOURCE": "y",
    "CONFIG_RANDOMIZE_BASE": "y",
}


# Nothing may rewrite kernel text while traffic is in flight: a static-key
# poke in the RX path panicked the live system on boot.
DISABLED = {
    "CONFIG_JUMP_LABEL": "runtime INT3 pokes in the network RX path panic the kernel",
    "CONFIG_PREEMPT_DYNAMIC": "boot-time static-call pokes of the same machinery",
}


def parse_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        m = re.match(r"^(CONFIG_[A-Z0-9_]+)=(.+)$", line)
        if not m:
            continue
        key, value = m.groups()
        values[key] = value.strip()
    return values


def check_localversion(values: dict[str, str]) -> bool:
    localversion = values.get("CONFIG_LOCALVERSION", "")
    return localversion == '"-zaod"' or localversion == "-zaod"


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/out/kernel/config")
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return 2

    values = parse_config(config_path)
    missing: list[str] = []
    bad: list[str] = []

    for key, expected in REQUIRED.items():
        val = values.get(key)
        if val is None:
            missing.append(key)
            continue
        if val != expected:
            bad.append(f"{key}={val} (expected {expected})")

    for key, why in DISABLED.items():
        if values.get(key) is not None:
            bad.append(f"{key}={values[key]} must stay off ({why})")

    ok = check_localversion(values)
    if not ok:
        bad.append(f"CONFIG_LOCALVERSION={values.get('CONFIG_LOCALVERSION', '<unset>')} (expected -zaod)")

    if missing or bad:
        if missing:
            print("Missing config switches:")
            for item in missing:
                print(f"  - {item}")
        if bad:
            print("Incorrect config values:")
            for item in bad:
                print(f"  - {item}")
        return 1

    print("Kernel config validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
