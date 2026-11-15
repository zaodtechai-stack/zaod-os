"""The Zaod store client.

Responsibilities kept deliberately small and testable:

* fetch an index over ``file://``, ``http://`` or ``https://``
* verify its signature against the trust store and refuse an expired one
* cache the verified document, so an offline machine still shows its catalogue
* resolve what to install or update from the installed database
* download a package and check its declared size and SHA-256 before the
  installer touches it

Nothing here installs anything: :class:`zaod.installer.Installer` does that, so
the download and the transaction stay separable and auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import db as db_mod
from . import repo as repo_mod
from . import semver
from . import signature as signature_mod
from .errors import NetworkError, PackageError, SignatureError

CACHE_RELATIVE_PATH = "var/cache/zaod/index.json"
TIMEOUT_SECONDS = 30


@dataclass
class Update:
    """One package the store can install or upgrade."""

    package_id: str
    current: str | None
    candidate: str
    size: int
    sha256: str
    url: str
    action: str

    def summary(self) -> str:
        if self.action == "install":
            return f"install {self.package_id} {self.candidate}"
        return f"update {self.package_id} {self.current} -> {self.candidate}"


def fetch(url: str, *, timeout: int = TIMEOUT_SECONDS) -> bytes:
    """Read a URL, supporting ``file://`` and plain local paths."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        request = urllib.request.Request(url, headers={"User-Agent": "zaod-store/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            raise NetworkError(f"cannot fetch {url}: {exc}") from exc
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
    elif parsed.scheme == "":
        path = Path(url)
    else:
        raise NetworkError(f"unsupported URL scheme {parsed.scheme!r}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise NetworkError(f"cannot read {path}: {exc}") from exc


class StoreCache:
    """The verified index kept on disk between runs."""

    def __init__(self, root: str | os.PathLike[str] = "/") -> None:
        self.path = Path(root) / CACHE_RELATIVE_PATH

    def load(self) -> dict | None:
        if not self.path.is_file():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def save(self, document: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=".index-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()


class Store:
    """A signed catalogue plus the operations the UI needs."""

    def __init__(
        self,
        *,
        trust: signature_mod.TrustStore,
        root: str | os.PathLike[str] = "/",
        url: str | None = None,
    ) -> None:
        self.trust = trust
        self.root = Path(root)
        self.url = url
        self.cache = StoreCache(self.root)
        self.document: dict | None = None
        self.offline = False

    # -- catalogue ---------------------------------------------------------

    def refresh(self) -> dict:
        """Fetch and verify the index, then cache it."""
        if not self.url:
            raise PackageError("no store URL is configured")
        payload = fetch(self.url)
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PackageError(f"the index at {self.url} is not JSON: {exc}") from exc
        repo_mod.verify_index(document, self.trust)
        self.document = document
        self.cache.save(document)
        self.offline = False
        return document

    def load(self) -> dict:
        """Verified index, from cache when a refresh is impossible."""
        if self.document is not None:
            return self.document
        try:
            return self.refresh()
        except (NetworkError, PackageError, SignatureError):
            cached = self.cache.load()
            if cached is None:
                raise
            repo_mod.verify_index(cached, self.trust)
            self.document = cached
            self.offline = True
            return cached

    def packages(self) -> list:
        return repo_mod.entries(self.load())

    def search(self, query: str) -> list:
        needle = query.strip().lower()
        if not needle:
            return self.packages()
        return [
            entry
            for entry in self.packages()
            if needle in entry.id.lower()
        ]

    def candidate(self, package_id: str, channel: str = "stable"):
        return repo_mod.latest(self.load(), package_id, channel)

    # -- resolution --------------------------------------------------------

    def updates(
        self,
        database: db_mod.Database | None = None,
        *,
        channel: str = "stable",
        include_new: bool = True,
    ) -> list:
        """What could be installed or upgraded right now."""
        installed = database if database is not None else db_mod.Database(self.root)
        installed.load()
        document = self.load()
        plan = []
        # One candidate per package: the newest version this channel may use.
        for package_id in sorted({entry.id for entry in self.packages()}):
            entry = repo_mod.latest(document, package_id, channel)
            if entry is None:
                continue
            record = installed.get(entry.id)
            if record is None:
                if not include_new:
                    continue
                action = "install"
                current = None
            else:
                if semver.compare(entry.version, record.version) <= 0:
                    continue
                action = "update"
                current = record.version
            plan.append(
                Update(
                    package_id=entry.id,
                    current=current,
                    candidate=entry.version,
                    size=entry.size,
                    sha256=entry.sha256,
                    url=entry.url,
                    action=action,
                )
            )
        plan.sort(key=lambda update: (update.action != "update", update.package_id))
        return plan

    # -- download ----------------------------------------------------------

    def download(self, update: Update, destination: str | os.PathLike[str]) -> Path:
        """Fetch a package and verify size and digest before returning it."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = fetch(update.url)
        if len(payload) != update.size:
            raise PackageError(
                f"{update.package_id} {update.candidate} is {len(payload)} bytes, "
                f"the index promised {update.size}"
            )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != update.sha256:
            raise PackageError(
                f"{update.package_id} {update.candidate} failed its SHA-256 check: "
                f"expected {update.sha256}, got {digest}"
            )
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(payload)
        os.replace(partial, target)
        return target
