"""Control Center backend tests using a recorded command runner."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

APPS = pathlib.Path(__file__).resolve().parents[1]
PAYLOAD = APPS / "control-center" / "payload"
sys.path.insert(0, str(PAYLOAD))


def load_backend():
    spec = importlib.util.spec_from_file_location("cc_backend", PAYLOAD / "backend.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cc_backend"] = module
    spec.loader.exec_module(module)
    return module


backend = load_backend()


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.calls = []

    def run(self, argv, timeout=20):
        self.calls.append(list(argv))
        return self.outputs.get(argv[0], "")


class ControlCenterTests(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner(
            {
                "nmcli": "enabled",
                "kreadconfig6": "ZaodLight",
                "wpctl": "Volume: 0.65",
                "uname": "6.18.63-zaod",
            }
        )
        self.center = backend.ControlCenter(runner=self.runner)

    def test_pages_and_controls_are_unique(self):
        pages = self.center.pages
        self.assertEqual(len(pages), 7)
        keys = set()
        for page in pages:
            for control in page.controls:
                pair = (page.key, control.key)
                self.assertNotIn(pair, keys)
                keys.add(pair)
        self.assertGreaterEqual(len(keys), 14)

    def test_wifi_state_is_translated(self):
        self.assertEqual(self.center.get("network", "wifi"), "on")
        self.runner.outputs["nmcli"] = "disabled"
        self.assertEqual(self.center.get("network", "wifi"), "off")

    def test_wifi_toggle_writes_nmcli(self):
        self.center.set("network", "wifi", "off")
        self.assertEqual(self.runner.calls[-1], ["nmcli", "radio", "wifi", "off"])

    def test_colour_scheme_uses_plasma_helper(self):
        self.assertEqual(self.center.get("appearance", "color_scheme"), "ZaodLight")
        self.center.set("appearance", "color_scheme", "ZaodDark")
        self.assertEqual(self.runner.calls[-1], ["plasma-apply-colorscheme", "ZaodDark"])

    def test_accent_writes_zaodrc(self):
        self.center.set("appearance", "accent", "teal")
        self.assertEqual(
            self.runner.calls[-1],
            ["kwriteconfig6", "--file", "zaodrc", "--group", "Appearance", "--key", "Accent", "teal"],
        )

    def test_night_light_applies_and_reconfigures(self):
        self.center.set("display", "night_light", "true")
        self.assertEqual(
            self.runner.calls[-2],
            ["kwriteconfig6", "--file", "kwinrc", "--group", "NightColor", "--key", "Active", "true"],
        )
        self.assertEqual(self.runner.calls[-1], ["qdbus", "org.kde.KWin", "/KWin", "reconfigure"])

    def test_volume_is_parsed_and_written_in_fractions(self):
        self.assertEqual(self.center.get("sound", "volume"), "65")
        self.center.set("sound", "volume", "40")
        self.assertEqual(self.runner.calls[-1], ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "0.40"])

    def test_volume_reference_fraction_is_accepted(self):
        self.runner.outputs["wpctl"] = "Volume: 1.00"
        self.assertEqual(self.center.get("sound", "volume"), "100")

    def test_mute_state_and_write(self):
        self.runner.outputs["wpctl"] = "Volume: 0.65 [MUTED]"
        self.assertEqual(self.center.get("sound", "mute"), "on")
        self.center.set("sound", "mute", "off")
        self.assertEqual(self.runner.calls[-1], ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])

    def test_lite_mode_writes_zaodrc(self):
        self.center.set("power", "lite_mode", "true")
        self.assertEqual(
            self.runner.calls[-1],
            ["kwriteconfig6", "--file", "zaodrc", "--group", "Performance", "--key", "LiteMode", "true"],
        )

    def test_update_action_runs_privileged_helper(self):
        self.center.set("updates", "apply", "")
        self.assertEqual(self.runner.calls[-1], ["pkexec", "zaod-priv-helper", "update"])

    def test_info_controls_are_read_only(self):
        with self.assertRaises(backend.SettingError):
            self.center.set("about", "kernel", "6.0.0")

    def test_action_has_no_value(self):
        with self.assertRaises(backend.SettingError):
            self.center.get("updates", "apply")

    def test_unknown_page_and_control(self):
        with self.assertRaises(backend.SettingError):
            self.center.page("printer")
        with self.assertRaises(backend.SettingError):
            self.center.get("network", "bluetooth")

    def test_repo_sync_reads_latest_stamp(self):
        root = pathlib.Path(tempfile.mkdtemp())
        repos = root / "repos.json"
        repos.write_text(
            json.dumps({"repos": [{"name": "core", "last_sync": "2026-11-01T10:00:00Z"},
                                  {"name": "extra", "last_sync": "2026-11-10T10:00:00Z"}]}),
            encoding="utf-8",
        )
        paths = type("Paths", (), {"repos_file": repos, "os_release": root / "os-release"})()
        center = backend.ControlCenter(runner=self.runner, paths=paths)
        self.assertEqual(center.get("updates", "last_sync"), "2026-11-10T10:00:00Z")

    def test_os_release_is_parsed(self):
        root = pathlib.Path(tempfile.mkdtemp())
        release = root / "os-release"
        release.write_text('PRETTY_NAME="Zaod OS"\nVERSION_ID="2026.11"\n', encoding="utf-8")
        paths = type("Paths", (), {"repos_file": root / "repos.json", "os_release": release})()
        center = backend.ControlCenter(runner=self.runner, paths=paths)
        self.assertEqual(center.get("about", "os"), "Zaod OS 2026.11")

    def test_missing_tool_error_is_precise(self):
        real = backend.Runner()
        with self.assertRaises(backend.SettingError) as caught:
            real.run(["definitely-not-a-tool", "--version"])
        self.assertIn("is not installed", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
