"""Filesystem layout of a Zaod system, relocatable for tests and build hosts."""

from __future__ import annotations

import os
import re
from pathlib import Path


class Paths:
    """Resolve every Zaod path below ``root`` (``/`` on a real system).

    Tests and build hosts set ``ZAOD_ROOT`` (or pass ``root=``) so the whole
    package manager can run unprivileged in a temporary directory.
    """

    def __init__(self, root: str | os.PathLike[str] | None = None, home: str | os.PathLike[str] | None = None):
        if root is None:
            root = os.environ.get("ZAOD_ROOT", "/")
        self.root = Path(root).resolve()
        self._home = Path(home).resolve() if home is not None else Path(os.environ.get("HOME", "/root"))
        self.installed = os.environ.get("ZAOD_ROOT") is None

    def path(self, absolute: str) -> Path:
        return self.root / absolute.lstrip("/")

    @property
    def apps_dir(self) -> Path:
        return self.path("/zaod/apps")

    @property
    def runtimes_dir(self) -> Path:
        return self.path("/zaod/runtimes")

    @property
    def keys_dir(self) -> Path:
        return self.path("/etc/zaod/keys")

    @property
    def state_dir(self) -> Path:
        return self.path("/var/lib/zaod")

    @property
    def db_file(self) -> Path:
        return self.state_dir / "db.json"

    @property
    def repos_file(self) -> Path:
        return self.state_dir / "repos.json"

    @property
    def cache_dir(self) -> Path:
        return self.state_dir / "cache"

    @property
    def index_cache_dir(self) -> Path:
        return self.cache_dir / "index"

    @property
    def package_cache_dir(self) -> Path:
        return self.cache_dir / "packages"

    @property
    def os_release(self) -> Path:
        return self.path("/etc/os-release")

    @property
    def applications_dir(self) -> Path:
        return self.path("/usr/share/applications")

    @property
    def user_data_dir(self) -> Path:
        return self._home / ".zaod" / "data"

    @property
    def user_config_dir(self) -> Path:
        return self._home / ".config"

    def app_dir(self, app_id: str) -> Path:
        return self.apps_dir / app_id

    def app_version_dir(self, app_id: str, version: str) -> Path:
        return self.app_dir(app_id) / version

    def app_current(self, app_id: str) -> Path:
        return self.app_dir(app_id) / "current"

    def app_data_dir(self, app_id: str) -> Path:
        return self.user_data_dir / app_id

    def desktop_file(self, app_id: str) -> Path:
        return self.applications_dir / f"{app_id}.desktop"

    def os_version(self) -> str:
        """Version of the running Zaod OS, used for ``min_os`` checks.

        Some hosts (a plain Debian container, for example) report a VERSION_ID that
        is not semver. Those values are ignored rather than crashing a comparison.
        """
        from . import DEFAULT_OS_VERSION

        semver = re.compile(r"^\d+\.\d+\.\d+$")
        release = self.os_release
        if release.is_file():
            for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("VERSION_ID="):
                    value = line.split("=", 1)[1].strip().strip('"')
                    if value and semver.match(value):
                        return value
        return DEFAULT_OS_VERSION
