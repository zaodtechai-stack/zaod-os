"""bubblewrap sandbox construction for Zaod applications."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .errors import SandboxError
from .manifest import Manifest

XDG_DIRECTORIES = {
    "documents": "Documents",
    "downloads": "Downloads",
    "music": "Music",
    "pictures": "Pictures",
    "videos": "Videos",
    "desktop": "Desktop",
}

DEVICE_PATHS = {
    "dri": ["/dev/dri"],
    "input": ["/dev/input"],
    "usb": ["/dev/bus/usb"],
    "kvm": ["/dev/kvm"],
}

AUDIO_PATHS = ["/run/user/%UID%/pipewire-0", "/run/user/%UID%/pulse/native", "/dev/snd"]


@dataclass
class SandboxPlan:
    argv: list[str]
    permissions: list[str] = field(default_factory=list)
    data_dir: Path | None = None

    def describe(self) -> str:
        if not self.permissions:
            return "no extra permissions (no network, isolated home)"
        return ", ".join(self.permissions)


def permission_summary(manifest: Manifest) -> list[str]:
    """Human readable permission list shown before install and in the store."""
    summary: list[str] = []
    if manifest.network:
        summary.append("network access")
    for item in manifest.filesystem_permissions:
        summary.append(f"files: {item}")
    for device in manifest.device_permissions:
        summary.append(f"device: {device}")
    return summary


def bwrap_binary() -> str:
    binary = shutil.which("bwrap")
    if not binary:
        raise SandboxError("bwrap (bubblewrap) is not installed; run 'zaod run' on a Zaod system")
    return binary


def build_plan(
    paths,
    manifest: Manifest,
    *,
    app_root: Path | None = None,
    data_dir: Path | None = None,
    home: Path | None = None,
    runtime_dir: Path | None = None,
    wayland_display: str | None = None,
    env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    binary: str | None = None,
) -> SandboxPlan:
    """Build the full ``bwrap`` command line for ``manifest``."""
    app_root = Path(app_root) if app_root else paths.app_current(manifest.id)
    data_dir = Path(data_dir) if data_dir else paths.app_data_dir(manifest.id)
    home = Path(home) if home else paths.user_data_dir.parent.parent
    data_dir.mkdir(parents=True, exist_ok=True)

    argv = [
        binary or bwrap_binary(),
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--tmpfs", "/run",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind-try", "/bin", "/bin",
        "--ro-bind-try", "/sbin", "/sbin",
        "--ro-bind-try", "/lib", "/lib",
        "--ro-bind-try", "/lib64", "/lib64",
        "--ro-bind-try", "/etc/fonts", "/etc/fonts",
        "--ro-bind-try", "/etc/ssl", "/etc/ssl",
        "--ro-bind-try", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind-try", "/etc/ld.so.cache", "/etc/ld.so.cache",
        "--ro-bind-try", "/etc/pipewire", "/etc/pipewire",
        "--ro-bind-try", "/etc/alsa", "/etc/alsa",
        "--ro-bind", str(app_root), "/app",
        "--bind", str(data_dir), "/data",
        "--chdir", "/app",
        "--setenv", "HOME", "/data",
        "--setenv", "XDG_DATA_HOME", "/data/.local/share",
        "--setenv", "XDG_CONFIG_HOME", "/data/.config",
        "--setenv", "XDG_CACHE_HOME", "/data/.cache",
        "--setenv", "XDG_RUNTIME_DIR", "/run/user",
        "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
        "--setenv", "ZAOD_APP_ID", manifest.id,
        "--setenv", "ZAOD_APP_VERSION", manifest.version,
    ]

    permissions = permission_summary(manifest)

    if manifest.network:
        argv.append("--share-net")
        argv.extend(["--setenv", "ZAOD_NETWORK", "1"])

    if "home" in manifest.filesystem_permissions:
        argv.extend(["--bind-try", str(home), str(home)])
    for name in manifest.filesystem_permissions:
        directory = XDG_DIRECTORIES.get(name)
        if directory is None:
            continue
        target = home / directory
        argv.extend(["--bind-try", str(target), str(target)])
    if "removable" in manifest.filesystem_permissions:
        for media in ("/media", "/run/media"):
            argv.extend(["--bind-try", media, media])

    if wayland_display and runtime_dir is not None:
        socket = Path(runtime_dir) / wayland_display
        argv.extend(["--bind-try", str(socket), f"/run/user/{wayland_display}"])
        argv.extend(["--setenv", "WAYLAND_DISPLAY", wayland_display])
        argv.extend(["--setenv", "XDG_RUNTIME_DIR", "/run/user"])

    for device in manifest.device_permissions:
        if device == "audio":
            for candidate in AUDIO_PATHS:
                argv.extend(["--dev-bind-try" if candidate.startswith("/dev") else "--bind-try",
                             candidate, candidate])
            continue
        for device_path in DEVICE_PATHS.get(device, []):
            argv.extend(["--dev-bind-try", device_path, device_path])

    for key, value in sorted((manifest.permissions.get("env") or {}).items()):
        argv.extend(["--setenv", key, value])
    for key, value in sorted((env or {}).items()):
        argv.extend(["--setenv", key, value])

    command = [f"/app/{manifest.entry['exec']}", *manifest.entry.get("args", [])]
    if extra_args:
        command.extend(extra_args)
    argv.extend(["--", *command])
    return SandboxPlan(argv=argv, permissions=permissions, data_dir=data_dir)
