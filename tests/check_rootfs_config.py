#!/usr/bin/env python3
"""Static checks for the Phase 3 base-system build.

The rootfs itself cannot be built without root and network access, so this
validates the inputs and the build script: the package set, the removal list,
every shipped configuration file, and the guarantees the script claims.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOTFS = REPO_ROOT / "rootfs"
FILES = ROOTFS / "files"
SCRIPT = REPO_ROOT / "scripts/build-rootfs.sh"


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


def listing(path: Path) -> list:
    entries = []
    for line in read(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        entries.append(stripped)
    return entries


def check_package_list(report: Report) -> None:
    packages = listing(ROOTFS / "packages.list")
    report.check(bool(packages), "rootfs/packages.list is not empty")
    report.check(len(packages) >= 80, "the package set is curated rather than minimal", f"{len(packages)} entries")

    duplicates = {name for name in packages if packages.count(name) > 1}
    report.check(not duplicates, "no duplicate packages", ", ".join(sorted(duplicates)))

    required = {
        "systemd": "init",
        "dbus": "IPC",
        "network-manager": "networking",
        "wpasupplicant": "wifi",
        "bluez": "bluetooth",
        "pipewire": "audio",
        "wireplumber": "audio session",
        "mesa-vulkan-drivers": "graphics",
        "libinput10": "input",
        "sddm": "login manager",
        "labwc": "compositor",
        "foot": "terminal",
        "thunar": "file manager",
        "xdg-desktop-portal-gtk": "portal",
        "polkitd": "authorisation",
        "bubblewrap": "sandbox",
        "zram-tools": "memory",
        "earlyoom": "memory pressure",
        "python3": "runtime",
        "fonts-inter": "font",
        "fonts-noto-core": "font",
        "fonts-jetbrains-mono": "font",
        "squashfs-tools": "image tooling",
        "zstd": "compression",
    }
    for name, purpose in required.items():
        report.check(name in packages, f"{purpose} package present: {name}")

    # The desktop is Zaod's own: the shell is desktop/shell, the compositor is
    # labwc and the apps are first-party or plain GTK. A Plasma/KDE package in
    # this list either pulls a second desktop into the image or replaces the
    # session that the Zaod panel runs in.
    kde = {
        name
        for name in packages
        if name.startswith(("plasma", "kwin", "kde-", "kf6-", "libkf6", "libkscreen", "kio"))
        or name in {"dolphin", "konsole", "kwalletmanager", "kscreen", "powerdevil",
                    "breeze-gtk-theme", "xdg-desktop-portal-kde", "polkit-kde-agent-1"}
    }
    report.check(not kde, "the desktop is Zaod's own, with no Plasma/KDE package", ", ".join(sorted(kde)))

    forbidden = {"apt", "aptitude", "dpkg", "synaptic", "packagekit", "gnome-software"}
    present = forbidden & set(packages)
    report.check(not present, "the install set contains no package manager", ", ".join(sorted(present)))

    report.check(
        all(not name.startswith("-") for name in packages),
        "no package entry looks like a flag",
    )


def check_build_guards(report: Report) -> None:
    """The build's own sanity list has to name the desktop this image ships.

    build-rootfs.sh refuses to run when a required package is missing from
    packages.list; while it still demanded plasma-desktop, removing Plasma made
    every image build fail before debootstrap started.
    """
    script = (ROOTFS.parent / "scripts" / "build-rootfs.sh").read_text()
    report.check("labwc" in script, "the build requires the Zaod compositor")
    report.check(
        "plasma-desktop" not in script,
        "the build does not require a Plasma package",
    )


def check_removal_list(report: Report) -> None:
    removals = listing(ROOTFS / "rootfs.remove.list")
    report.check(bool(removals), "rootfs/rootfs.remove.list is not empty")
    for path in (
        "/usr/bin/apt",
        "/usr/bin/apt-get",
        "/usr/bin/apt-cache",
        "/usr/bin/dpkg",
        "/usr/bin/dpkg-query",
        "/usr/bin/dpkg-deb",
        "/etc/apt",
        "/var/lib/apt",
        "/var/lib/dpkg",
    ):
        report.check(path in removals, f"removal list covers {path}")
    report.check(
        all(path.startswith("/") for path in removals),
        "every removal entry is an absolute path",
    )
    report.check(
        not any(path in {"/", "/*", "/usr", "/etc", "/var"} for path in removals),
        "the removal list never names a system-wide directory",
    )


def check_shipped_files(report: Report) -> None:
    os_release = read(FILES / "etc/os-release")
    report.check(bool(os_release), "os-release is shipped")
    report.contains(os_release, 'NAME="Zaod OS"', "os-release names Zaod OS")
    report.contains(os_release, "ID=zaod", "os-release identifies the distribution as zaod")
    report.contains(os_release, "VERSION_ID=", "os-release carries a version id")
    report.contains(os_release, "HOME_URL=", "os-release carries a URL")
    report.check("debian" not in os_release.replace("ID_LIKE=debian", ""), "os-release is not a Debian copy")

    locale = read(FILES / "etc/locale.gen")
    report.contains(locale, "en_US.UTF-8 UTF-8", "en_US.UTF-8 is generated")

    default_locale = read(FILES / "etc/default-locale")
    report.contains(default_locale, "LANG=en_US.UTF-8", "the default locale is en_US.UTF-8")

    zone_note = read(FILES / "etc/timezone-note")
    report.check(bool(zone_note), "the timezone decision is documented")
    report.check(
        not (FILES / "etc/localtime").exists(),
        "no build-host timezone is baked into the image",
    )

    sudoers = read(FILES / "etc/sudoers.d/zaod-desktop")
    report.contains(sudoers, "%wheel ALL=(ALL:ALL) ALL", "wheel may administer the machine")
    report.check(
        "NOPASSWD" not in sudoers,
        "no passwordless sudo rule is shipped",
    )

    polkit = read(FILES / "etc/polkit-1/rules.d/50-zaod-desktop.rules")
    report.contains(polkit, "polkit.addAdminRule", "polkit admin rule is present")
    report.contains(polkit, 'subject.isInGroup("wheel")', "polkit grants wheel the admin role")
    report.check(
        "polkit.Result.NO" in polkit,
        "polkit refuses PackageKit so only zaod installs packages",
    )

    journald = read(FILES / "etc/systemd/journald.conf.d/zaod.conf")
    report.contains(journald, "Storage=persistent", "the installed system keeps a bounded journal")
    report.contains(journald, "SystemMaxUse=", "journal disk use is capped")
    live_journal = read(FILES / "etc/systemd/journald.conf.d/zaod-live.conf")
    report.contains(live_journal, "Storage=volatile", "live sessions keep the journal in RAM")

    zram = read(FILES / "etc/default/zramswap")
    report.contains(zram, "ALGO=zstd", "zram uses zstd")
    report.contains(zram, "PERCENT=", "zram is sized from RAM")
    report.contains(zram, "PRIORITY=", "zram swap is preferred over disk")

    sysctl = read(FILES / "etc/sysctl.d/90-zaod-memory.conf")
    report.contains(sysctl, "vm.swappiness", "swappiness is set")
    report.contains(sysctl, "vm.min_free_kbytes", "a free-memory floor is kept")

    earlyoom = read(FILES / "etc/earlyoom.conf")
    report.contains(earlyoom, "EARLYOOM_ARGS", "earlyoom is configured")
    report.contains(earlyoom, "--avoid", "earlyoom protects the session processes")
    report.contains(earlyoom, "--prefer", "earlyoom prefers killing browsers first")

    hostname = read(FILES / "etc/hostname").strip()
    report.check(bool(hostname), "a hostname is shipped")
    hosts = read(FILES / "etc/hosts")
    report.contains(hosts, "zaod", "hosts resolves the hostname")


def check_build_script(report: Report) -> None:
    text = read(SCRIPT)
    if not report.check(bool(text), "scripts/build-rootfs.sh exists"):
        return
    report.check(SCRIPT.stat().st_mode & 0o111 != 0, "build-rootfs.sh is executable")
    report.contains(text, "set -euo pipefail", "build-rootfs.sh is strict")
    report.contains(text, "--check", "build-rootfs.sh supports a dry run")
    report.contains(text, "debootstrap", "the base is bootstrapped, not copied")
    report.contains(text, "mmdebstrap", "mmdebstrap is preferred when available")
    report.contains(text, "--components=main,contrib,non-free-firmware", "firmware components are enabled")
    report.contains(text, "dpkg-query", "the SBOM comes from the package database")
    report.contains(text, "/usr/share/zaod/sbom.txt", "the SBOM path is the documented one")
    report.contains(text, "/usr/share/zaod/licenses", "licence texts are exported")
    report.contains(text, "find \"$range\" -mindepth 1 -delete", "documentation is stripped")
    report.contains(text, "survivors", "the build verifies that removal actually happened")
    report.contains(text, "command -v $binary", "the build checks the removed binaries are off PATH")
    report.contains(text, "-comp zstd", "the image is squashed with zstd")
    report.contains(text, '-Xcompression-level "$SQUASH_LEVEL"', "the compression level is explicit")
    report.contains(text, 'SQUASH_LEVEL="${SQUASH_LEVEL:-19}"', "the default squash level is 19")
    report.contains(text, "MAX_UNCOMPRESSED_MB", "the size budget is enforced")
    report.contains(text, "du -sk", "the uncompressed size is measured")
    report.check(
        re.search(r"ROOTFS_DIR:?[}\"]?", text) is not None,
        "the target directory is expanded safely",
    )
    report.check(
        "${ROOTFS_DIR:?}" in text,
        "removal paths are guarded against an empty root",
    )
    report.check(
        "rm -rf /" not in text.replace("rm -rf \"$ROOTFS_DIR\"", ""),
        "the script never removes a bare system path on the host",
    )
    for token in ("apt-get install", "apt install"):
        report.check(token not in text, f"the build does not call {token} on the host")


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    report = Report(verbose=args.verbose)
    for check in (
        check_package_list,
        check_removal_list,
        check_build_guards,
        check_shipped_files,
        check_build_script,
    ):
        check(report)

    for failure in report.failures:
        print(f"  FAIL {failure}")
    print(f"rootfs config checks: {report.run} run, {len(report.failures)} failed")
    if report.failures:
        print("rootfs config checks: FAIL")
        return 1
    print("rootfs config checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
