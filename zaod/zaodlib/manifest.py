"""Manifest loading, validation and typed access for ``.zaod`` packages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import schema, util
from .errors import CompatibilityError, ManifestError

SPEC_DIRS = (
    Path(__file__).resolve().parent.parent / "spec",
    Path("/usr/share/zaod/spec"),
)

KINDS = ("app", "runtime", "theme", "project", "system-update")
FILESYSTEM_PERMISSIONS = ("home", "documents", "downloads", "music", "pictures", "videos", "desktop", "removable")
DEVICE_PERMISSIONS = ("dri", "audio", "input", "usb", "kvm")


def schema_path() -> Path:
    for directory in SPEC_DIRS:
        candidate = directory / "manifest.schema.json"
        if candidate.is_file():
            return candidate
    raise ManifestError("manifest schema not found; expected zaod/spec/manifest.schema.json")


def load_schema() -> dict:
    return json.loads(schema_path().read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Manifest:
    """Validated view over a manifest dictionary."""

    raw: dict
    path: Path | None = None
    canonical: bytes = field(default=b"", repr=False)

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def version(self) -> str:
        return self.raw["version"]

    @property
    def kind(self) -> str:
        return self.raw["kind"]

    @property
    def arch(self) -> str:
        return self.raw["arch"]

    @property
    def min_os(self) -> str:
        return self.raw["min_os"]

    @property
    def summary(self) -> str:
        return self.raw["summary"]

    @property
    def description(self) -> str:
        return self.raw.get("description", "")

    @property
    def license(self) -> dict:
        return self.raw["license"]

    @property
    def author(self) -> dict:
        return self.raw["author"]

    @property
    def categories(self) -> list[str]:
        return list(self.raw.get("categories", []))

    @property
    def entry(self) -> dict:
        return self.raw.get("entry", {})

    @property
    def icon(self) -> str:
        return self.raw.get("icon", "icon.svg")

    @property
    def screenshots(self) -> list[str]:
        return list(self.raw.get("screenshots", []))

    @property
    def permissions(self) -> dict:
        return self.raw.get("permissions", {})

    @property
    def runtimes(self) -> list[str]:
        return list(self.raw.get("runtimes", []))

    @property
    def associations(self) -> list[str]:
        return list(self.raw.get("associations", []))

    @property
    def network(self) -> bool:
        return bool(self.permissions.get("network", False))

    @property
    def filesystem_permissions(self) -> list[str]:
        return list(self.permissions.get("filesystem", []))

    @property
    def device_permissions(self) -> list[str]:
        return list(self.permissions.get("devices", []))

    def check_compatibility(self, os_version: str, arch: str = "x86_64") -> None:
        if self.arch != arch:
            raise CompatibilityError(f"{self.id}: built for {self.arch}, this system is {arch}")
        if util.compare_semver(self.min_os, os_version) > 0:
            raise CompatibilityError(
                f"{self.id} {self.version} needs Zaod OS {self.min_os} or newer, this system is {os_version}"
            )

    def desktop_summary(self) -> str:
        return self.summary


def parse_manifest(data: dict | str | bytes, path: Path | None = None) -> Manifest:
    if isinstance(data, (str, bytes)):
        text = data if isinstance(data, str) else data.decode("utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"MANIFEST.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"MANIFEST.json must contain a JSON object, got {type(data).__name__}")

    errors = schema.validate(data, load_schema())
    if errors:
        raise ManifestError("invalid manifest: " + "; ".join(errors))

    manifest = Manifest(raw=data, path=path, canonical=util.canonical_json(data))

    if manifest.kind in ("app", "project") and "entry" not in data:
        raise ManifestError(f"{manifest.id}: kind '{manifest.kind}' requires an entry.exec")
    for screenshot in manifest.screenshots:
        util.ensure_safe_relative(screenshot, "screenshots")
    if "icon" in data:
        util.ensure_safe_relative(manifest.icon, "icon")
    if manifest.entry:
        util.ensure_safe_relative(manifest.entry["exec"], "entry.exec")
    for runtime in manifest.runtimes:
        if runtime == manifest.id:
            raise ManifestError(f"{manifest.id}: an app cannot list itself as a runtime")
    return manifest


def load_manifest(path: Path) -> Manifest:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise ManifestError(f"manifest not found: {manifest_path}")
    try:
        raw = manifest_path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"cannot read {manifest_path}: {exc}") from exc
    return parse_manifest(raw, path=manifest_path)
