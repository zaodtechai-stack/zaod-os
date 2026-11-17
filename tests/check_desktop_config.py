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

    def contains(self, text: str, needle: str, label: str) -> None:
        """A file has to carry this line for the desktop to work."""
        self.check(needle in text, label, needle)


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
        report.check(
            exec_value.startswith(("/usr/bin/", "/usr/local/bin/")),
            f"{path.name} Exec is an absolute binary",
            exec_value,
        )
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
    check_theme_metadata(report, theme_dir)
    check_theme_qml(report, theme_dir)
    check_zaod_session(report)
    check_login_theme_modules(report)


def check_theme_metadata(report: Report, theme_dir) -> None:
    """The keys SDDM reads, in the section it reads them from.

    ThemeMetadata parses [SddmGreeterTheme] and defaults QtVersion to 5. An image
    that ships only /usr/bin/sddm-greeter-qt6 then has no greeter for the theme and
    paints its own default screen instead, which is exactly how the Zaod login
    screen once went missing. Declaring the keys under [Desktop Entry] looks right
    in a diff and is silently ignored.
    """
    metadata = configparser.ConfigParser(interpolation=None)
    metadata.optionxform = str
    metadata.read_string(read_text(theme_dir / "metadata.desktop"))
    report.check(
        metadata.has_section("SddmGreeterTheme"),
        "sddm theme metadata uses the [SddmGreeterTheme] section",
    )
    if not metadata.has_section("SddmGreeterTheme"):
        return
    section = metadata["SddmGreeterTheme"]
    report.check(
        section.get("ConfigFile", "") == "theme.conf",
        "sddm theme metadata names theme.conf",
    )
    report.check(
        section.get("MainScript", "") == "Main.qml",
        "sddm theme metadata names Main.qml",
    )
    report.check(
        section.get("QtVersion", "") == "6",
        "sddm theme metadata declares the Qt the greeter is built against",
    )


def check_theme_qml(report: Report, theme_dir) -> None:
    """The theme QML has to be loadable by the Qt the greeter is built against.

    A single unknown property is enough for the greeter to throw the file away and
    paint its own "The current theme cannot be loaded due to the errors below"
    screen on top of the login box - which is what `palette.button: root.accent`
    did: Qt Quick Controls here has no palette property on Button, so the login
    screen could be seen but never used. Button colouring goes through
    background/contentItem, which every Control has.
    """
    qml = read_text(theme_dir / "Main.qml")
    # Only real property assignments count: the comments in Main.qml name the bad
    # line on purpose, so a plain substring search would match them.
    code = "\n".join(
        line.split("//", 1)[0] for line in qml.splitlines() if not line.strip().startswith("//")
    )
    report.check(
        re.search(r"\bpalette\.[A-Za-z]+:", code) is None,
        "sddm theme paints buttons without the absent palette property",
    )
    report.check(
        "background:" in qml and "contentItem:" in qml,
        "sddm theme styles the primary button through background/contentItem",
    )
    report.check(
        "import SddmComponents" in qml,
        "sddm theme imports SddmComponents",
    )


def check_zaod_session(report: Report) -> None:
    """The desktop is Zaod's own: no Plasma, no KDE, no third-party shell.

    The session entry is what the login screen starts, so it is the one place
    where a leftover desktop can quietly come back. It has to point at the Zaod
    script, that script has to start labwc, the panel has to be installed as an
    executable, and no Plasma/KDE session may be shipped alongside it.
    """
    session = (DESKTOP / "sessions" / "zaod.desktop").read_text()
    report.contains(session, "Exec=/usr/local/bin/zaod-session", "the session starts the Zaod desktop")
    report.check("DesktopNames=Zaod" in session, "the session names the Zaod desktop")
    for stray in (DESKTOP / "sessions").glob("plasma*.desktop"):
        report.check(False, f"no Plasma session entry ships: {stray.name}")

    script = (DESKTOP / "shell" / "zaod-session").read_text()
    report.contains(script, "exec /usr/bin/labwc", "the compositor is labwc")
    report.contains(script, "XDG_CURRENT_DESKTOP=Zaod", "the session says which desktop it is")

    installer = (DESKTOP / "scripts" / "apply-desktop.sh").read_text()
    for needle, why in (
        ("$DESKTOP_DIR/shell/panel.py", "the panel is installed"),
        ("$DESKTOP_DIR/shell/zaod-session", "the session script is installed"),
        ("$DESKTOP_DIR/sessions/zaod.desktop", "the session entry is installed"),
        ("etc/xdg/labwc/autostart", "the panel starts with the compositor"),
    ):
        report.contains(installer, needle, why)

    panel = (DESKTOP / "shell" / "panel.py").read_text()
    report.contains(panel, "org.zaod.store", "the panel launches the app store")
    report.contains(panel, "Gio.AppInfo", "the launcher lists installed apps instead of a hard-coded menu")
    report.check(
        all(not line.strip().startswith("import PyQt") for line in panel.splitlines()),
        "the panel draws with GTK, which the image already ships",
    )


