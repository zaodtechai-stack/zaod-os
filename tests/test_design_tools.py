#!/usr/bin/env python3
"""Unit tests for the Phase 6 design tooling.

Covers the colour maths behind the accessibility gate, generator determinism,
stale detection, and that the generated artefacts are structurally valid.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = REPO_ROOT / "desktop" / "design"
sys.path.insert(0, str(DESIGN_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import check_design_tokens as tokens_check
import make_wallpapers
import tokens_to_css
import tokens_to_qml


class ContrastMathTests(unittest.TestCase):
    def test_black_on_white_is_twenty_one(self):
        self.assertAlmostEqual(tokens_check.contrast_ratio("#000000", "#FFFFFF"), 21.0, places=2)

    def test_identical_colours_are_one(self):
        self.assertAlmostEqual(tokens_check.contrast_ratio("#0067C0", "#0067C0"), 1.0, places=4)

    def test_order_does_not_matter(self):
        forward = tokens_check.contrast_ratio("#101418", "#F6F7F9")
        backward = tokens_check.contrast_ratio("#F6F7F9", "#101418")
        self.assertAlmostEqual(forward, backward, places=6)

    def test_known_reference_value(self):
        # WCAG reference: #777777 on white is 4.48:1
        self.assertAlmostEqual(tokens_check.contrast_ratio("#777777", "#FFFFFF"), 4.48, places=2)

    def test_luminance_of_white_is_one(self):
        self.assertAlmostEqual(tokens_check.relative_luminance("#FFFFFF"), 1.0, places=6)

    def test_luminance_of_black_is_zero(self):
        self.assertAlmostEqual(tokens_check.relative_luminance("#000000"), 0.0, places=6)

    def test_invalid_colour_raises(self):
        with self.assertRaises(ValueError):
            tokens_check.contrast_ratio("#12345", "#FFFFFF")

    def test_short_hex_is_rejected(self):
        with self.assertRaises(ValueError):
            tokens_check.hex_to_rgb("#fff")

    def test_kebab_case_conversion(self):
        self.assertEqual(tokens_to_css.camel_to_kebab("onAccent"), "on-accent")
        self.assertEqual(tokens_to_css.camel_to_kebab("textPrimary"), "text-primary")
        self.assertEqual(tokens_to_css.camel_to_kebab("background"), "background")


class QmlGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tokens = tokens_to_qml.load_tokens()

    def test_render_is_deterministic(self):
        self.assertEqual(
            tokens_to_qml.render_qml(self.tokens), tokens_to_qml.render_qml(self.tokens)
        )

    def test_render_exposes_every_colour_role(self):
        rendered = tokens_to_qml.render_qml(self.tokens)
        for role in tokens_to_qml.COLOR_ROLES:
            self.assertIn(f"readonly property color {role}:", rendered)

    def test_render_is_a_singleton(self):
        self.assertIn("pragma Singleton", tokens_to_qml.render_qml(self.tokens))

    def test_render_contains_grid_and_motion(self):
        rendered = tokens_to_qml.render_qml(self.tokens)
        self.assertIn("readonly property int grid: 4", rendered)
        self.assertIn("readonly property int motionFast: 120", rendered)

    def test_write_then_not_stale(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "ZaodTheme.qml"
            tokens_to_qml.write_output(self.tokens, output)
            self.assertFalse(tokens_to_qml.is_stale(self.tokens, output))

    def test_modified_output_is_stale(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "ZaodTheme.qml"
            tokens_to_qml.write_output(self.tokens, output)
            output.write_text(output.read_text() + "\n// drift\n")
            self.assertTrue(tokens_to_qml.is_stale(self.tokens, output))

    def test_missing_output_is_stale(self):
        with TemporaryDirectory() as tmp:
            self.assertTrue(tokens_to_qml.is_stale(self.tokens, Path(tmp) / "missing.qml"))

    def test_committed_singleton_is_current(self):
        self.assertFalse(tokens_to_qml.is_stale(self.tokens, tokens_to_qml.OUTPUT_PATH))


class CssGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tokens = tokens_to_qml.load_tokens()

    def test_every_theme_produces_css(self):
        for theme_name in ("light", "dark"):
            css = tokens_to_css.render_css(self.tokens, theme_name)
            self.assertIn("@define-color zaod_background", css)
            self.assertIn(self.tokens["themes"][theme_name]["background"], css)

    def test_light_and_dark_differ(self):
        light = tokens_to_css.render_css(self.tokens, "light")
        dark = tokens_to_css.render_css(self.tokens, "dark")
        self.assertNotEqual(light, dark)

    def test_all_used_colour_names_are_defined(self):
        for theme_name in ("light", "dark"):
            css = tokens_to_css.render_css(self.tokens, theme_name)
            defined = set()
            used = set()
            for line in css.splitlines():
                if line.startswith("@define-color "):
                    defined.add(line.split()[1])
                for marker in line.split("@")[1:]:
                    name = marker.split()[0].split(";")[0].rstrip(",")
                    if name.startswith("zaod_"):
                        used.add(name)
            self.assertEqual(used - defined, set(), f"undefined colour names in {theme_name}")

    def test_outputs_cover_both_toolkits(self):
        paths = {str(path.relative_to(DESIGN_ROOT)) for path in tokens_to_css.outputs(self.tokens)}
        for toolkit in ("gtk-3.0", "gtk-4.0"):
            for name in ("zaod-light.css", "zaod-dark.css", "gtk.css", "gtk-dark.css"):
                self.assertIn(f"gtk/{toolkit}/{name}", paths)

    def test_entry_point_imports_theme(self):
        self.assertIn("@import url(\"zaod-dark.css\")", tokens_to_css.render_entry_point("dark"))

    def test_no_stale_css_is_committed(self):
        self.assertEqual(tokens_to_css.stale_paths(self.tokens), [])


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.tokens = tokens_to_qml.load_tokens()

    def test_renders_three_designs_in_two_themes_and_two_tiers(self):
        outputs = make_wallpapers.outputs(self.tokens)
        # 3 designs x 2 themes x 2 tiers (full, flat) = 12
        self.assertEqual(len(outputs), 12)

    def test_flat_tier_is_the_lite_wallpaper(self):
        """The flat tier exists so lite mode can skip gradients entirely."""
        flat = make_wallpapers.render_aurora_flat(self.tokens, "light")
        full = make_wallpapers.render_aurora(self.tokens, "light")
        self.assertNotIn("radialGradient", flat)
        self.assertIn("radialGradient", full)
        self.assertLess(len(flat), len(full))
        self.assertEqual(self.tokens["lite"]["wallpaperTier"], "flat")

    def test_render_is_deterministic(self):
        first = make_wallpapers.render_aurora(self.tokens, "dark")
        second = make_wallpapers.render_aurora(self.tokens, "dark")
        self.assertEqual(first, second)

    def test_light_and_dark_differ(self):
        light = make_wallpapers.render_horizon(self.tokens, "light")
        dark = make_wallpapers.render_horizon(self.tokens, "dark")
        self.assertNotEqual(light, dark)

    def test_svg_is_well_formed_and_sized(self):
        from xml.etree import ElementTree

        for design in self.tokens["wallpapers"]:
            renderer = make_wallpapers.RENDERERS[design["id"]]
            for theme_name in ("light", "dark"):
                svg = renderer(self.tokens, theme_name)
                root = ElementTree.fromstring(svg)
                self.assertEqual(root.get("viewBox"), "0 0 2560 1440")
                self.assertIn("Zaod OS", svg)

    def test_wallpaper_budget(self):
        for design in self.tokens["wallpapers"]:
            renderer = make_wallpapers.RENDERERS[design["id"]]
            for theme_name in ("light", "dark"):
                size = len(renderer(self.tokens, theme_name).encode())
                self.assertLess(size, 400 * 1024, f"{design['id']}-{theme_name} is too large")

    def test_no_stale_wallpaper_is_committed(self):
        self.assertEqual(make_wallpapers.stale_paths(self.tokens), [])


class CommittedTokenTests(unittest.TestCase):
    def setUp(self):
        self.tokens = json.loads((DESIGN_ROOT / "tokens" / "tokens.json").read_text())

    def test_every_contrast_pair_passes(self):
        report = tokens_check.Report()
        rows = tokens_check.check_contrast(self.tokens, report, verbose=False)
        self.assertEqual(report.failures, [])
        self.assertGreaterEqual(len(rows), 40)
        self.assertGreaterEqual(min(row[3] for row in rows), 3.0)

    def test_structure_is_valid(self):
        report = tokens_check.Report()
        tokens_check.check_structure(self.tokens, report)
        self.assertEqual(report.failures, [])

    def test_validator_fails_on_a_broken_contrast(self):
        broken = json.loads(json.dumps(self.tokens))
        broken["themes"]["light"]["textPrimary"] = "#F0F0F0"
        report = tokens_check.Report()
        tokens_check.check_contrast(broken, report, verbose=False)
        self.assertTrue(report.failures, "a pale text colour must fail the contrast gate")

    def test_validator_fails_on_off_grid_spacing(self):
        broken = json.loads(json.dumps(self.tokens))
        broken["spacing"]["3"] = 13
        report = tokens_check.Report()
        tokens_check.check_structure(broken, report)
        self.assertTrue(report.failures, "13 px is not on the 4 px grid")

    def test_validator_fails_on_too_slow_motion(self):
        broken = json.loads(json.dumps(self.tokens))
        broken["motion"]["slow"] = 400
        report = tokens_check.Report()
        tokens_check.check_structure(broken, report)
        self.assertTrue(report.failures, "400 ms is outside the 120-250 ms window")

    def test_validator_fails_on_vendor_font(self):
        broken = json.loads(json.dumps(self.tokens))
        broken["typography"]["families"]["text"] = "Segoe UI"
        report = tokens_check.Report()
        tokens_check.check_structure(broken, report)
        self.assertTrue(report.failures, "a non-whitelisted font must fail")


class ComponentInventoryTests(unittest.TestCase):
    def test_every_registered_component_exists(self):
        qmldir = (DESIGN_ROOT / "qml" / "qmldir").read_text()
        for line in qmldir.splitlines():
            parts = line.split()
            if not parts or parts[0] == "module":
                continue
            filename = parts[-1]
            self.assertTrue((DESIGN_ROOT / "qml" / filename).is_file(), filename)

    def test_shell_surfaces_exist(self):
        for name in ("Taskbar", "StartMenu", "QuickSettings", "NotificationCenter"):
            self.assertTrue((DESIGN_ROOT / "shell" / f"{name}.qml").is_file(), name)

    def test_components_use_tokens_only(self):
        import re

        hex_pattern = re.compile(r'"#[0-9A-Fa-f]{6}"')
        for path in sorted((DESIGN_ROOT / "qml").glob("*.qml")):
            if path.name == "ZaodTheme.qml":
                continue  # the generated palette file carries the raw values
            text = path.read_text()
            self.assertEqual(
                hex_pattern.findall(text), [], f"{path.name} hardcodes a colour instead of a token"
            )


if __name__ == "__main__":
    unittest.main()
