#!/usr/bin/env python3
"""Enforce the Zaod Fluent design system rules on the committed tokens.

This is the Phase 6 automated gate. It computes contrast for real (WCAG 2.1
relative luminance), verifies the 4 px grid, the allowed radii, the motion
window, the font/licence whitelist, theme parity, and that every generated
artefact (QML singleton, GTK CSS, wallpapers) still matches tokens.json.

Exit status 0 means the design system is internally consistent and accessible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = REPO_ROOT / "desktop" / "design"
TOKENS_PATH = DESIGN_ROOT / "tokens" / "tokens.json"

ALLOWED_RADII = {0, 4, 8, 12, 16, 24, 999}
ALLOWED_FAMILIES = {"Inter", "JetBrains Mono", "Noto Sans", "Noto Sans Mono"}
REQUIRED_FAMILY_LICENSES = {"Inter", "JetBrains Mono", "Noto Sans"}
FORBIDDEN_ASSET_STRINGS = (
    "microsoft",
    "windows 1",
    "windows-1",
    "segoe",
    "cortana",
    "ms-settings",
    "calibri",
    "tahoma",
    "acrylic material",
)
MOTION_MIN_MS = 120
MOTION_MAX_MS = 250
REQUIRED_COLOR_ROLES = (
    "background",
    "surface",
    "surfaceAlt",
    "surfaceRaised",
    "surfaceOverlay",
    "border",
    "borderStrong",
    "textPrimary",
    "textSecondary",
    "textTertiary",
    "textDisabled",
    "accent",
    "accentHover",
    "accentPressed",
    "accentSubtle",
    "onAccent",
    "danger",
    "onDanger",
    "success",
    "warning",
    "focusRing",
    "shadow",
    "scrim",
)


class Report:
    def __init__(self) -> None:
        self.checks = 0
        self.failures = []

    def check(self, condition: bool, label: str, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(f"{label}{(': ' + detail) if detail else ''}")


def hex_to_rgb(value: str) -> tuple:
    cleaned = value.lstrip("#")
    if len(cleaned) != 6 or re.fullmatch(r"[0-9a-fA-F]{6}", cleaned) is None:
        raise ValueError(f"not a hex colour: {value}")
    return tuple(int(cleaned[i : i + 2], 16) / 255 for i in (0, 2, 4))


def relative_luminance(value: str) -> float:
    """WCAG 2.1 relative luminance of a #rrggbb colour."""

    def channel(raw: float) -> float:
        return raw / 12.92 if raw <= 0.03928 else ((raw + 0.055) / 1.055) ** 2.4

    red, green, blue = hex_to_rgb(value)
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(first: str, second: str) -> float:
    """WCAG 2.1 contrast ratio between two #rrggbb colours."""
    lum_a = relative_luminance(first)
    lum_b = relative_luminance(second)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def check_structure(tokens: dict, report: Report) -> None:
    grid = tokens["meta"]["grid"]
    report.check(grid == 4, "spacing grid is 4 px", str(grid))
    for key, value in tokens["spacing"].items():
        report.check(
            value % grid == 0,
            f"spacing {key} sits on the {grid} px grid",
            f"{value} px",
        )
    for name, value in tokens["radii"].items():
        report.check(value in ALLOWED_RADII, f"radius {name} is an allowed value", str(value))
        if value != 999:
            report.check(value % grid == 0, f"radius {name} is on the grid", f"{value} px")

    for name in ("fast", "base", "slow"):
        value = tokens["motion"][name]
        report.check(
            MOTION_MIN_MS <= value <= MOTION_MAX_MS,
            f"motion {name} is inside the {MOTION_MIN_MS}-{MOTION_MAX_MS} ms window",
            f"{value} ms",
        )
    easing = tokens["motion"]["easing"]
    report.check(easing.startswith("cubic-bezier("), "motion easing is a cubic-bezier", easing)
    numbers = re.findall(r"-?\d*\.?\d+", easing)
    report.check(len(numbers) == 4, "motion easing declares four control points", easing)

    families = tokens["typography"]["families"]
    for role, family in families.items():
        report.check(family in ALLOWED_FAMILIES, f"font {role} is whitelisted", family)
    licenses = tokens["typography"]["licenses"]
    for family in REQUIRED_FAMILY_LICENSES:
        report.check(family in licenses, f"font licence declared for {family}")
        report.check(
            licenses.get(family, "").startswith("OFL"),
            f"font {family} uses an open licence",
            licenses.get(family, "missing"),
        )

    previous_size = 0
    previous_weight = 0
    for step in tokens["typography"]["scale"]:
        # A step either grows or, at the same size, gains weight (body-strong).
        report.check(
            step["size"] > previous_size
            or (step["size"] == previous_size and step["weight"] > previous_weight),
            f"type scale {step['name']} is distinguishable from the previous step",
            f"{step['size']}px/{step['weight']} after {previous_size}px/{previous_weight}",
        )
        previous_size = step["size"]
        previous_weight = step["weight"]
        report.check(
            step["lineHeight"] >= step["size"], f"type scale {step['name']} has room to breathe"
        )

    light = tokens["themes"]["light"]
    dark = tokens["themes"]["dark"]
    report.check(set(light) == set(dark), "light and dark themes define the same roles")
    for role in REQUIRED_COLOR_ROLES:
        report.check(role in light, f"light theme defines {role}")
        report.check(role in dark, f"dark theme defines {role}")
    for theme_name, theme in (("light", light), ("dark", dark)):
        for role, value in theme.items():
            try:
                hex_to_rgb(value)
            except ValueError as exc:
                report.check(False, f"{theme_name}.{role} is a hex colour", str(exc))

    report.check(len(tokens["wallpapers"]) == 3, "three wallpapers are declared")
    for name, design in ((d["id"], d) for d in tokens["wallpapers"]):
        report.check("flat" in design, f"wallpaper {name} declares its flat lite variant")

    # Shell geometry is a token too: it sat hardcoded in the QML before 0.6.1.
    layout = tokens["layout"]
    for key, value in layout.items():
        report.check(
            isinstance(value, int) and value % grid == 0,
            f"layout {key} sits on the {grid} px grid",
            str(value),
        )
    report.check(layout["taskbarHeightLite"] <= layout["taskbarHeight"], "lite taskbar is not taller")

    # Lite profile: every expensive effect must be switchable off.
    lite = tokens["lite"]
    for flag in ("allowBlur", "allowGlass", "allowAnimation", "allowPreviews"):
        report.check(lite.get(flag) is False, f"lite profile disables {flag}")
    report.check(lite["elevationCap"] <= 1, "lite profile caps elevation at 1")
    report.check(
        tokens["elevationUsage"]["maxComponentLevel"] <= 3,
        "components may not use elevation 4",
    )

    # Text scale: 100-150% is the accessibility contract, so both ends must exist.
    scale_range = tokens["typography"]["scaleRange"]
    report.check(scale_range["min"] <= 100, "text scale starts at 100%", str(scale_range["min"]))
    report.check(scale_range["max"] >= 150, "text scale reaches 150%", str(scale_range["max"]))
    report.check(
        scale_range["min"] <= scale_range["reflowAt"] <= scale_range["max"],
        "text reflow point is inside the declared range",
    )

    # Hit targets: the brief asks for 28 px minimum, the token set promises more.
    report.check(tokens["focus"]["minTargetSize"] >= 28, "keyboard target is at least 28 px")
    report.check(tokens["focus"]["minPointerTarget"] >= 28, "pointer target is at least 28 px")


