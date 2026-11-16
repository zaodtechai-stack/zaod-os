#!/usr/bin/env python3
"""Regression test: the kernel module archive must not clobber /lib.

The modules archive that kernel/build.sh produces starts with its own `./lib/`
entry. Debian images are merged-/usr, so in the target root `lib` is a symlink to
`usr/lib`. Extracted with a plain `tar -x`, that `./lib/` entry replaces the
symlink with a real directory: the modules end up outside usr/lib, and every path
that used to resolve through /lib (the firmware directory among them) stops
existing. Build 20 of the ISO died exactly there with

    tar: build/rootfs/lib/firmware: Cannot open: No such file or directory

This test rebuilds that situation in a temporary directory and proves the flags
the build scripts now use keep the symlink intact.
"""

from __future__ import annotations

import re
import subprocess
import tarfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOTFS = REPO_ROOT / "scripts/build-rootfs.sh"
FINALIZE_ROOTFS = REPO_ROOT / "rootfs/scripts/finalize-rootfs.sh"

KERNEL_RELEASE = "6.18.63-zaod"


def _modules_archive(tmp: Path) -> Path:
    """A miniature copy of the real archive, including its leading ./lib/."""
    stage = tmp / "stage"
    module_dir = stage / "lib/modules" / KERNEL_RELEASE
    module_dir.mkdir(parents=True)
    (module_dir / "zaod_test.ko").write_bytes(b"\x7fELF")
    (module_dir / "modules.dep").write_text("zaod_test.ko:\n")

    archive = tmp / "modules.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(stage / "lib", arcname="./lib")
    return archive


def _merged_usr_root(tmp: Path) -> Path:
    root = tmp / "rootfs"
    (root / "usr/lib").mkdir(parents=True)
    (root / "lib").symlink_to("usr/lib")
    return root


def test_plain_extraction_loses_the_lib_symlink(tmp_path: Path) -> None:
    """The failure itself, so the test proves it is testing the right thing."""
    archive = _modules_archive(tmp_path)
    root = _merged_usr_root(tmp_path)
    subprocess.run(
        ["tar", "-xzf", str(archive), "-C", str(root)],
        check=True,
        capture_output=True,
    )
    assert not (root / "lib").is_symlink()


def test_extraction_with_the_safe_flags_keeps_the_symlink(tmp_path: Path) -> None:
    archive = _modules_archive(tmp_path)
    root = _merged_usr_root(tmp_path)
    subprocess.run(
        [
            "tar",
            "-xzf",
            str(archive),
            "-C",
            str(root),
            "--keep-directory-symlink",
            "--no-same-owner",
        ],
        check=True,
        capture_output=True,
    )
    assert (root / "lib").is_symlink()
    # usr/lib/modules is where a merged-/usr system actually keeps them.
    assert (root / "usr/lib/modules" / KERNEL_RELEASE / "zaod_test.ko").is_file()
    assert not (root / "usr/lib/modules" / KERNEL_RELEASE).parent.is_symlink()


def test_scripts_unpack_the_archive_through_the_symlink() -> None:
    """Every place that unpacks the module archive has to use the flags."""
    for script in (BUILD_ROOTFS, FINALIZE_ROOTFS):
        text = script.read_text()
        # A command may be split over several lines with a trailing backslash.
        joined = text.replace("\\\n", " ")
        unpacks = [
            line
            for line in joined.splitlines()
            if re.search(r"tar\s+-[a-zA-Z]*x[a-zA-Z]*f", line)
            and "MODULES" in line.upper()
        ]
        assert unpacks, f"{script} no longer unpacks the module archive"
        for line in unpacks:
            assert "--keep-directory-symlink" in line, f"{script}: {line.strip()}"
            assert "--no-same-owner" in line, f"{script}: {line.strip()}"
