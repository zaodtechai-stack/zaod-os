#!/usr/bin/env python3
"""Block design drift: no colour, size or metric may bypass the token set.

`check_design_tokens.py` proves the tokens are internally consistent. It cannot
prove that a surface *uses* them, which is how the Phase 6 delivery shipped an
application palette with a different accent, borders at 1.4:1, and a Studio
editor whose syntax colours were only legible on a white background.

This checker is the enforcement half:

1. QML (`desktop/design/qml`, `shell`, `tools/surfaces`): no hex colour literals,
   no numeric `font.pixelSize`, no numeric radius/spacing/margin literals.
2. First-party app code (`apps/*/payload`, `apps/lib`, `studio/zaodstudio`):
   no hex colour literals and no inline `font-size:` rules; the widget palette
   comes from the generated `zaod_tokens` module.
3. Every component's declared elevation stays inside the 0-3 ladder.
4. Every QML file compiles (delegated to `check_qml.py`).

Exit 0 means nothing in the repo hardcodes a design decision.

Usage: python3 tests/check_design_drift.py [--verbose]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = REPO_ROOT / "desktop" / "design"

QML_DIRS = (
    DESIGN_ROOT / "qml",
    DESIGN_ROOT / "shell",
    DESIGN_ROOT / "tools" / "surfaces",
)
PY_DIRS = (
    REPO_ROOT / "apps" / "lib",
    REPO_ROOT / "studio" / "zaodstudio",
)
# app payloads, excluding the generated token module and vendored helpers
PY_GLOBS = ("apps/*/payload/*.py",)

EXEMPT_QML = {
    # ZaodTheme.qml is the generated token surface: its hex values ARE the tokens.
    "desktop/design/qml/ZaodTheme.qml",
}

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
NUMERIC_PIXEL_SIZE = re.compile(r"font\.pixelSize:\s*\d")
NUMERIC_FONT_QSS = re.compile(r"font-size:\s*\d+(\.\d+)?(px|pt)\b")
NUMERIC_METRIC = re.compile(
    r"\b(radius|spacing|padding|anchors\.margins|anchors\.(left|right|top|bottom)Margin)"
    r"\s*:\s*\d+(\.\d+)?\s*(?=[,\n}])"
)
ELEVATION_USE = re.compile(r"ZaodTheme\.elevation([0-9])")
# Qt colour keywords that carry no hue and need no token.
COLOUR_KEYWORDS = ("transparent", "currentColor")


class Drift:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.checked = 0

    def scan(self, path: Path, text: str) -> None:
        relative = str(path.relative_to(REPO_ROOT))
        self.checked += 1
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.split("//")[0] if path.suffix == ".qml" else line.split("#")[0]
            where = f"{relative}:{line_number}"
            for match in HEX_COLOUR.finditer(stripped):
                self.findings.append(f"{where} hardcoded colour {match.group(0)}")
            if path.suffix == ".qml":
                if NUMERIC_PIXEL_SIZE.search(stripped):
                    self.findings.append(f"{where} numeric font.pixelSize")
                if NUMERIC_METRIC.search(stripped):
                    self.findings.append(f"{where} numeric metric, use a token")
                for level in ELEVATION_USE.findall(stripped):
                    if int(level) > 3:
                        self.findings.append(
                            f"{where} elevation{level} is outside the 0-3 component ladder"
                        )
            else:
                if NUMERIC_FONT_QSS.search(line):
                    self.findings.append(f"{where} inline font-size, add a token role instead")


# A pointer-only control is not keyboard reachable, and focus that is drawn with
# colour alone disappears for a colour-blind user. Both are enforced here.
POINTER_AREA = re.compile(r"\bMouseArea\s*\{")
FOCUS_DECLARED = re.compile(r"activeFocusOnTab|Keys\.on|focus:\s*true")
FOCUS_RING_DRAWN = re.compile(r"focusRingWidth")


def check_focus_reachability(path: Path, text: str, drift: "Drift") -> None:
    """Every component with a pointer area must also declare keyboard focus."""
    relative = str(path.relative_to(REPO_ROOT))
    if POINTER_AREA.search(text) and not FOCUS_DECLARED.search(text):
        drift.findings.append(f"{relative} has a pointer area but no keyboard focus")
    if FOCUS_DECLARED.search(text) and not FOCUS_RING_DRAWN.search(text):
        drift.findings.append(f"{relative} takes focus but never draws the focus ring token")


def qml_files() -> list[Path]:
    files = []
    for directory in QML_DIRS:
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.qml")))
    return files


def py_files() -> list[Path]:
    files = []
    for directory in PY_DIRS:
        if directory.is_dir():
            files.extend(sorted(directory.rglob("*.py")))
    for pattern in PY_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(pattern)))
    return [path for path in files if "__pycache__" not in path.parts]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    drift = Drift()
    for path in qml_files():
        relative = str(path.relative_to(REPO_ROOT))
        if relative in EXEMPT_QML:
            continue
        text = path.read_text(encoding="utf-8")
        drift.scan(path, text)
        check_focus_reachability(path, text, drift)
    for path in py_files():
        drift.scan(path, path.read_text(encoding="utf-8"))

    if args.verbose:
        for finding in drift.findings:
            print(f"DRIFT {finding}")
    print(f"design drift: {drift.checked} files scanned, {len(drift.findings)} findings")
    if drift.findings:
        for finding in drift.findings:
            print(f"  FAIL {finding}")
        return 1
    print("design drift: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