def check_contrast(tokens: dict, report: Report, verbose: bool) -> list:
    rows = []
    for theme_name in ("light", "dark"):
        theme = tokens["themes"][theme_name]
        for pair in tokens["accessibility"]["pairs"]:
            source, target, minimum = pair["from"], pair["to"], pair["min"]
            try:
                ratio = contrast_ratio(theme[source], theme[target])
            except KeyError as exc:
                report.check(False, f"{theme_name}: contrast pair references a missing token", str(exc))
                continue
            rows.append((theme_name, source, target, ratio, minimum, pair["kind"]))
            report.check(
                ratio >= minimum,
                f"{theme_name}: {source} on {target} ratio {ratio:.2f} meets {minimum}",
                f"{ratio:.2f} < {minimum}",
            )
    if verbose:
        print(f"{'theme':6} {'text':18} {'on':18} {'ratio':>6} {'min':>5} kind")
        for theme_name, source, target, ratio, minimum, kind in rows:
            flag = "ok" if ratio >= minimum else "FAIL"
            print(f"{theme_name:6} {source:18} {target:18} {ratio:6.2f} {minimum:5.1f} {kind:4} {flag}")
    return rows


def check_generated(tokens: dict, report: Report) -> None:
    sys.path.insert(0, str(DESIGN_ROOT / "tools"))
    import make_icons
    import make_wallpapers
    import tokens_to_css
    import tokens_to_python
    import tokens_to_qml

    report.check(not tokens_to_qml.is_stale(tokens), "ZaodTheme.qml is up to date with tokens.json")
    for path in tokens_to_css.stale_paths(tokens):
        report.check(False, "generated GTK css is up to date", str(path.relative_to(REPO_ROOT)))
    for path in make_wallpapers.stale_paths(tokens):
        report.check(False, "generated wallpaper is up to date", str(path.relative_to(REPO_ROOT)))
    report.check(
        not tokens_to_python.is_stale(tokens),
        "apps/lib/zaod_tokens.py is up to date with tokens.json",
    )
    for path in make_icons.stale_paths(tokens):
        report.check(False, "generated icon is up to date", str(path.relative_to(REPO_ROOT)))

    qml_text = tokens_to_qml.OUTPUT_PATH.read_text(encoding="utf-8")
    for role in REQUIRED_COLOR_ROLES:
        report.check(f"property color {role}" in qml_text, f"ZaodTheme.qml exposes {role}")
    report.check("pragma Singleton" in qml_text, "ZaodTheme.qml is a singleton")
    report.check('mode: "dark"' in qml_text, "ZaodTheme.qml defaults to dark")


