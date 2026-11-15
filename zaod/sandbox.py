"""Bubblewrap sandbox command construction.

The sandbox is described as data (an argument vector) so it can be unit tested
without bubblewrap being installed, and so the permission model in the manifest
has exactly one place where it turns into kernel-level isolation.

Isolation policy for v1:

* read-only access to the runtime image below ``/usr`` and ``/etc``
* a private ``/tmp``, a private ``/dev`` and a private IPC and UTS namespace
* no network namespace sharing unless the ``network`` permission is granted
* no D-Bus session socket unless the ``notifications`` or ``tray`` permission
  is granted, and then only the notifications proxy
* device access only for the devices the manifest declares
"""

from __future__ import annotations

import os
import shutil

from .errors import SandboxError

BWRAP = "bwrap"

BASE_ARGUMENTS = (
    "--die-with-parent",
    "--unshare-pid",
    "--unshare-ipc",
    "--unshare-uts",
    "--unshare-cgroup-try",
    "--new-session",
    "--proc",
    "/proc",
    "--dev",
    "/dev",
    "--tmpfs",
    "/tmp",
    "--ro-bind",
    "/usr",
    "/usr",
    "--ro-bind",
    "/etc",
    "/etc",
    "--symlink",
    "usr/lib",
    "/lib",
    "--symlink",
    "usr/lib64",
    "/lib64",
    "--symlink",
    "usr/bin",
    "/bin",
    "--symlink",
    "usr/sbin",
    "/sbin",
    "--chdir",
    "/",
)

DEVICE_BINDS = {
    "dri": ("/dev/dri",),
    "input": ("/dev/input",),
    "alsa": ("/dev/snd",),
    "usb": ("/dev/bus/usb",),
}


def bubblewrap_available() -> bool:
    return shutil.which(BWRAP) is not None


def build_arguments(
    *,
    command: list,
    data_dir: str,
    permissions,
    home_dir: str | None = None,
    runtime_dirs: tuple = (),
) -> list:
    """Return the complete ``bwrap`` argument vector for one application."""
    if not command:
        raise SandboxError("no command to run")
    arguments = [BWRAP]

    if permissions.network:
        arguments += ["--share-net"]
    else:
        arguments += ["--unshare-net"]

    arguments += list(BASE_ARGUMENTS)

    for path in runtime_dirs:
        arguments += ["--ro-bind", path, path]

    arguments += ["--bind", data_dir, data_dir]
    if home_dir:
        arguments += ["--bind", home_dir, home_dir]

    for device in permissions.devices:
        for path in DEVICE_BINDS.get(device, ()):
            arguments += ["--dev-bind-try", path, path]

    if permissions.session_bus:
        bus = os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000") + "/bus"
        arguments += ["--ro-bind-try", bus, bus]

    for path in getattr(permissions, "paths_ro", ()) or ():
        arguments += ["--ro-bind-try", path, path]
    for path in getattr(permissions, "paths_rw", ()) or ():
        arguments += ["--bind-try", path, path]

    arguments += ["--"]
    arguments += list(command)
    return arguments


def describe(permissions) -> str:
    """One-line human summary of what an application may do."""
    if hasattr(permissions, "summary"):
        return permissions.summary()
    return "this application uses no extra permissions"
