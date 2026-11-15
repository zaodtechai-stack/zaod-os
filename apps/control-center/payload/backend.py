"""Control Center settings backend.

Every control maps to a real desktop command: NetworkManager for Wi-Fi, KDE
configuration files for appearance and display, PipeWire for sound, the Zaod
configuration file for Lite mode, and the `zaod` CLI for updates. Nothing here
is decorative: if a command is missing the caller gets a precise error.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class SettingError(RuntimeError):
    """A setting could not be read or written."""


class Runner:
    """Runs system commands and reports missing tools instead of crashing."""

    def run(self, argv: list[str], timeout: int = 20) -> str:
        if not argv:
            raise SettingError("empty command")
        executable = shutil.which(argv[0])
        if executable is None:
            raise SettingError(f"{argv[0]} is not installed on this system")
        result = subprocess.run(
            [executable, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise SettingError(f"{' '.join(argv)} failed: {message[0] if message else 'unknown error'}")
        return result.stdout.strip()


@dataclass(frozen=True)
class Control:
    key: str
    label: str
    kind: str  # toggle | choice | slider | action | info
    description: str = ""
    choices: tuple = ()
    read: tuple = ()
    write: tuple = ()
    post: tuple = ()
    parser: str = "raw"
    value_map: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Page:
    key: str
    title: str
    summary: str
    controls: tuple


def _cmd(*parts: str) -> tuple:
    return tuple(parts)


READ_KCONFIG = ("kreadconfig6", "--file")
WRITE_KCONFIG = ("kwriteconfig6", "--file")


def default_pages() -> tuple[Page, ...]:
    network = Page(
        "network",
        "Network",
        "Wi-Fi radio and saved connections",
        (
            Control(
                "wifi",
                "Wi-Fi",
                "toggle",
                "Turns the wireless radio on or off through NetworkManager.",
                read=_cmd("nmcli", "-t", "-f", "WIFI", "general"),
                write=_cmd("nmcli", "radio", "wifi", "{value}"),
                value_map={"enabled": "on", "disabled": "off", "on": "on", "off": "off"},
            ),
            Control(
                "connections",
                "Saved connections",
                "info",
                "NetworkManager connection profiles on this system.",
                read=_cmd("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"),
            ),
        ),
    )
    appearance = Page(
        "appearance",
        "Appearance",
        "Colour scheme and accent colour",
        (
            Control(
                "color_scheme",
                "Colour scheme",
                "choice",
                "Switches the desktop between the Zaod light and dark schemes.",
                choices=(("ZaodLight", "Light"), ("ZaodDark", "Dark")),
                read=(*READ_KCONFIG, "kdeglobals", "--group", "General", "--key", "ColorScheme"),
                write=_cmd("plasma-apply-colorscheme", "{value}"),
            ),
            Control(
                "accent",
                "Accent colour",
                "choice",
                "Accent used by shell widgets and app highlights.",
                choices=(("blue", "Blue"), ("teal", "Teal"), ("violet", "Violet"), ("rose", "Rose")),
                read=(*READ_KCONFIG, "zaodrc", "--group", "Appearance", "--key", "Accent"),
                write=(*WRITE_KCONFIG, "zaodrc", "--group", "Appearance", "--key", "Accent", "{value}"),
            ),
        ),
    )
    display = Page(
        "display",
        "Display",
        "Night light and UI scaling",
        (
            Control(
                "night_light",
                "Night light",
                "toggle",
                "Warmer colours after sunset; KWin applies the change immediately.",
                choices=(("true", "On"), ("false", "Off")),
                read=(*READ_KCONFIG, "kwinrc", "--group", "NightColor", "--key", "Active"),
                write=(*WRITE_KCONFIG, "kwinrc", "--group", "NightColor", "--key", "Active", "{value}"),
                post=_cmd("qdbus", "org.kde.KWin", "/KWin", "reconfigure"),
            ),
            Control(
                "scale",
                "Scale",
                "choice",
                "UI scale factor; Plasma applies it at the next sign-in.",
                choices=(("1", "100%"), ("1.25", "125%"), ("1.5", "150%"), ("2", "200%")),
                read=(*READ_KCONFIG, "kdeglobals", "--group", "KScreen", "--key", "ScaleFactor"),
                write=(*WRITE_KCONFIG, "kdeglobals", "--group", "KScreen", "--key", "ScaleFactor", "{value}"),
            ),
        ),
    )
    sound = Page(
        "sound",
        "Sound",
        "Output volume and mute",
        (
            Control(
                "volume",
                "Volume",
                "slider",
                "Default output volume in percent, applied with wpctl.",
                read=_cmd("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"),
                write=_cmd("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "{value}"),
                parser="volume",
            ),
            Control(
                "mute",
                "Mute",
                "toggle",
                "Mutes or unmutes the default output.",
                read=_cmd("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"),
                write=_cmd("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "{value}"),
                parser="muted",
                value_map={"on": "1", "off": "0"},
            ),
        ),
    )
    power = Page(
        "power",
        "Power",
        "Lite mode for low-memory machines",
        (
            Control(
                "lite_mode",
                "Lite mode",
                "toggle",
                "Drops animations and background services on 2 GB machines.",
                choices=(("true", "On"), ("false", "Off")),
                read=(*READ_KCONFIG, "zaodrc", "--group", "Performance", "--key", "LiteMode"),
                write=(*WRITE_KCONFIG, "zaodrc", "--group", "Performance", "--key", "LiteMode", "{value}"),
            ),
            Control(
                "free_space",
                "Free disk space",
                "info",
                "Space available on the root filesystem.",
                read=_cmd("df", "-h", "--output=avail", "/"),
            ),
        ),
    )
    updates = Page(
        "updates",
        "Updates",
        "Signed package updates for installed apps",
        (
            Control(
                "apply",
                "Install available updates",
                "action",
                "Runs the signed update path through the privileged zaod helper.",
                write=_cmd("pkexec", "zaod-priv-helper", "update"),
            ),
            Control(
                "last_sync",
                "Last store sync",
                "info",
                "When the store index was last verified.",
                parser="repo_sync",
            ),
        ),
    )
    about = Page(
        "about",
        "About",
        "Version information",
        (
            Control("os", "System", "info", "Zaod OS release installed here.", parser="os_release"),
            Control("kernel", "Kernel", "info", "Running kernel release.", read=_cmd("uname", "-r")),
        ),
    )
    return (network, appearance, display, sound, power, updates, about)


class ControlCenter:
    """Read and write every Control Center setting."""

    def __init__(self, runner=None, paths=None):
        self.runner = runner or Runner()
        self.paths = paths
        self._pages = default_pages()

    @property
    def pages(self) -> tuple[Page, ...]:
        return self._pages

    def page(self, page_key: str) -> Page:
        for page in self._pages:
            if page.key == page_key:
                return page
        raise SettingError(f"no such page: {page_key}")

    def control(self, page_key: str, control_key: str) -> Control:
        for control in self.page(page_key).controls:
            if control.key == control_key:
                return control
        raise SettingError(f"no such setting: {page_key}.{control_key}")

    def get(self, page_key: str, control_key: str) -> str:
        control = self.control(page_key, control_key)
        if control.kind == "action":
            raise SettingError(f"{page_key}.{control_key} is an action, not a value")
        if control.parser == "repo_sync":
            return self._repo_sync()
        if control.parser == "os_release":
            return self._os_release()
        raw = self.runner.run(list(control.read))
        return self._parse(control, raw)

    def set(self, page_key: str, control_key: str, value: str) -> None:
        control = self.control(page_key, control_key)
        if control.kind == "info":
            raise SettingError(f"{page_key}.{control_key} is read-only")
        if control.kind == "action":
            self.runner.run(list(control.write))
            return
        translated = control.value_map.get(str(value), str(value))
        if control.parser == "volume":
            translated = f"{float(value) / 100:.2f}"
        argv = [argument.replace("{value}", translated) for argument in control.write]
        self.runner.run(argv)
        if control.post:
            self.runner.run(list(control.post))

    def _parse(self, control: Control, raw: str) -> str:
        if control.parser == "volume":
            for token in raw.split():
                try:
                    return str(int(round(float(token) * 100)))
                except ValueError:
                    continue
            raise SettingError(f"cannot read the volume from {raw!r}")
        if control.parser == "muted":
            return "on" if "MUTED" in raw.upper() else "off"
        value = raw.strip()
        if not value and control.choices:
            return control.choices[0][0]
        return control.value_map.get(value, value)

    def _repo_sync(self) -> str:
        if self.paths is None:
            return "not configured"
        path = Path(self.paths.repos_file)
        if not path.is_file():
            return "never"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return "unknown"
        stamps = [entry.get("last_sync") for entry in data.get("repos", []) if entry.get("last_sync")]
        return max(stamps) if stamps else "never"

    def _os_release(self) -> str:
        candidates = []
        if self.paths is not None:
            candidates.append(Path(self.paths.os_release))
        candidates.append(Path("/etc/os-release"))
        for path in candidates:
            if path.is_file():
                values = {}
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        values[key] = value.strip().strip('"')
                name = values.get("PRETTY_NAME") or values.get("NAME") or "Zaod OS"
                version = values.get("VERSION_ID", "")
                return f"{name} {version}".strip()
        return "Zaod OS (development build)"
