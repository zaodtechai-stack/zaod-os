#!/usr/bin/env python3
"""Unit tests for the Zaod Lite mode decision logic (Phase 5)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "desktop" / "tools"))

import lite_mode


def meminfo(total_mb: int) -> str:
    return (
        f"MemTotal:       {total_mb * 1024} kB\n"
        "MemFree:        100000 kB\n"
        "MemAvailable:   200000 kB\n"
    )


class ParseMeminfoTests(unittest.TestCase):
    def test_parses_total_mib(self):
        self.assertEqual(lite_mode.parse_meminfo(meminfo(2048)), 2048)

    def test_rounds_down_partial_mib(self):
        text = "MemTotal:        2500000 kB\n"
        self.assertEqual(lite_mode.parse_meminfo(text), 2441)

    def test_missing_memtotal_is_an_error(self):
        with self.assertRaises(lite_mode.LiteModeError):
            lite_mode.parse_meminfo("MemFree: 10 kB\n")

    def test_zero_memtotal_is_an_error(self):
        with self.assertRaises(lite_mode.LiteModeError):
            lite_mode.parse_meminfo("MemTotal: 0 kB\n")

    def test_garbage_is_an_error(self):
        with self.assertRaises(lite_mode.LiteModeError):
            lite_mode.parse_meminfo("not a meminfo file")

    def test_unreadable_path_is_an_error(self):
        with TemporaryDirectory() as tmp, self.assertRaises(lite_mode.LiteModeError):
            lite_mode.read_total_mb(Path(tmp) / "missing/meminfo")


class DetectGpuTests(unittest.TestCase):
    def test_hardware_driver_detected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "card0" / "device").mkdir(parents=True)
            target = root / "drivers" / "i915"
            target.mkdir(parents=True)
            (root / "card0" / "device" / "driver").symlink_to(target)
            self.assertEqual(lite_mode.detect_gpu(root), lite_mode.GPU_HARDWARE)

    def test_simpledrm_is_software(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "card0" / "device").mkdir(parents=True)
            target = root / "drivers" / "simpledrm"
            target.mkdir(parents=True)
            (root / "card0" / "device" / "driver").symlink_to(target)
            self.assertEqual(lite_mode.detect_gpu(root), lite_mode.GPU_SOFTWARE)

    def test_no_cards_is_software(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            self.assertEqual(lite_mode.detect_gpu(root), lite_mode.GPU_SOFTWARE)

    def test_module_list_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            drm = root / "missing-drm"
            modules = root / "modules"
            modules.mkdir()
            (modules / "amdgpu.ko.zst").write_text("x")
            self.assertEqual(lite_mode.detect_gpu(drm, modules), lite_mode.GPU_HARDWARE)

    def test_module_fallback_without_gpu_module_is_unknown(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            modules = root / "modules"
            modules.mkdir()
            (modules / "snd_hda_intel.ko.xz").write_text("x")
            self.assertEqual(
                lite_mode.detect_gpu(root / "missing-drm", modules), lite_mode.GPU_UNKNOWN
            )


class DecideTests(unittest.TestCase):
    def test_two_gigabyte_machine_is_lite(self):
        decision = lite_mode.decide(2048, lite_mode.GPU_HARDWARE)
        self.assertEqual(decision.mode, lite_mode.MODE_LITE)
        self.assertTrue(decision.is_lite)

    def test_exact_lite_threshold_is_lite(self):
        self.assertEqual(
            lite_mode.decide(lite_mode.LITE_MAX_MB, lite_mode.GPU_HARDWARE).mode,
            lite_mode.MODE_LITE,
        )

    def test_just_above_lite_threshold_stays_lite(self):
        self.assertEqual(
            lite_mode.decide(lite_mode.LITE_MAX_MB + 1, lite_mode.GPU_HARDWARE).mode,
            lite_mode.MODE_LITE,
        )

    def test_three_gigabyte_machine_stays_lite(self):
        self.assertEqual(lite_mode.decide(3072, lite_mode.GPU_HARDWARE).mode, lite_mode.MODE_LITE)

    def test_four_gigabyte_machine_is_full(self):
        self.assertEqual(lite_mode.decide(4096, lite_mode.GPU_HARDWARE).mode, lite_mode.MODE_FULL)

    def test_exact_full_threshold_is_full(self):
        self.assertEqual(
            lite_mode.decide(lite_mode.FULL_MIN_MB, lite_mode.GPU_HARDWARE).mode,
            lite_mode.MODE_FULL,
        )

    def test_just_below_full_threshold_stays_lite(self):
        self.assertEqual(
            lite_mode.decide(lite_mode.FULL_MIN_MB - 1, lite_mode.GPU_HARDWARE).mode,
            lite_mode.MODE_LITE,
        )

    def test_software_gpu_forces_lite_on_big_machine(self):
        decision = lite_mode.decide(16384, lite_mode.GPU_SOFTWARE)
        self.assertEqual(decision.mode, lite_mode.MODE_LITE)
        self.assertIn("software rendering only", decision.reasons)

    def test_unknown_gpu_on_big_machine_is_full(self):
        self.assertEqual(lite_mode.decide(8192, lite_mode.GPU_UNKNOWN).mode, lite_mode.MODE_FULL)

    def test_zero_memory_is_an_error(self):
        with self.assertRaises(lite_mode.LiteModeError):
            lite_mode.decide(0, lite_mode.GPU_HARDWARE)

    def test_negative_memory_is_an_error(self):
        with self.assertRaises(lite_mode.LiteModeError):
            lite_mode.decide(-1, lite_mode.GPU_HARDWARE)

    def test_decision_is_serialisable(self):
        payload = lite_mode.decide(2048, lite_mode.GPU_HARDWARE).as_dict()
        self.assertEqual(payload["mode"], "lite")
        self.assertEqual(payload["total_mb"], 2048)
        json.dumps(payload)


class WriteConfigTests(unittest.TestCase):
    def test_lite_writes_expected_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = lite_mode.write_configs(lite_mode.MODE_LITE, root)
            self.assertEqual(len(written), len(lite_mode.MANAGED_FILES))
            for path in written:
                self.assertTrue(path.is_file(), path)
            kwinrc = (root / "kwinrc").read_text()
            self.assertIn("MaxFPS=30", kwinrc)
            self.assertIn("blurEnabled=false", kwinrc)
            self.assertIn("Indexing-Enabled=false", (root / "baloofilerc").read_text())

    def test_full_writes_full_values(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lite_mode.write_configs(lite_mode.MODE_FULL, root)
            self.assertIn("MaxFPS=60", (root / "kwinrc").read_text())
            self.assertIn("Indexing-Enabled=true", (root / "baloofilerc").read_text())

    def test_apply_is_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lite_mode.write_configs(lite_mode.MODE_LITE, root)
            first = {p.name: p.read_text() for p in root.iterdir() if p.is_file()}
            lite_mode.write_configs(lite_mode.MODE_LITE, root)
            second = {p.name: p.read_text() for p in root.iterdir() if p.is_file()}
            self.assertEqual(first, second)

    def test_switching_mode_rewrites(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lite_mode.write_configs(lite_mode.MODE_FULL, root)
            lite_mode.write_configs(lite_mode.MODE_LITE, root)
            self.assertEqual(lite_mode.read_state(root)["mode"], "lite")

    def test_unknown_mode_is_an_error(self):
        with TemporaryDirectory() as tmp, self.assertRaises(lite_mode.LiteModeError):
            lite_mode.write_configs("turbo", Path(tmp))

    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            written = lite_mode.write_configs(lite_mode.MODE_LITE, root, dry_run=True)
            self.assertTrue(written)
            self.assertEqual(list(root.iterdir()), [])

    def test_read_state_without_file(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(lite_mode.read_state(Path(tmp)), {"mode": None})


class CliTests(unittest.TestCase):
    def _host(self, tmp: Path, total_mb: int, driver: str | None) -> Path:
        (tmp / "proc").mkdir()
        (tmp / "proc/meminfo").write_text(meminfo(total_mb))
        drm = tmp / "sys/class/drm"
        (drm / "card0" / "device").mkdir(parents=True)
        if driver:
            target = tmp / "drivers" / driver
            target.mkdir(parents=True)
            (drm / "card0" / "device" / "driver").symlink_to(target)
        else:
            (drm / "card0" / "device" / "driver").symlink_to(tmp / "drivers/missing")
        return tmp

    def test_status_json_on_low_end_host(self):
        with TemporaryDirectory() as tmp:
            root = self._host(Path(tmp), 2048, "i915")
            code = lite_mode.main(["--status", "--json", "--root", str(root)])
            self.assertEqual(code, 0)

    def test_apply_writes_under_root(self):
        with TemporaryDirectory() as tmp:
            root = self._host(Path(tmp), 8192, "amdgpu")
            config = root / "etc/skel/.config"
            code = lite_mode.main(["--apply", "--json", "--root", str(root)])
            self.assertEqual(code, 0)
            self.assertEqual(lite_mode.read_state(config)["mode"], "full")

    def test_force_lite_overrides_measurement(self):
        with TemporaryDirectory() as tmp:
            root = self._host(Path(tmp), 16384, "amdgpu")
            config = root / "cfg"
            code = lite_mode.main(
                ["--apply", "--force-lite", "--root", str(root), "--config-dir", str(config)]
            )
            self.assertEqual(code, 0)
            self.assertEqual(lite_mode.read_state(config)["mode"], "lite")

    def test_force_flags_are_mutually_exclusive(self):
        with TemporaryDirectory() as tmp:
            root = self._host(Path(tmp), 4096, "i915")
            code = lite_mode.main(["--force-lite", "--force-full", "--root", str(root)])
            self.assertEqual(code, 2)

    def test_missing_meminfo_exits_two(self):
        with TemporaryDirectory() as tmp:
            code = lite_mode.main(["--status", "--root", tmp])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
