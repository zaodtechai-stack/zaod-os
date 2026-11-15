#!/usr/bin/env python3
"""Emit the QML theme singleton from tokens.json.

`tokens.json` is the only source of truth: ZaodTheme.qml is generated, never
edited by hand. Run with `--check` in CI to fail when the committed file is
stale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DESIGN_ROOT = Path(__file__).resolve().parents[1]
TOKENS_PATH = DESIGN_ROOT / "tokens" / "tokens.json"
OUTPUT_PATH = DESIGN_ROOT / "qml" / "ZaodTheme.qml"

COLOR_ROLES = (
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


def load_tokens(path: Path = TOKENS_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _qml_color_map(theme: dict) -> str:
    lines = []
    for role in COLOR_ROLES:
        lines.append(f'    readonly property color {role}: "{theme[role]}"')
    return "\n".join(lines)


def render_qml(tokens: dict) -> str:
    spacing = tokens["spacing"]
    radii = tokens["radii"]
    motion = tokens["motion"]
    elevation = tokens["elevation"]
    typography = tokens["typography"]
    scale = {item["name"]: item for item in typography["scale"]}
    light = tokens["themes"]["light"]
    dark = tokens["themes"]["dark"]

    spacing_camel = {
        "0": "space0",
        "1": "space1",
        "2": "space2",
        "3": "space3",
        "4": "space4",
        "5": "space5",
        "6": "space6",
        "7": "space7",
        "8": "space8",
        "10": "space10",
        "12": "space12",
        "16": "space16",
        "20": "space20",
        "24": "space24",
    }
    spacing_lines = "\n".join(
        f"    readonly property int {spacing_camel[str(key)]}: {value}"
        for key, value in spacing.items()
    )
    radius_lines = "\n".join(
        f"    readonly property int radius{key.capitalize()}: {value}" for key, value in radii.items()
    )
    elevation_lines = "\n".join(
        f"    readonly property var elevation{key}: ({{ blur: {spec['blur']}, y: {spec['y']}, "
        f"opacity: {spec['opacity']} }})"
        for key, spec in elevation.items()
    )
    type_lines = "\n".join(
        f"    readonly property var type{name.replace('-', '').capitalize()}: "
        f"({{ size: {spec['size']}, lineHeight: {spec['lineHeight']}, "
        f"weight: {spec['weight']}, tracking: {spec['tracking']} }})"
        for name, spec in scale.items()
    )

    return f"""// GENERATED FILE - do not edit.
// Source: desktop/design/tokens/tokens.json
// Generator: desktop/design/tools/tokens_to_qml.py
pragma Singleton
import QtQuick 2.15

QtObject {{
    id: theme

    // Mode: use ZaodTheme.mode = "light" | "dark" to switch at runtime.
    property string mode: "dark"
    readonly property bool isDark: mode === "dark"

    readonly property int grid: {tokens['meta']['grid']}

{spacing_lines}

{radius_lines}

    readonly property int hairline: {tokens['borders']['hairline']}
    readonly property int borderThick: {tokens['borders']['thick']}
    readonly property int focusRingWidth: {tokens['focus']['ringWidth']}
    readonly property int focusRingOffset: {tokens['focus']['ringOffset']}
    readonly property int minTargetSize: {tokens['focus']['minTargetSize']}

    readonly property int motionFast: {motion['fast']}
    readonly property int motionBase: {motion['base']}
    readonly property int motionSlow: {motion['slow']}
    readonly property string motionEasing: "{motion['easing']}"

    readonly property string fontFamily: "{typography['families']['text']}"
    readonly property string fontFamilyDisplay: "{typography['families']['display']}"
    readonly property string fontFamilyMono: "{typography['families']['mono']}"

{type_lines}

{elevation_lines}

    // Palette: light and dark are both generated so a theme switch is instant.
    readonly property var lightPalette: ({{
{_qml_color_map(light)}
    }})

    readonly property var darkPalette: ({{
{_qml_color_map(dark)}
    }})

    readonly property var palette: isDark ? darkPalette : lightPalette

{chr(10).join(f'    readonly property color {role}: palette.{role}' for role in COLOR_ROLES)}

    function withAlpha(color, alpha) {{
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }}

    function toggleMode() {{
        mode = isDark ? "light" : "dark"
    }}
}}
"""


def write_output(tokens: dict, path: Path = OUTPUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_qml(tokens), encoding="utf-8")
    return path


def is_stale(tokens: dict, path: Path = OUTPUT_PATH) -> bool:
    if not path.is_file():
        return True
    return path.read_text(encoding="utf-8") != render_qml(tokens)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    parser.add_argument("--tokens", default=str(TOKENS_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    args = parser.parse_args(argv)

    tokens = load_tokens(Path(args.tokens))
    output = Path(args.output)
    if args.check:
        if is_stale(tokens, output):
            print(f"tokens_to_qml: {output} is stale, run the generator", file=sys.stderr)
            return 1
        print(f"tokens_to_qml: {output} is up to date")
        return 0
    write_output(tokens, output)
    print(f"tokens_to_qml: wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
