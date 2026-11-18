"""Zaod desktop settings: stored once, applied through the tools the image ships.

Plasma is not in this image, so nothing here may call ``kwriteconfig6`` or
``plasma-apply-colorscheme``. A setting is a key in
``~/.config/zaod/settings.json``; applying it means running the real tool
(``wpctl``, ``brightnessctl``, ``wlr-randr``, ``wlsunset``) or telling the next
session to start with it (``ZAOD_THEME`` and friends, read by ``zaod-session``).

Every ``apply`` returns a short sentence for the status line and raises
``SettingError`` with a human message when the tool is missing or refuses.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULTS = {
    "theme": "dark",
    "accent": "blue",
    "text_scale": 100,
    "night_light": False,
    "lite_mode": False,
    "wallpaper": "",
}

ACCENTS = {
    "blue": ("#4CC2FF", "#0067C0"),
    "teal": ("#4DD0C0", "#007A6C"),
    "violet": ("#B79CFF", "#6B47D6"),
    "rose": ("#FF8FB1", "#C2275C"),
}


class SettingError(RuntimeError):
    """A setting could not be read or applied; the message is fit to show."""


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path(os.environ.get("HOME", "/root")) / ".config")
    return Path(base) / "zaod"


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_dir() / "settings.json"

    def load(self) -> dict:
        data = dict(DEFAULTS)
        try:
            data.update(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            pass
        return data

    def get(self, key: str):
        return self.load().get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        if key not in DEFAULTS:
            raise SettingError(f"unknown setting {key}")
        data = self.load()
        data[key] = value
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n")
            tmp.replace(self.path)
        except OSError as error:
            raise SettingError(f"could not save settings: {error}") from error
        self.write_environment(data)

    def write_environment(self, data: dict | None = None) -> None:
        """The file the session sources at login so apps pick the choice up."""
        data = data or self.load()
        lines = [
            f"ZAOD_THEME={data['theme']}",
            f"ZAOD_TEXT_SCALE={int(data['text_scale'])}",
            f"ZAOD_ACCENT={data['accent']}",
            f"ZAOD_LITE={'1' if data['lite_mode'] else '0'}",
        ]
        target = self.path.parent / "session.env"
        try:
            target.write_text("\n".join(lines) + "\n")
        except OSError:
            pass


def _run(argv: list[str], timeout: int = 10) -> str:
    exe = shutil.which(argv[0])
    if exe is None:
        raise SettingError(f"{argv[0]} is not installed on this system")
    try:
        result = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise SettingError(f"{argv[0]} did not answer") from error
    if result.returncode != 0:
        line = (result.stderr or result.stdout).strip().splitlines()
        raise SettingError(line[0] if line else f"{argv[0]} failed")
    return result.stdout.strip()


# ---- sound ---------------------------------------------------------------------
def get_volume() -> tuple[int, bool]:
    """(percent, muted) of the default output."""
    text = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    match = re.search(r"([0-9]*\.?[0-9]+)", text)
    if not match:
        raise SettingError("no audio output was found")
    return round(float(match.group(1)) * 100), "[MUTED]" in text


def set_volume(percent: int) -> str:
    percent = max(0, min(150, int(percent)))
    _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{percent}%"])
    return f"Volume {percent}%"


def set_mute(muted: bool) -> str:
    _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if muted else "0"])
    return "Muted" if muted else "Unmuted"


# ---- brightness ----------------------------------------------------------------
def brightness_available() -> bool:
    if shutil.which("brightnessctl") is None:
        return False
    try:
        return "class" in _run(["brightnessctl", "-m", "info"])
    except SettingError:
        return False


def get_brightness() -> int:
    fields = _run(["brightnessctl", "-m", "info"]).split(",")
    if len(fields) < 4:
        raise SettingError("no screen backlight was found")
    return int(fields[3].rstrip("%"))


def set_brightness(percent: int) -> str:
    percent = max(5, min(100, int(percent)))
    _run(["brightnessctl", "set", f"{percent}%"])
    return f"Brightness {percent}%"


# ---- display -------------------------------------------------------------------
def outputs() -> list[dict]:
    """Connected outputs and their current scale, from wlr-randr."""
    text = _run(["wlr-randr"])
    found: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line and not line.startswith(" "):
            current = {"name": line.split()[0], "scale": 1.0, "mode": ""}
            found.append(current)
        elif current is not None:
            stripped = line.strip()
            if stripped.startswith("Scale:"):
                current["scale"] = float(stripped.split(":", 1)[1])
            elif "current" in stripped and "px" in stripped:
                current["mode"] = stripped.split()[0]
    return found


def set_scale(scale: float) -> str:
    targets = outputs()
    if not targets:
        raise SettingError("no display was found")
    for output in targets:
        _run(["wlr-randr", "--output", output["name"], "--scale", str(scale)])
    return f"Scale {int(scale * 100)}%"


def set_night_light(enabled: bool) -> str:
    # wlsunset has no "off": it is a process, so the toggle starts or stops it.
    subprocess.run(["pkill", "-x", "wlsunset"], check=False, capture_output=True)
    if not enabled:
        return "Night light off"
    exe = shutil.which("wlsunset")
    if exe is None:
        raise SettingError("wlsunset is not installed on this system")
    subprocess.Popen(
        [exe, "-t", "4000", "-T", "6500", "-S", "07:00", "-s", "19:30"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return "Night light on"


# ---- power / system ------------------------------------------------------------
def battery() -> tuple[int, str] | None:
    """(percent, state) of the first battery, or None on a desktop."""
    root = Path("/sys/class/power_supply")
    if not root.is_dir():
        return None
    for entry in sorted(root.iterdir()):
        try:
            if (entry / "type").read_text().strip() != "Battery":
                continue
            percent = int((entry / "capacity").read_text().strip())
            state = (entry / "status").read_text().strip()
            return percent, state
        except (OSError, ValueError):
            continue
    return None


def system_facts() -> dict:
    facts = {"kernel": os.uname().release, "host": os.uname().nodename}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                facts["os"] = line.split("=", 1)[1].strip('"')
    except OSError:
        facts["os"] = "Zaod OS"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                facts["memory"] = f"{int(line.split()[1]) / 1048576:.1f} GB"
                break
    except OSError:
        pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                facts["cpu"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    usage = shutil.disk_usage("/")
    facts["disk"] = f"{usage.free / 1073741824:.1f} GB free of {usage.total / 1073741824:.1f} GB"
    return facts