def check_app_set(report: Report, tmp_root) -> None:
    """Every first-party app reaches the launcher, through a .desktop entry.

    An image that boots to an empty desktop is what this replaces: the panel and
    the store both read /usr/share/applications, so the app set has to be staged
    with entries before the rootfs is squashed.
    """
    entry = REPO_ROOT / "scripts" / "install-app-set.py"
    report.check(entry.is_file(), "the app set installer is part of the build")
    if not entry.is_file():
        return
    root = tmp_root / "rootfs-app-set"
    (root / "etc").mkdir(parents=True, exist_ok=True)
    import subprocess

    result = subprocess.run(
        [sys.executable, str(entry), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    report.check(result.returncode == 0, "the app set installs into a root filesystem", result.stderr[-300:])
    entries = sorted(p.name for p in (root / "usr/share/applications").glob("*.desktop"))
    for app_id in ("org.zaod.store", "org.zaod.editor", "org.zaod.notes", "org.zaod.control-center"):
        report.check(f"{app_id}.desktop" in entries, f"the launcher gets an entry for {app_id}")
    store_entry = root / "usr/share/applications" / "org.zaod.store.desktop"
    report.check(store_entry.is_file(), "the app store is installed")
    if store_entry.is_file():
        report.contains(store_entry.read_text(), "Icon=org.zaod.store", "the store entry carries its icon")
    build = (REPO_ROOT / "scripts" / "build-rootfs.sh").read_text()
    report.contains(build, "install-app-set.py", "the image build installs the app set")


QML_MODULE_PACKAGES = {
    "QtQuick": "qml6-module-qtquick",
    "QtQuick.Window": "qml6-module-qtquick-window",
    "QtQuick.Controls": "qml6-module-qtquick-controls",
    "QtQuick.Templates": "qml6-module-qtquick-templates",
    "QtQuick.Layouts": "qml6-module-qtquick-layouts",
    "QtQuick.Shapes": "qml6-module-qtquick-shapes",
    "QtQml": "qml6-module-qtqml",
    "QtQml.Models": "qml6-module-qtqml-models",
}


def check_login_theme_modules(report: Report) -> None:
    """The login theme's QtQuick imports have to be installed in the image.

    QtQuick is split into per-module Debian packages. While the image carried
    Plasma those modules arrived as dependencies; on their own the greeter shows
    "module \"QtQuick.Layouts\" is not installed" and refuses the theme, which is
    what a person sees instead of their login screen.
    """
    packages = {
        line.strip()
        for line in (REPO_ROOT / "rootfs" / "packages.list").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    theme_files = sorted((DESKTOP / "sddm" / "themes" / "zaod").glob("*.qml"))
    report.check(bool(theme_files), "the login theme has QML to check")
    imported = set()
    for path in theme_files:
        for line in read_text(path).splitlines():
            line = line.strip()
            if not line.startswith("import "):
                continue
            module = line.split()[1]
            if module in QML_MODULE_PACKAGES:
                imported.add(module)
    report.check(bool(imported), "the login theme imports QtQuick modules")
    for module in sorted(imported):
        package = QML_MODULE_PACKAGES[module]
        report.check(
            package in packages,
            f"the image installs {package} for the login theme's {module} import",
        )


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
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        check_app_set(report, Path(tmp))

    print(f"desktop config checks: {report.checks} run, {len(report.failures)} failed")
    for failure in report.failures:
        print(f"  FAIL {failure}")
    if report.failures:
        return 1
    print("desktop config checks: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