# LICENSE.md is the file that states the provenance rule, so it necessarily
# names the vendors that are excluded. It is the only exemption; the scan still
# asserts that the statement itself is present.
PROVENANCE_FILE = "LICENSE.md"
# The scanner itself must name the excluded vendors to be able to reject them,
# and this validator holds the same list.
SELF_EXEMPT = ("tools/scan_assets.py",)


def check_assets(report: Report) -> None:
    for path in sorted(DESIGN_ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.name == PROVENANCE_FILE:
            continue
        relative_to_design = str(path.relative_to(DESIGN_ROOT))
        if any(relative_to_design.endswith(name) for name in SELF_EXEMPT):
            continue
        if path.suffix not in {"", ".md", ".json", ".qml", ".css", ".svg", ".py", ".txt", ".js"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        relative = path.relative_to(REPO_ROOT)
        for vendor in FORBIDDEN_ASSET_STRINGS:
            report.check(vendor not in text, f"{relative} is free of '{vendor}'")
    licence_file = DESIGN_ROOT / "LICENSE.md"
    report.check(licence_file.is_file(), "design assets declare a licence file")
    if licence_file.is_file():
        licence_text = licence_file.read_text(encoding="utf-8").lower()
        for family in REQUIRED_FAMILY_LICENSES:
            report.check(
                family.lower() in licence_text, f"LICENSE.md credits the {family} font licence"
            )
        report.check("cc-by-4.0" in licence_text, "LICENSE.md declares the token licence")
        report.check(
            "no asset in this directory is copied" in licence_text,
            "LICENSE.md carries the provenance statement",
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true", help="print the full contrast table")
    parser.add_argument("--json", action="store_true", help="print a machine readable summary")
    args = parser.parse_args(argv)

    tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    report = Report()
    check_structure(tokens, report)
    rows = check_contrast(tokens, report, verbose=args.verbose and not args.json)
    check_generated(tokens, report)
    check_assets(report)

    minimum_ratio = min((row[3] for row in rows), default=0.0)
    if args.json:
        print(
            json.dumps(
                {
                    "checks": report.checks,
                    "failures": report.failures,
                    "contrast_pairs": len(rows),
                    "lowest_contrast": round(minimum_ratio, 2),
                    "status": "pass" if not report.failures else "fail",
                },
                indent=2,
            )
        )
    else:
        print(
            f"design token checks: {report.checks} run, {len(report.failures)} failed, "
            f"{len(rows)} contrast pairs, lowest ratio {minimum_ratio:.2f}:1"
        )
        for failure in report.failures:
            print(f"  FAIL {failure}")
        if not report.failures:
            print("design token checks: PASS")
    return 0 if not report.failures else 1


if __name__ == "__main__":
    sys.exit(main())
