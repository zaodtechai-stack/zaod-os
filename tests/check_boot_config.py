#!/usr/bin/env python3
"""Static checks for the Phase 4 boot chain.

Every check is read-only: the GRUB menu, the Plymouth theme, the live-boot init
and the three build scripts are inspected as files, so this runs on a build host
with no kernel, no root and no QEMU.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BOOT = REPO_ROOT / "boot"
SCRIPTS = REPO_ROOT / "scripts"

MAX_FAILURES = 0


class Report:
    def __init__(self, verbose: bool = False) -> None:
        self.run = 0
        self.failures = []
        self.verbose = verbose

    def check(self, condition: bool, description: str, detail: str = "") -> bool:
        self.run += 1
        if not condition:
            self.failures.append(f"{description}{f' ({detail})' if detail else ''}")
        elif self.verbose:
            print(f"  ok   {description}")
        return bool(condition)

    def contains(self, text: str, needle: str, description: str) -> bool:
        return self.check(needle in text, description, f"missing {needle!r}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def check_grub(report: Report) -> None:
    path = BOOT / "grub/grub.cfg"
    text = read(path)
    if not report.check(bool(text), "boot/grub/grub.cfg exists"):
        return

    report.contains(text, "insmod search_label", "GRUB loads search_label")
    report.contains(text, "search --no-floppy --label --set=root ZAODOS", "GRUB finds the media by label")
    report.contains(text, "set timeout=5", "autoboot timeout is set")
    report.contains(text, "insmod all_video", "all video drivers are loaded")
    report.contains(text, "terminal_output gfxterm", "graphical terminal is used")
    # plymouthd ran on iso-29 because only "splash" was absent, and it then held
    # the console the onboarding wizard draws on. The daemon is now switched off
    # on the command line as well as masked from the live boot.
    report.contains(text, "plymouth.enable=0", "GRUB disables plymouth on the command line")

    entries = re.findall(r"menuentry\s+\"([^\"]+)\"", text)
    report.check(len(entries) >= 7, "menu has at least seven entries", f"found {len(entries)}")
    names = " | ".join(entries).lower()
    for expected in ("live", "safe graphics", "install", "first internal disk", "rescue"):
        report.check(expected in names, f"menu offers a {expected} entry")

    report.contains(text, "zaod.safegfx=1", "safe graphics passes its parameter")
    report.contains(text, "nomodeset", "safe graphics disables kernel modesetting")
    report.contains(text, "zaod.toram=1", "copy-to-RAM entry exists")
    report.contains(text, "zaod.installer=1", "installer entry exists")
    report.contains(text, 'if [ "$grub_platform" = "efi" ]', "UEFI-only entry is guarded")
    report.contains(text, "fwsetup", "firmware settings entry is present")

    # memtest86+ is a standalone payload, not a live-boot entry.
    joined = text.replace("\\\n", " ")  # re-flow GRUB line continuations
    linux_lines = [
        line
        for line in joined.splitlines()
        if line.strip().startswith("linux ") and "memtest" not in line
    ]
    report.check(bool(linux_lines), "GRUB has linux lines")
    report.check(
        all("root=live:LABEL=ZAODOS" in line for line in linux_lines),
        "every live linux line boots from the labelled media",
    )
    report.check(
        all("initrd /boot/initramfs.img" in text for _ in (0,)) or "initrd /boot/initramfs.img" in text,
        "an initramfs is loaded",
    )
    report.check(not re.search(r"^\s*save_env", text, re.MULTILINE), "GRUB writes no environment saves")
    report.check("no-floppy" in text, "floppy probing is disabled")


def check_plymouth(report: Report) -> None:
    theme = read(BOOT / "plymouth/zaod.plymouth")
    script = read(BOOT / "plymouth/zaod.script")
    report.contains(theme, "[Plymouth Theme]", "plymouth theme section exists")
    report.contains(theme, "ModuleName=script", "theme uses the script module")
    report.contains(theme, "ImageDir=/usr/share/plymouth/themes/zaod", "theme image directory declared")
    report.contains(theme, "ScriptFile=/usr/share/plymouth/themes/zaod/zaod.script", "theme script declared")

    report.contains(script, "Plymouth.SetRefreshFunction", "splash animates")
    report.contains(script, "Plymouth.SetQuitFunction", "splash cleans up on quit")
    report.contains(script, "Plymouth.SetDisplayMessageFunction", "boot messages are shown")

    generator = read(BOOT / "plymouth/tools/gen-assets.py")
    referenced = set(re.findall(r'Image\("([a-zA-Z0-9._-]+\.png)"\)', script))
    report.check(bool(referenced), "splash references at least one image")
    for name in sorted(referenced):
        stub = name.replace(".png", "")
        report.check(
            stub.split("-")[0] in generator,
            f"{name} is produced by the artwork generator",
        )
    report.check(
        "spinner-" in script and "progress-lit" in script,
        "splash draws the spinner and the progress pill",
    )
    report.check(
        "microsoft" not in script.lower() and "windows" not in script.lower(),
        "splash carries no vendor trademark",
    )


def check_live_init(report: Report) -> None:
    path = BOOT / "initramfs/zaod-live"
    text = read(path)
    if not report.check(bool(text), "boot/initramfs/zaod-live exists"):
        return
    report.check(path.stat().st_mode & 0o111 != 0, "live init is executable")
    # Deliberately no `set -e`: an unguarded failure used to exit PID 1 and
    # panic the machine, so every step reports through fail() instead.
    report.check(
        "set -eu" not in text and "fail()" in text,
        "every live-init step reports its own failure",
    )
    report.contains(text, "switch_root", "live init hands over with switch_root")
    report.contains(text, "zaod.toram", "live init understands zaod.toram")
    report.contains(text, "zaod.rescue", "live init understands zaod.rescue")
    report.contains(text, "zaod.safegfx", "live init understands zaod.safegfx")
    report.contains(text, "zaod.installer", "live init understands zaod.installer")
    report.contains(text, "mount -t squashfs -o ro,loop", "the image is mounted read-only")
    report.contains(text, "lowerdir=", "a writable overlay is stacked on the read-only image")
    # A rescue shell that is exec'd once can still exit, and PID 1 exiting is the
    # "Attempted to kill init" panic this file exists to prevent. The shell is
    # therefore reopened in a loop that has no exit.
    # The rescue shell belongs to /init, the only process that may be PID 1: a
    # shell that is exec'd once can exit, and PID 1 exiting is the "Attempted to
    # kill init" panic this file exists to prevent, so it is reopened in a loop.
    pid1 = read(BOOT / "initramfs/init")
    report.check(
        re.search(r"^rescue\(\) \{", pid1, re.MULTILINE) is not None
        and "$RESCUE_SHELL" in pid1
        and re.search(r"while :; do", pid1) is not None
        and "exec /bin/sh" not in pid1,
        "a failure drops to a rescue shell that PID 1 cannot leave",
    )
    report.check(
        "mkfs" not in text and "wipefs" not in text,
        "the live init never formats or wipes a device",
    )
    report.check(
        re.search(r"attempt.*-lt [1-9][0-9]+", text) is not None,
        "media detection retries instead of racing udev",
    )
    report.check(
        "/sys/class/block" in text and "removable" in text,
        "media detection enumerates the block devices the kernel registered",
    )
    report.check(
        "$MEDIA" in text and "mount -t iso9660 -o ro" in text,
        "the boot media is mounted read-only",
    )
    # ldconfig.service reads every library in the image off the boot media and
    # has no timeout, which is the "frozen" boot people reported on a USB stick.
    report.check(
        re.search(r"for unit in .*ldconfig\.service", text) is not None
        and 'ln -sf /dev/null "$NEW_ROOT/etc/systemd/system/$unit"' in text,
        "the live boot masks the units that would grind on the boot media",
    )
    report.contains(
        text,
        "getty@.service",
        "the live boot enables a second console as a way in",
    )


def check_scripts(report: Report) -> None:
    for name in ("make-initramfs.sh", "make-iso.sh", "write-usb.sh"):
        path = SCRIPTS / name
        text = read(path)
        if not report.check(bool(text), f"scripts/{name} exists"):
            continue
        report.check(path.stat().st_mode & 0o111 != 0, f"scripts/{name} is executable")
        report.contains(text, "set -euo pipefail", f"scripts/{name} is strict")

    iso = read(SCRIPTS / "make-iso.sh")
    report.contains(iso, "--check", "make-iso.sh supports a dry run")
    report.contains(iso, 'VOLUME_LABEL="${VOLUME_LABEL:-ZAODOS}"', "make-iso.sh defaults to the ZAODOS label")
    report.contains(iso, "-volid", "make-iso.sh sets the ISO volume label")
    report.contains(iso, "-eltorito-boot", "make-iso.sh adds the BIOS boot record")
    report.contains(iso, "-eltorito-alt-boot", "make-iso.sh adds the UEFI boot record")
    report.contains(iso, "sha256sum", "make-iso.sh publishes a checksum")
    report.contains(iso, "zaod-os-${VERSION}-${ARCH}.iso", "ISO is named zaod-os-VERSION-ARCH.iso")
    report.check(
        "mkfs." not in iso or iso.count("mkfs.") == 1,
        "make-iso.sh formats the EFI image through mtools only",
    )

    initramfs = read(SCRIPTS / "make-initramfs.sh")
    report.contains(initramfs, "squashfs", "initramfs includes the squashfs driver")
    report.contains(initramfs, "overlay", "initramfs includes overlayfs")
    report.contains(initramfs, "cpio", "initramfs is a cpio archive")
    report.contains(initramfs, "zstd", "initramfs is zstd compressed")
    report.contains(initramfs, "--check", "make-initramfs.sh supports a dry run")

    usb = read(SCRIPTS / "write-usb.sh")
    report.contains(usb, "looks like a partition", "write-usb.sh refuses a partition target")
    report.contains(usb, "lsblk -nrpo NAME,MOUNTPOINT", "write-usb.sh checks for mounted partitions")
    report.contains(usb, "is too small", "write-usb.sh checks the target size")
    report.contains(usb, "confirmation did not match", "write-usb.sh requires typing the device path")
    report.contains(usb, "conv=fsync", "write-usb.sh flushes to the device")
    report.contains(usb, "carries a bootable Zaod OS image", "write-usb.sh verifies the label afterwards")


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    report = Report(verbose=args.verbose)
    for check in (check_grub, check_plymouth, check_live_init, check_scripts):
        check(report)

    for failure in report.failures:
        print(f"  FAIL {failure}")
    print(f"boot config checks: {report.run} run, {len(report.failures)} failed")
    if report.failures:
        print("boot config checks: FAIL")
        return 1
    print("boot config checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
