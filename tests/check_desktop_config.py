#!/usr/bin/env python3
"""Validate the shipped Phase 5 desktop configuration.

Runs without Plasma, SDDM or a display. It checks the things that break a
session at boot time: unparseable INI, session entries pointing at nonsense,
install scripts that reference missing files, QML files that cannot parse,
leftover stubs, and forbidden vendor assets.

Exit status 0 means every check passed.
"""

from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"

FORBIDDEN_STRINGS = (
    "microsoft",
    "windows 11",
    "segoe",
    "cortana",
    "windows logo",
    "ms-settings",
)
FORBIDDEN_MARKERS = ("todo", "fixme", "xxx:", "lorem ipsum", "not implemented")

ASCII_DESKTOP_KEYS = ("Type", "Name", "Exec", "Comment")


class Report:
    def __init__(self) -> None:
        self.checks = 0
        self.failures = []

    def check(self, condition: bool, label: str, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(f"{label}{(': ' + detail) if detail else ''}")


TEXT_SUFFIXES = {"", ".conf", ".sh", ".py", ".desktop", ".service", ".list", ".svg", ".qml", ".txt"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def iter_text_files(root: Path):
    """Yield every regular text file below root, skipping caches and binaries."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        yield path


def check_ini(report: Report) -> None:
    for path in sorted((DESKTOP / "config").glob("*")):
        if not path.is_file():
            continue
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            parser.read_string(read_text(path))
        except configparser.Error as exc:
            report.check(False, f"{path.relative_to(REPO_ROOT)} parses as INI", str(exc).replace("\n", " "))
            continue
        report.check(bool(parser.sections()), f"{path.relative_to(REPO_ROOT)} has sections")
    for path in sorted((DESKTOP / "sddm").rglob("*.conf")):
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            parser.read_string(read_text(path))
        except configparser.Error as exc:
            report.check(False, f"{path.relative_to(REPO_ROOT)} parses as INI", str(exc))
            continue
        report.check(bool(parser.sections()), f"{path.relative_to(REPO_ROOT)} has sections")


def check_session_entries(report: Report) -> None:
    for path in sorted((DESKTOP / "sessions").glob("*.desktop")):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str  # desktop-entry keys are case sensitive
        parser.read_string(read_text(path))
        sections = {name: dict(parser[name]) for name in parser.sections()}
        report.check("Desktop Entry" in sections, f"{path.name} has a Desktop Entry group")
        entry = sections.get("Desktop Entry", {})
        for key in ASCII_DESKTOP_KEYS:
            report.check(bool(entry.get(key)), f"{path.name} defines {key}")
        exec_value = entry.get("Exec", "")
        report.check(exec_value.startswith("/usr/bin/"), f"{path.name} Exec is an absolute binary", exec_value)
        report.check(
            entry.get("Type") == "Application", f"{path.name} Type is Application", entry.get("Type", "")
        )


def check_install_sources(report: Report) -> None:
    script = DESKTOP / "scripts" / "apply-desktop.sh"
    text = read_text(script)
    referenced = {
        match
        for match in re.findall(r'\$DESKTOP_DIR/([^"\s]+)', text)
        if "$" not in match
    }
    report.check(bool(referenced), "apply-desktop.sh references desktop files")
    for relative in sorted(referenced):
        report.check((DESKTOP / relative).is_file(), f"install source exists: desktop/{relative}")


def check_qml(report: Report) -> None:
    for path in sorted(DESKTOP.rglob("*.qml")):
        text = read_text(path)
        report.check(
            text.count("{") == text.count("}"),
            f"{path.relative_to(REPO_ROOT)} has balanced braces",
            f'{text.count("{")} open vs {text.count("}")} close',
        )
        report.check(
            text.count("(") == text.count(")"),
            f"{path.relative_to(REPO_ROOT)} has balanced parentheses",
        )
        report.check(
            re.search(r"^import QtQuick", text, re.MULTILINE) is not None,
            f"{path.relative_to(REPO_ROOT)} imports QtQuick",
        )
        # A surface or component is a real QML document when it declares a root
        # type: the shell surfaces are items, the screenshot harnesses are
        # windows, and the icon set draws with Canvas or Shape.
        root = re.search(
            r"^\s*(?:Rectangle|Item|Window|Row|Column|Grid|Flow|Shape|Canvas|Text|Image|MouseArea)\s*\{",
            text,
            re.MULTILINE,
        )
        report.check(
            "function" in text or root is not None,
            f"{path.relative_to(REPO_ROOT)} has content",
        )


# The vendor scanner must name the vendors it rejects, so it is exempt from the
# content scan; it is itself the enforcement for everything else.
VENDOR_SCANNER = "desktop/design/tools/scan_assets.py"


def check_no_stubs_and_vendor_assets(report: Report) -> None:
    for path in iter_text_files(DESKTOP):
        if str(path.relative_to(REPO_ROOT)) == VENDOR_SCANNER:
            continue
        text = read_text(path).lower()
        for marker in FORBIDDEN_MARKERS:
            report.check(marker not in text, f"{path.relative_to(REPO_ROOT)} free of '{marker}'")
        for vendor in FORBIDDEN_STRINGS:
            report.check(vendor not in text, f"{path.relative_to(REPO_ROOT)} free of '{vendor}'")


def check_theme(report: Report) -> None:
    theme_dir = DESKTOP / "sddm" / "themes" / "zaod"
    for name in ("theme.conf", "metadata.desktop", "Main.qml"):
        report.check((theme_dir / name).is_file(), f"sddm theme ships {name}")
    theme_conf = configparser.ConfigParser(interpolation=None)
    theme_conf.read_string(read_text(theme_dir / "theme.conf"))
    background = theme_conf.get("General", "background", fallback="")
    report.check(bool(background), "theme.conf declares a background")
    report.check((theme_dir / background).is_file(), f"theme background exists: {background}")
    main_qml = read_text(theme_dir / "Main.qml")
    for symbol in ("sddm.login", "sddm.powerOff", "sddm.reboot", "passwordField"):
        report.check(symbol in main_qml, f"Main.qml uses {symbol}")
    report.check("userModel.lastUser" in main_qml, "Main.qml reads the last user")


def check_lite_mode_wiring(report: Report) -> None:
    unit = (DESKTOP / "systemd" / "zaod-lite-mode.service").read_text()
    report.check("Before=display-manager.service" in unit, "lite mode runs before the display manager")
    report.check("--apply" in unit, "lite mode applies on boot")
    report.check("NoNewPrivileges=yes" in unit, "lite mode is sandboxed")
    report.check((DESKTOP / "tools" / "lite_mode.py").is_file(), "lite mode tool is shipped")
    wrapper = (DESKTOP / "scripts" / "lite-mode.sh").read_text()
    report.check("lite_mode.py" in wrapper, "wrapper points at the tool")


def check_mimeapps(report: Report) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string((DESKTOP / "config" / "mimeapps.list").read_text())
    defaults = parser["Default Applications"]
    report.check(bool(defaults), "mimeapps.list declares defaults")
    for mime, target in defaults.items():
        report.check(mime.count("/") == 1, f"mimeapps key looks like a MIME type: {mime}")
        report.check(
            re.fullmatch(r"[A-Za-z0-9._-]+\.desktop", target) is not None,
            f"mimeapps value is a desktop id: {target}",
        )


def main() -> int:
    report = Report()
    check_ini(report)
    check_session_entries(report)
    check_install_sources(report)
    check_qml(report)
    check_no_stubs_and_vendor_assets(report)
    check_theme(report)
    check_lite_mode_wiring(report)
    check_mimeapps(report)

    print(f"desktop config checks: {report.checks} run, {len(report.failures)} failed")
    for failure in report.failures:
        print(f"  FAIL {failure}")
    if report.failures:
        return 1
    print("desktop config checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
