#!/usr/bin/env python3
"""Emit GTK 3 and GTK 4 colour definitions from tokens.json.

GTK has no runtime theme switching through CSS variables, so two files are
generated per toolkit (`zaod-light.css`, `zaod-dark.css`) plus a `gtk.css`
entry point that imports the light variant by default. The dark variant is
selected by the session through `gtk-theme-name=zaod-dark`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DESIGN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_ROOT / "tools"))

from tokens_to_qml import COLOR_ROLES, load_tokens

GTK_ROOT = DESIGN_ROOT / "gtk"
TARGETS = ("gtk-3.0", "gtk-4.0")


def camel_to_kebab(name: str) -> str:
    """textPrimary -> text-primary, onAccent -> on-accent."""
    out = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            out.append("-")
        out.append(char.lower())
    return "".join(out)


def _hex_to_css(role: str, value: str) -> str:
    return f"@define-color zaod_{camel_to_kebab(role)} {value};"


def render_css(tokens: dict, theme_name: str) -> str:
    theme = tokens["themes"][theme_name]
    spacing = tokens["spacing"]
    radii = tokens["radii"]
    type_scale = tokens["typography"]["scale"]

    lines = [
        "/* GENERATED FILE - do not edit.",
        " * Source: desktop/design/tokens/tokens.json",
        " * Generator: desktop/design/tools/tokens_to_css.py",
        f" * Theme: {theme_name}",
        " */",
        "",
    ]
    lines.extend(_hex_to_css(role, theme[role]) for role in COLOR_ROLES)
    lines.append("")
    lines.append(f"/* spacing grid: {tokens['meta']['grid']} px */")
    lines.append("")

    # Structural CSS on top of the colour definitions.
    body_size = next(item for item in type_scale if item["name"] == "body")
    radius_md = radii["md"]
    radius_lg = radii["lg"]
    spacing_2 = spacing["2"]
    spacing_3 = spacing["3"]
    spacing_4 = spacing["4"]
    border = tokens["borders"]["hairline"]
    focus_width = tokens["focus"]["ringWidth"]

    lines.append(
        f"""
* {{
  font-family: "{tokens['typography']['families']['text']}",
               "{tokens['typography']['families']['fallback']}", sans-serif;
  font-size: {body_size['size']}pt;
  color: @zaod_text-primary;
  background-color: @zaod_background;
}}

window, dialog, popover, menu {{
  background-color: @zaod_surface;
  color: @zaod_text-primary;
  border-radius: {radius_lg}px;
}}

headerbar, .titlebar {{
  background-color: @zaod_surface-alt;
  border-bottom: {border}px solid @zaod_border;
  padding: {spacing_2}px {spacing_3}px;
}}

button {{
  background-color: @zaod_surface-alt;
  color: @zaod_text-primary;
  border: {border}px solid @zaod_border;
  border-radius: {radius_md}px;
  padding: {spacing_2}px {spacing_4}px;
  min-height: {tokens['focus']['minTargetSize']}px;
  transition: background-color {tokens['motion']['fast']}ms {tokens['motion']['easing']};
}}

button:hover {{ background-color: @zaod_accent-subtle; }}
button:active {{ background-color: @zaod_accent-subtle; border-color: @zaod_accent-pressed; }}
button:focus-visible {{ outline: {focus_width}px solid @zaod_focus-ring; outline-offset: 2px; }}
button.suggested-action {{ background-color: @zaod_accent; color: @zaod_on-accent; border-color: @zaod_accent; }}
button.destructive-action {{ background-color: @zaod_danger; color: @zaod_on-danger; border-color: @zaod_danger; }}
button:disabled {{ color: @zaod_text-disabled; }}

entry, spinbutton, textview, .view {{
  background-color: @zaod_surface;
  color: @zaod_text-primary;
  border: {border}px solid @zaod_border;
  border-radius: {radius_md}px;
  padding: {spacing_2}px {spacing_3}px;
  caret-color: @zaod_text-primary;
}}

entry:focus, textview:focus {{ border-color: @zaod_focus-ring; }}

label:disabled, .dim-label {{ color: @zaod_text-secondary; }}

*:link, *:visited {{ color: @zaod_accent; }}
selection {{ background-color: @zaod_accent; color: @zaod_on-accent; }}

scrollbar slider {{ background-color: @zaod_border; border-radius: {radii['pill']}px; min-width: 8px; }}
scrollbar slider:hover {{ background-color: @zaod_border-strong; }}

switch {{ border-radius: {radii['pill']}px; border: {border}px solid @zaod_border; }}
switch:checked {{ background-color: @zaod_accent; border-color: @zaod_accent; }}
progressbar progress {{ background-color: @zaod_accent; border-radius: {radii['pill']}px; }}
tooltip {{ background-color: @zaod_surface-overlay; color: @zaod_text-primary; border-radius: {radius_md}px; }}
"""
    )
    return "\n".join(lines)


def render_entry_point(theme_name: str) -> str:
    return (
        "/* GENERATED FILE - do not edit. Entry point for the Zaod GTK theme. */\n"
        f'@import url("zaod-{theme_name}.css");\n'
    )


def outputs(tokens: dict) -> dict:
    result = {}
    for target in TARGETS:
        for theme_name in ("light", "dark"):
            result[GTK_ROOT / target / f"zaod-{theme_name}.css"] = render_css(tokens, theme_name)
        result[GTK_ROOT / target / "gtk.css"] = render_entry_point("light")
        result[GTK_ROOT / target / "gtk-dark.css"] = render_entry_point("dark")
    return result


def write_outputs(tokens: dict) -> list:
    written = []
    for path, content in outputs(tokens).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def stale_paths(tokens: dict) -> list:
    stale = []
    for path, content in outputs(tokens).items():
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            stale.append(path)
    return stale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed CSS is stale")
    args = parser.parse_args(argv)
    tokens = load_tokens()
    if args.check:
        stale = stale_paths(tokens)
        if stale:
            for path in stale:
                print(f"tokens_to_css: stale {path}", file=sys.stderr)
            return 1
        print("tokens_to_css: all generated CSS is up to date")
        return 0
    for path in write_outputs(tokens):
        print(f"tokens_to_css: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
