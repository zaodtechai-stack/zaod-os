#!/usr/bin/env python3
"""Emit the QML theme singleton from tokens.json.

`tokens.json` is the only source of truth: ZaodTheme.qml is generated, never
edited by hand. Run with `--check` in CI to fail when the committed file is
stale.

Two rules this generator has to get right, because the first version broke both
and shipped a singleton that could not compile:

1. The palettes are JavaScript object literals (`({ ... })`), so their contents
   are `name: "#rrggbb"` pairs, never `readonly property` declarations.
2. Token names are hyphenated (`body-sm`), QML property names are camel case
   with the inner word capitalised (`typeBodySm`). `str.capitalize()` lowercases
   the rest of the word and produced `typeBodysm`, which no component referenced.
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

SPACING_NAMES = {
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

# Token name -> QML property name. Explicit on purpose: implicit casing rules
# are how `body-strong` became `typeBodystrong` and broke three components.
TYPE_NAMES = {
    "caption": "typeCaption",
    "body-sm": "typeBodySm",
    "body": "typeBody",
    "body-strong": "typeBodyStrong",
    "subtitle": "typeSubtitle",
    "title": "typeTitle",
    "title-lg": "typeTitleLg",
    "display": "typeDisplay",
}

SESSION_GATED = {"allowBlur", "allowGlass", "allowAnimation", "allowPreviews"}

OPACITY_NAMES = {
    "glass": "opacityGlass",
    "scrim": "opacityScrim",
    "hover": "opacityHover",
    "pressed": "opacityPressed",
    "disabled": "opacityDisabled",
    "hint": "opacityHint",
}


def load_tokens(path: Path = TOKENS_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _qml_color_map(theme: dict) -> str:
    """Render one palette as the body of a JavaScript object literal."""
    entries = [f'        {role}: "{theme[role]}"' for role in COLOR_ROLES]
    return ",\n".join(entries)


def render_qml(tokens: dict) -> str:
    spacing = tokens["spacing"]
    radii = tokens["radii"]
    motion = tokens["motion"]
    elevation = tokens["elevation"]
    typography = tokens["typography"]
    scale = {item["name"]: item for item in typography["scale"]}
    light = tokens["themes"]["light"]
    dark = tokens["themes"]["dark"]
    opacity = tokens["opacity"]
    lite = tokens["lite"]
    focus = tokens["focus"]

    spacing_lines = "\n".join(
        f"    readonly property int {SPACING_NAMES[str(key)]}: {value}"
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
        f"    readonly property var {TYPE_NAMES[name]}: "
        f"({{ size: {spec['size']}, lineHeight: {spec['lineHeight']}, "
        f"weight: {spec['weight']}, tracking: {spec['tracking']} }})"
        for name, spec in scale.items()
    )
    layout_lines = "\n".join(
        f"    readonly property int {key}: {value}" for key, value in tokens["layout"].items()
    )
    opacity_lines = "\n".join(
        f"    readonly property real {OPACITY_NAMES[name]}: {value}"
        for name, value in opacity.items()
    )
    # The scrim is only ever painted as a translucent overlay, so it is emitted
    # composited with its declared opacity. Emitting the raw role made every
    # surface paint an opaque panel over the desktop instead of dimming it.
    palette_role_lines = "\n".join(
        f"    readonly property color {role}: palette.{role}"
        for role in COLOR_ROLES
        if role != "scrim"
    )
    # allowBlur/allowGlass/allowAnimation/allowPreviews are emitted above with the
    # session switch folded in, so skip them here to avoid duplicate properties.
    lite_lines = "\n".join(
        f"    readonly property bool {key}: {str(value).lower()}"
        for key, value in lite.items()
        if isinstance(value, bool) and key not in SESSION_GATED
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

    // Lite profile: 1366x768 / 2 GB / 2 cores. Set by the session, never by an app.
    property bool lite: false
    readonly property int elevationCap: lite ? {lite['elevationCap']} : {tokens['elevationUsage']['maxComponentLevel']}
    readonly property bool allowBlur: !lite && {(str(lite['allowBlur']).lower())}
    readonly property bool allowGlass: !lite && {(str(lite['allowGlass']).lower())}
    readonly property bool allowAnimation: !lite && {(str(lite['allowAnimation']).lower())}
    readonly property bool allowPreviews: !lite && {(str(lite['allowPreviews']).lower())}
{lite_lines}

    // Text scale: 1.0 to 1.5. Every pixelSize goes through scaled().
    property real fontScale: 1.0
    readonly property real minFontScale: {typography['scaleRange']['min'] / 100}
    readonly property real maxFontScale: {typography['scaleRange']['max'] / 100}

    function scaled(pixels) {{
        return Math.round(pixels * fontScale)
    }}

    function lineHeight(step) {{
        return Math.round(step.lineHeight * fontScale)
    }}

    // Motion: 0 ms whenever the lite profile or the session disables animation.
    function duration(milliseconds) {{
        return allowAnimation ? milliseconds : 0
    }}

    readonly property int grid: {tokens['meta']['grid']}

{spacing_lines}

{radius_lines}

    readonly property int hairline: {tokens['borders']['hairline']}
    readonly property int borderThick: {tokens['borders']['thick']}
    readonly property int focusRingWidth: {focus['ringWidth']}
    readonly property int focusRingOffset: {focus['ringOffset']}
    readonly property int minTargetSize: {focus['minTargetSize']}
    readonly property int minPointerTarget: {focus['minPointerTarget']}

{layout_lines}

{opacity_lines}

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

{palette_role_lines}

    readonly property color scrimBase: palette.scrim
    readonly property color scrim: Qt.rgba(scrimBase.r, scrimBase.g, scrimBase.b, opacityScrim)

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
