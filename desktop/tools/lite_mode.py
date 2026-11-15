#!/usr/bin/env python3
"""Zaod OS Lite mode decision logic and applier.

Lite mode targets the PRD minimum hardware (2 GB RAM, two-core Celeron-class
CPU, software or low-end DRM GPU). The decision is deliberately made from two
measured inputs only - total system memory and whether a usable DRM render
device exists - so the result is reproducible and testable without a desktop
session.

PRD references:
  section 3  - minimum hardware, idle RAM budget
  section 9 Phase 5 - adaptive Lite mode, zram/earlyoom/swappiness, Wayland
                      default with X11 fallback
Frozen behaviour (tested in tests/test_lite_mode.py):
  * <= 2560 MB total RAM      -> lite
  * >= 3840 MB and DRM GPU    -> full
  * software rendering only   -> lite, regardless of RAM
  * 2561-3839 MB              -> lite (conservative: Plasma 6 + Firefox on
                                       3 GB is still inside the low budget)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MODE_LITE = "lite"
MODE_FULL = "full"

# Decision thresholds in mebibytes, see the module docstring.
LITE_MAX_MB = 2560
FULL_MIN_MB = 3840

GPU_HARDWARE = "hardware"
GPU_SOFTWARE = "software"
GPU_UNKNOWN = "unknown"

# Configuration files rewritten by --apply. Everything is written below the
# injected root so tests never touch a real home directory.
MANAGED_FILES = (
    "kwinrc",
    "kdeglobals",
    "baloofilerc",
    "zaod-lite.conf",
)


class LiteModeError(RuntimeError):
    """Raised for unusable inputs (missing root, unreadable meminfo)."""


@dataclass(frozen=True)
class HostProfile:
    """Measured host facts that drive the decision."""

    total_mb: int
    gpu: str
    mem_source: str = ""
    gpu_source: str = ""


@dataclass(frozen=True)
class Decision:
    mode: str
    reasons: tuple
    profile: HostProfile

    @property
    def is_lite(self) -> bool:
        return self.mode == MODE_LITE

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reasons": list(self.reasons),
            "total_mb": self.profile.total_mb,
            "gpu": self.profile.gpu,
            "mem_source": self.profile.mem_source,
            "gpu_source": self.profile.gpu_source,
        }


def parse_meminfo(text: str) -> int:
    """Return total RAM in MiB from /proc/meminfo content.

    Raises LiteModeError when MemTotal is missing or unusable rather than
    silently guessing a size.
    """
    match = re.search(r"^MemTotal:\s+(\d+)\s*kB\s*$", text, re.MULTILINE)
    if not match:
        raise LiteModeError("MemTotal not found in meminfo")
    kib = int(match.group(1))
    if kib <= 0:
        raise LiteModeError("MemTotal must be positive")
    return kib // 1024


def read_total_mb(meminfo_path: Path) -> int:
    try:
        text = meminfo_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - host dependent
        raise LiteModeError(f"cannot read {meminfo_path}: {exc}") from exc
    return parse_meminfo(text)


def detect_gpu(drm_root: Path, modules_root: Path | None = None) -> str:
    """Classify the graphics stack as hardware, software or unknown.

    A DRM card counts as hardware when it exposes a driver entry that is not
    one of the software fallbacks (simple-framebuffer, simpledrm, vkms). The
    module list is only consulted when /sys/class/drm is unreadable.
    """
    if drm_root.is_dir():
        for card in sorted(drm_root.glob("card[0-9]*")):
            driver_link = card / "device" / "driver"
            try:
                driver = os.path.basename(os.path.realpath(driver_link))
            except OSError:
                driver = ""
            if not driver or driver in {"simple-framebuffer", "simpledrm", "vkms", "vgem"}:
                continue
            return GPU_HARDWARE
        # Cards exist but none expose a real driver, or no card at all.
        return GPU_SOFTWARE
    if modules_root is not None and modules_root.is_dir():
        names = {p.name.split(".")[0] for p in modules_root.glob("*.ko*")}
        hardware = names & {
            "i915",
            "xe",
            "amdgpu",
            "radeon",
            "nouveau",
            "virtio_gpu",
            "vmwgfx",
            "qxl",
        }
        if hardware:
            return GPU_HARDWARE
    return GPU_UNKNOWN


def decide(total_mb: int, gpu: str) -> Decision:
    """Pure decision function. Every threshold is documented above."""
    if total_mb <= 0:
        raise LiteModeError("total_mb must be positive")
    reasons = []
    if gpu == GPU_SOFTWARE:
        reasons.append("software rendering only")
    if total_mb <= LITE_MAX_MB:
        reasons.append(f"{total_mb} MB RAM is at or below the {LITE_MAX_MB} MB lite threshold")
    if reasons:
        mode = MODE_LITE
    elif total_mb >= FULL_MIN_MB:
        mode = MODE_FULL
        reasons.append(f"{total_mb} MB RAM at or above the {FULL_MIN_MB} MB full threshold")
        if gpu == GPU_UNKNOWN:
            reasons.append("GPU state unknown, treated as usable")
    else:
        mode = MODE_LITE
        reasons.append(
            f"{total_mb} MB RAM is between {LITE_MAX_MB} and {FULL_MIN_MB} MB, staying lite"
        )
    profile = HostProfile(total_mb=total_mb, gpu=gpu)
    return Decision(mode=mode, reasons=tuple(reasons), profile=profile)


def write_configs(mode: str, config_root: Path, dry_run: bool = False) -> list:
    """Write the managed config files for a mode below config_root.

    Returns the list of written paths. The operation is idempotent: rewritten
    content depends only on the mode, so a second call changes nothing.
    """
    if mode not in {MODE_LITE, MODE_FULL}:
        raise LiteModeError(f"unknown mode {mode!r}")
    lite = mode == MODE_LITE
    contents = {
        "zaod-lite.conf": f"[Zaod]\nMode={mode}\n",
        "kwinrc": (
            "[Compositing]\n"
            "Enabled={}\n"
            "OpenGLIsUnsafe={}\n"
            "LatencyPolicy={}\n"
            "MaxFPS={}\n"
            "\n[Effect-blur]\n"
            "Enabled={}\n"
            "\n[Effect-windowview]\n"
            "Enabled={}\n"
            "\n[Plugins]\n"
            "blurEnabled={}\n"
            "contrastEnabled={}\n"
            "kwin4_effect_dimscreenEnabled={}\n"
        ).format(
            "true",
            "false",
            "Low" if lite else "Medium",
            "30" if lite else "60",
            "false",
            "false",
            "false",
            "false",
            "true",
        ),
        "kdeglobals": (
            "[KDE]\n"
            "AnimationDurationFactor={}\n"
            "SingleClick=false\n"
            "ShowDeleteCommand=false\n"
            "\n[General]\n"
            "ColorScheme=ZaodColors{}\n"
            "\n[KDE Action Restrictions][$i]\n"
            "action/balooctl=false\n"
        ).format("0" if lite else "1", "Lite" if lite else "Dark"),
        "baloofilerc": (
            "[Basic Settings]\n"
            "Indexing-Enabled={}\n"
            "\n[General]\n"
            "dbVersion=2\n"
            "exclude filters=*.o,*.part,*.iso,*.img\n"
        ).format("false" if lite else "true"),
    }
    written = []
    for name in MANAGED_FILES:
        target = config_root / name
        written.append(target)
        if dry_run:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents[name], encoding="utf-8")
    return written


def read_state(config_root: Path) -> dict:
    state_file = config_root / "zaod-lite.conf"
    if not state_file.is_file():
        return {"mode": None}
    text = state_file.read_text(encoding="utf-8")
    match = re.search(r"^Mode=(lite|full)$", text, re.MULTILINE)
    return {"mode": match.group(1) if match else None}


def collect_profile(meminfo_path: Path, drm_root: Path, modules_root: Path | None = None) -> HostProfile:
    total_mb = read_total_mb(meminfo_path)
    gpu = detect_gpu(drm_root, modules_root)
    return HostProfile(
        total_mb=total_mb,
        gpu=gpu,
        mem_source=str(meminfo_path),
        gpu_source=str(drm_root if drm_root.is_dir() else modules_root or ""),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lite-mode",
        description="Detect and apply the Zaod OS Lite mode profile.",
    )
    parser.add_argument("--status", action="store_true", help="print the current decision and state")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--apply", action="store_true", help="write the config files for the decision")
    parser.add_argument("--dry-run", action="store_true", help="report actions without writing")
    parser.add_argument("--force-lite", action="store_true", help="force Lite mode")
    parser.add_argument("--force-full", action="store_true", help="force full mode")
    parser.add_argument(
        "--root",
        default="/",
        help="filesystem root used to read meminfo/drm and to write config (tests)",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="override the KDE config directory (default <root>/etc/skel/.config)",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    meminfo = root / "proc/meminfo"
    drm = root / "sys/class/drm"
    modules = root / "lib/modules"
    config_dir = Path(args.config_dir) if args.config_dir else root / "etc/skel/.config"
    try:
        profile = collect_profile(meminfo, drm, modules)
        if args.force_lite and args.force_full:
            raise LiteModeError("--force-lite and --force-full are mutually exclusive")
        if args.force_lite:
            decision = Decision(MODE_LITE, ("forced by --force-lite",), profile)
        elif args.force_full:
            decision = Decision(MODE_FULL, ("forced by --force-full",), profile)
        else:
            decision = decide(profile.total_mb, profile.gpu)
        payload = decision.as_dict()
        if args.apply:
            payload["written"] = [str(p) for p in write_configs(decision.mode, config_dir, args.dry_run)]
            payload["dry_run"] = args.dry_run
        payload["current_state"] = read_state(config_dir)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"Zaod Lite mode: {decision.mode}")
            print(f"  RAM: {profile.total_mb} MB ({profile.mem_source})")
            print(f"  GPU: {profile.gpu} ({profile.gpu_source})")
            for reason in decision.reasons:
                print(f"  reason: {reason}")
            for path in payload.get("written", ()):
                print(f"  wrote: {path}")
    except LiteModeError as exc:
        print(f"lite-mode: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
