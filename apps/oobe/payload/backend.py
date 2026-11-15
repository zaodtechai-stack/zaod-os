"""First-boot setup state for Zaod OS.

Setup is offline-only and makes the privacy default explicit: no telemetry or
diagnostics are ever sent unless the person turns them on, and the choice is
recorded so later boots can show it back to them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS = {
    "appearance": "light",
    "accent": "blue",
    "updates": "security-only",
    "telemetry": False,
    "location": False,
    "completed": False,
}

APPEARANCES = ("light", "dark")
ACCENTS = ("blue", "teal", "violet", "amber")
UPDATE_MODES = ("manual", "security-only", "automatic")


class SetupError(ValueError):
    """A setup answer that cannot be accepted."""


def config_dir(home: str | os.PathLike[str] | None = None) -> Path:
    base = Path(home) if home is not None else Path(os.environ.get("HOME", "~")).expanduser()
    return base / ".config" / "zaod"


def state_file(home: str | os.PathLike[str] | None = None) -> Path:
    return config_dir(home) / "oobe.json"


def load_state(home: str | os.PathLike[str] | None = None) -> dict:
    path = state_file(home)
    state = dict(DEFAULTS)
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return state
        if isinstance(stored, dict):
            state.update({key: stored[key] for key in DEFAULTS if key in stored})
    return state


class Setup:
    """Collect first-boot answers and finish setup exactly once."""

    def __init__(self, home: str | os.PathLike[str] | None = None):
        self.home = home
        self.state = load_state(home)

    # ------------------------------------------------------------------ queries
    @property
    def completed(self) -> bool:
        return bool(self.state.get("completed"))

    def summary(self) -> str:
        mode = {
            "manual": "you install updates yourself",
            "security-only": "security updates only",
            "automatic": "updates download and install automatically",
        }[self.state["updates"]]
        telemetry = "shared when you choose to send it" if self.state["telemetry"] else "never sent"
        return f"{self.state['appearance']} theme, {self.state['accent']} accent, {mode}, diagnostics {telemetry}"

    # ----------------------------------------------------------------- mutation
    def set(self, key: str, value) -> None:
        if key not in DEFAULTS or key == "completed":
            raise SetupError(f"unknown setting {key!r}")
        if key == "appearance" and value not in APPEARANCES:
            raise SetupError(f"appearance must be one of {', '.join(APPEARANCES)}")
        if key == "accent" and value not in ACCENTS:
            raise SetupError(f"accent must be one of {', '.join(ACCENTS)}")
        if key == "updates" and value not in UPDATE_MODES:
            raise SetupError(f"updates must be one of {', '.join(UPDATE_MODES)}")
        if key in ("telemetry", "location") and not isinstance(value, bool):
            raise SetupError(f"{key} must be true or false")
        self.state[key] = value

    def finish(self) -> dict:
        """Record the answers and mark setup complete. Requires a real choice."""
        if self.state["updates"] not in UPDATE_MODES:
            raise SetupError("choose how updates should be handled")
        self.state["completed"] = True
        self.save()
        return dict(self.state)

    def save(self) -> Path:
        path = state_file(self.home)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return path
