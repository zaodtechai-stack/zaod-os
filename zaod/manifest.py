"""Manifest (``MANIFEST.json``) loading and validation for `.zaod` format v1.

The normative description lives in ``docs/zaod-format-v1.md``; the machine
readable form is ``zaod/spec/manifest.schema.json``. This module is the
authority the CLI actually enforces, and it is deliberately *stricter* than a
generic JSON Schema validator would be:

* unknown top-level keys are rejected, so a package cannot smuggle settings;
* types are checked exactly (a string where a list is expected is an error,
  never coerced);
* identifiers, versions, paths, exec targets and permissions are validated
  against closed grammars.

Validation collects **all** problems instead of stopping at the first, because
the Phase 9 Studio requirement is that an invalid manifest "provides precise
error and produces no package".
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from . import semver
from .errors import ManifestError, SemverError

__all__ = [
    "ARCHES",
    "CATEGORIES",
    "DEVICES",
    "FORMAT_VERSION",
    "KINDS",
    "MANIFEST_NAME",
    "PERMISSION_KEYS",
    "Author",
    "Entry",
    "Manifest",
    "Permissions",
    "RuntimeDep",
    "dumps",
    "load",
    "loads",
    "validate_document",
]

#: Only format version 1 exists; a future major bump must be rejected by old CLIs.
FORMAT_VERSION = 1

#: ``kind`` values from PRD section 10.
KINDS = ("app", "runtime", "theme", "project", "system-update")

#: v1 ships exactly one architecture (PRD section 3, "no ARM/RISC-V/32-bit").
ARCHES = ("x86_64",)

#: Closed set of permission switches. Anything else is a schema error so that
#: a package cannot ask for a permission the sandbox implementation ignores.
PERMISSION_KEYS = (
    "network",
    "audio",
    "session_bus",
    "system_bus",
    "home_read",
    "home_write",
    "paths_ro",
    "paths_rw",
    "devices",
)

#: Device classes a package may request inside the sandbox.
DEVICES = ("dri", "input", "alsa", "usb")

#: Freedesktop main categories accepted in ``categories``.
CATEGORIES = (
    "AudioVideo",
    "Audio",
    "Video",
    "Development",
    "Education",
    "Game",
    "Graphics",
    "Network",
    "Office",
    "Science",
    "Settings",
    "System",
    "Utility",
)

MANIFEST_NAME = "MANIFEST.json"

# Reverse-DNS identifier: at least two dot-separated labels, lowercase ASCII
# alphanumerics and hyphens, each label starting with a letter; total <= 128.
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}(?:\.[a-z][a-z0-9-]{0,62})+$")
# A payload-relative POSIX path: no absolute paths, no "." / ".." components,
# no backslashes, no empty components, no NUL.
_PATH_RE = re.compile(r"^[A-Za-z0-9._+@-][A-Za-z0-9._+@/-]*$")
_SCREENSHOT_RE = re.compile(r"^screenshots/[A-Za-z0-9._-]+\.(?:png|jpg|jpeg|webp)$")
_ICON_RE = re.compile(r"^icon\.(?:svg|png)$")
_MIME_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MAX_ID_LENGTH = 128
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 2000
MAX_CATEGORIES = 8
MAX_RUNTIMES = 24
MAX_SCREENSHOTS = 12
MAX_ENTRY_ARGS = 32
MAX_ARG_LENGTH = 1024
MAX_PATH_LENGTH = 256


@dataclass(frozen=True)
class Author:
    """``author`` object from the manifest."""

    name: str
    email: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name}
        if self.email:
            data["email"] = self.email
        if self.url:
            data["url"] = self.url
        return data


@dataclass(frozen=True)
class Entry:
    """``entry``: what ``zaod run`` launches.

    ``exec`` is a path relative to the archive root, normally under
    ``payload/``. It is never a shell command line: arguments go in ``args``
    and are passed as an argv vector, so no shell metacharacter is interpreted.
    """

    exec: str
    args: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"exec": self.exec}
        if self.args:
            data["args"] = list(self.args)
        return data


@dataclass(frozen=True)
class Permissions:
    """Sandbox permissions requested by the package.

    Defaults are "nothing": no network, no buses, no device nodes, no access
    to the user's home. This matches PRD section 11's "bubblewrap is default
    least privilege".
    """

    network: bool = False
    audio: bool = False
    session_bus: bool = False
    system_bus: bool = False
    home_read: bool = False
    home_write: bool = False
    paths_ro: tuple[str, ...] = ()
    paths_rw: tuple[str, ...] = ()
    devices: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "network": self.network,
            "audio": self.audio,
            "session_bus": self.session_bus,
            "system_bus": self.system_bus,
            "home_read": self.home_read,
            "home_write": self.home_write,
            "paths_ro": list(self.paths_ro),
            "paths_rw": list(self.paths_rw),
            "devices": list(self.devices),
        }

    def summary(self) -> str:
        """Human sentence used by ``zaod info`` and the install confirmation."""
        parts: list[str] = []
        parts.append("network access" if self.network else "no network")
        if self.home_write:
            parts.append("read/write your home folder")
        elif self.home_read:
            parts.append("read your home folder")
        else:
            parts.append("isolated home")
        if self.session_bus:
            parts.append("session bus")
        if self.system_bus:
            parts.append("system bus")
        if self.audio:
            parts.append("audio")
        if self.devices:
            parts.append("devices: " + ", ".join(self.devices))
        if self.paths_ro:
            parts.append("read: " + ", ".join(self.paths_ro))
        if self.paths_rw:
            parts.append("write: " + ", ".join(self.paths_rw))
        return "; ".join(parts)


@dataclass(frozen=True)
class RuntimeDep:
    """A shared runtime dependency, e.g. ``org.zaod.python-runtime >=3.12``."""

    id: str
    version: str = "*"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class Manifest:
    """A fully validated manifest."""

    format: int
    id: str
    name: str
    version: str
    kind: str
    arch: str
    min_os: str
    description: str
    license: str
    author: Author
    entry: Entry
    categories: tuple[str, ...] = ()
    runtimes: tuple[RuntimeDep, ...] = ()
    permissions: Permissions = field(default_factory=Permissions)
    icon: str = "icon.svg"
    screenshots: tuple[str, ...] = ()
    mime_types: tuple[str, ...] = ()
    homepage: str | None = None

    # -- derived helpers ---------------------------------------------------

    @property
    def version_obj(self) -> semver.Version:
        return semver.parse(self.version)

    @property
    def min_os_obj(self) -> semver.Version:
        return semver.parse(self.min_os)

    @property
    def has_payload(self) -> bool:
        return self.kind != "theme"

    def to_dict(self) -> dict[str, Any]:
        """Canonical manifest dictionary (stable key order, no nulls)."""
        data: dict[str, Any] = {
            "format": self.format,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "arch": self.arch,
            "min_os": self.min_os,
            "description": self.description,
            "license": self.license,
            "author": self.author.to_dict(),
            "entry": self.entry.to_dict(),
            "icon": self.icon,
        }
        if self.categories:
            data["categories"] = list(self.categories)
        if self.runtimes:
            data["runtimes"] = [dep.to_dict() for dep in self.runtimes]
        if self.screenshots:
            data["screenshots"] = list(self.screenshots)
        if self.mime_types:
            data["mime_types"] = list(self.mime_types)
        if self.homepage:
            data["homepage"] = self.homepage
        data["permissions"] = self.permissions.to_dict()
        return data

    def canonical_bytes(self) -> bytes:
        """Deterministic JSON encoding used for signing and checksums.

        Two-space indent, sorted keys, UTF-8, trailing newline. ``zaod pack``
        always writes MANIFEST.json in exactly this form, so a signature over
        the manifest bytes is reproducible byte-for-byte.
        """
        return (json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )


# --- validation helpers -----------------------------------------------------


class _Problems:
    """Collects validation failures with a JSON-ish path prefix."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, path: str, message: str) -> None:
        self.items.append(f"{path}: {message}" if path else message)

    def raise_if_any(self) -> None:
        if self.items:
            joined = "; ".join(self.items)
            raise ManifestError(
                f"invalid manifest ({len(self.items)} problem"
                f"{'s' if len(self.items) != 1 else ''}): {joined}"
            )


def _expect_object(value: Any, path: str, problems: _Problems, allowed: tuple[str, ...]) -> dict:
    if not isinstance(value, Mapping):
        problems.add(path, f"must be an object, got {_type_name(value)}")
        return {}
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        problems.add(path, f"unknown key(s): {', '.join(unknown)}")
    return dict(value)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _expect_string(
    container: Mapping,
    key: str,
    path: str,
    problems: _Problems,
    *,
    required: bool = True,
    max_length: int | None = None,
    min_length: int = 1,
) -> str | None:
    if key not in container:
        if required:
            problems.add(f"{path}.{key}", "is required")
        return None
    value = container[key]
    if not isinstance(value, str):
        problems.add(f"{path}.{key}", f"must be a string, got {_type_name(value)}")
        return None
    if len(value) < min_length:
        problems.add(f"{path}.{key}", f"must not be shorter than {min_length} characters")
        return None
    if max_length is not None and len(value) > max_length:
        problems.add(f"{path}.{key}", f"must not be longer than {max_length} characters")
        return None
    if any(ord(char) < 0x20 for char in value):
        problems.add(f"{path}.{key}", "must not contain control characters")
        return None
    return value


def _expect_bool(container: Mapping, key: str, path: str, problems: _Problems) -> bool:
    value = container.get(key, False)
    if not isinstance(value, bool):
        problems.add(f"{path}.{key}", f"must be a boolean, got {_type_name(value)}")
        return False
    return value


def _validate_relative_path(value: str, path: str, problems: _Problems, *, prefix: str | None = None) -> bool:
    if len(value) > MAX_PATH_LENGTH:
        problems.add(path, f"path is longer than {MAX_PATH_LENGTH} characters")
        return False
    if value.startswith("/"):
        problems.add(path, "must be relative to the archive root, not absolute")
        return False
    if "\\" in value:
        problems.add(path, "must use forward slashes")
        return False
    components = value.split("/")
    if any(component in ("", ".", "..") for component in components):
        problems.add(path, "must not contain empty, '.' or '..' components")
        return False
    if not _PATH_RE.match(value):
        problems.add(path, "contains characters that are not allowed in a payload path")
        return False
    if prefix is not None and not value.startswith(prefix):
        problems.add(path, f"must start with {prefix!r}")
        return False
    return True


def _validate_permissions(value: Any, path: str, problems: _Problems) -> Permissions:
    if value is None:
        return Permissions()
    data = _expect_object(value, path, problems, PERMISSION_KEYS)
    if not data:
        return Permissions()

    def path_list(key: str) -> tuple[str, ...]:
        raw = data.get(key, [])
        if raw is None:
            return ()
        if not isinstance(raw, list):
            problems.add(f"{path}.{key}", f"must be an array of strings, got {_type_name(raw)}")
            return ()
        result: list[str] = []
        for index, item in enumerate(raw):
            item_path = f"{path}.{key}[{index}]"
            if not isinstance(item, str):
                problems.add(item_path, f"must be a string, got {_type_name(item)}")
                continue
            if not item.startswith("/"):
                problems.add(item_path, "must be an absolute sandbox path (e.g. /usr/share/fonts)")
                continue
            if ".." in item.split("/"):
                problems.add(item_path, "must not contain '..'")
                continue
            if item in ("/", "/etc", "/home", "/root", "/var", "/zaod"):
                problems.add(item_path, f"{item} is not an allowed host path to bind")
                continue
            result.append(item)
        if len(result) > 32:
            problems.add(f"{path}.{key}", "at most 32 paths may be requested")
        return tuple(result)

    devices_raw = data.get("devices", [])
    devices: tuple[str, ...] = ()
    if devices_raw is not None:
        if not isinstance(devices_raw, list):
            problems.add(f"{path}.devices", f"must be an array, got {_type_name(devices_raw)}")
        else:
            validated = []
            for index, device in enumerate(devices_raw):
                if not isinstance(device, str):
                    problems.add(f"{path}.devices[{index}]", "must be a string")
                    continue
                if device not in DEVICES:
                    problems.add(
                        f"{path}.devices[{index}]",
                        f"unknown device class {device!r} (allowed: {', '.join(DEVICES)})",
                    )
                    continue
                validated.append(device)
            devices = tuple(dict.fromkeys(validated))

    return Permissions(
        network=_expect_bool(data, "network", path, problems),
        audio=_expect_bool(data, "audio", path, problems),
        session_bus=_expect_bool(data, "session_bus", path, problems),
        system_bus=_expect_bool(data, "system_bus", path, problems),
        home_read=_expect_bool(data, "home_read", path, problems),
        home_write=_expect_bool(data, "home_write", path, problems),
        paths_ro=path_list("paths_ro"),
        paths_rw=path_list("paths_rw"),
        devices=devices,
    )


_TOP_LEVEL_KEYS = (
    "format",
    "id",
    "name",
    "version",
    "kind",
    "arch",
    "min_os",
    "description",
    "license",
    "author",
    "entry",
    "categories",
    "runtimes",
    "permissions",
    "icon",
    "screenshots",
    "mime_types",
    "homepage",
)


def validate_document(document: Any) -> Manifest:
    """Validate a parsed JSON document and return a :class:`Manifest`.

    Raises :class:`ManifestError` listing every problem found.
    """
    problems = _Problems()
    data = _expect_object(document, "", problems, _TOP_LEVEL_KEYS)
    if not data:
        problems.raise_if_any()
        raise ManifestError("invalid manifest: expected a JSON object")

    raw_format = data.get("format")
    if "format" not in data:
        problems.add("format", "is required")
    elif isinstance(raw_format, bool) or not isinstance(raw_format, int):
        problems.add("format", f"must be an integer, got {_type_name(raw_format)}")
    elif raw_format != FORMAT_VERSION:
        problems.add(
            "format",
            f"unsupported format version {raw_format}; this zaod supports {FORMAT_VERSION}",
        )

    identifier = _expect_string(data, "id", "", problems, max_length=MAX_ID_LENGTH)
    if identifier is not None and not _ID_RE.match(identifier):
        problems.add(
            "id",
            "must be a reverse-DNS identifier such as 'org.zaod.hello' "
            "(lowercase letters, digits, hyphens, at least two dot-separated labels)",
        )

    name = _expect_string(data, "name", "", problems, max_length=MAX_NAME_LENGTH)

    version = _expect_string(data, "version", "", problems, max_length=64)
    if version is not None:
        try:
            semver.parse(version)
        except SemverError as exc:
            problems.add("version", str(exc))

    kind = _expect_string(data, "kind", "", problems)
    if kind is not None and kind not in KINDS:
        problems.add("kind", f"must be one of: {', '.join(KINDS)}")

    arch = _expect_string(data, "arch", "", problems)
    if arch is not None and arch not in ARCHES:
        problems.add("arch", f"must be one of: {', '.join(ARCHES)}")

    min_os = _expect_string(data, "min_os", "", problems, max_length=64)
    if min_os is not None:
        try:
            semver.parse(min_os)
        except SemverError as exc:
            problems.add("min_os", str(exc))

    description = _expect_string(
        data, "description", "", problems, max_length=MAX_DESCRIPTION_LENGTH
    )
    license_text = _expect_string(data, "license", "", problems, max_length=200)

    author_data = data.get("author")
    author: Author | None = None
    if author_data is None:
        problems.add("author", "is required")
    else:
        author_obj = _expect_object(author_data, "author", problems, ("name", "email", "url"))
        author_name = _expect_string(author_obj, "name", "author", problems, max_length=128)
        author_email = _expect_string(
            author_obj, "email", "author", problems, required=False, max_length=254
        )
        author_url = _expect_string(
            author_obj, "url", "author", problems, required=False, max_length=512
        )
        if author_email is not None and not _EMAIL_RE.match(author_email):
            problems.add("author.email", "is not a valid e-mail address")
        if author_url is not None and not author_url.startswith(("https://", "http://")):
            problems.add("author.url", "must be an http(s) URL")
        if author_name is not None:
            author = Author(name=author_name, email=author_email, url=author_url)

    entry_data = data.get("entry")
    entry: Entry | None = None
    if entry_data is None:
        problems.add("entry", "is required")
    else:
        entry_obj = _expect_object(entry_data, "entry", problems, ("exec", "args"))
        exec_path = _expect_string(entry_obj, "exec", "entry", problems, max_length=MAX_PATH_LENGTH)
        args: tuple[str, ...] = ()
        if (
            exec_path is not None
            and _validate_relative_path(exec_path, "entry.exec", problems)
            and not exec_path.startswith("payload/")
        ):
            problems.add("entry.exec", "must point inside 'payload/'")
        raw_args = entry_obj.get("args", [])
        if raw_args is None:
            raw_args = []
        if not isinstance(raw_args, list):
            problems.add("entry.args", f"must be an array of strings, got {_type_name(raw_args)}")
        else:
            if len(raw_args) > MAX_ENTRY_ARGS:
                problems.add("entry.args", f"at most {MAX_ENTRY_ARGS} arguments are allowed")
            checked: list[str] = []
            for index, arg in enumerate(raw_args):
                if not isinstance(arg, str):
                    problems.add(f"entry.args[{index}]", f"must be a string, got {_type_name(arg)}")
                    continue
                if len(arg) > MAX_ARG_LENGTH:
                    problems.add(f"entry.args[{index}]", f"longer than {MAX_ARG_LENGTH} characters")
                    continue
                if "\x00" in arg:
                    problems.add(f"entry.args[{index}]", "must not contain NUL")
                    continue
                checked.append(arg)
            args = tuple(checked)
        if exec_path is not None:
            entry = Entry(exec=exec_path, args=args)

    categories: tuple[str, ...] = ()
    raw_categories = data.get("categories")
    if raw_categories is not None:
        if not isinstance(raw_categories, list):
            problems.add("categories", f"must be an array, got {_type_name(raw_categories)}")
        else:
            if len(raw_categories) > MAX_CATEGORIES:
                problems.add("categories", f"at most {MAX_CATEGORIES} categories are allowed")
            collected: list[str] = []
            for index, category in enumerate(raw_categories):
                if not isinstance(category, str):
                    problems.add(f"categories[{index}]", "must be a string")
                    continue
                if category not in CATEGORIES:
                    problems.add(
                        f"categories[{index}]",
                        f"unknown category {category!r} (allowed: {', '.join(CATEGORIES)})",
                    )
                    continue
                collected.append(category)
            categories = tuple(dict.fromkeys(collected))

    runtimes: tuple[RuntimeDep, ...] = ()
    raw_runtimes = data.get("runtimes")
    if raw_runtimes is not None:
        if not isinstance(raw_runtimes, list):
            problems.add("runtimes", f"must be an array, got {_type_name(raw_runtimes)}")
        else:
            if len(raw_runtimes) > MAX_RUNTIMES:
                problems.add("runtimes", f"at most {MAX_RUNTIMES} runtime dependencies are allowed")
            deps: list[RuntimeDep] = []
            for index, item in enumerate(raw_runtimes):
                item_path = f"runtimes[{index}]"
                if isinstance(item, str):
                    runtime_id, _, constraint = item.partition(" ")
                    constraint = constraint.strip() or "*"
                else:
                    obj = _expect_object(item, item_path, problems, ("id", "version"))
                    runtime_id = _expect_string(obj, "id", item_path, problems)
                    constraint = _expect_string(
                        obj, "version", item_path, problems, required=False, max_length=64
                    ) or "*"
                    if runtime_id is None:
                        continue
                if runtime_id is not None and not _ID_RE.match(runtime_id):
                    problems.add(f"{item_path}.id", "must be a reverse-DNS identifier")
                    continue
                try:
                    semver.satisfies("0.0.0", constraint)
                except SemverError as exc:
                    problems.add(f"{item_path}.version", str(exc))
                    continue
                if runtime_id is not None:
                    deps.append(RuntimeDep(id=runtime_id, version=constraint))
            runtimes = tuple(deps)

    permissions = _validate_permissions(data.get("permissions"), "permissions", problems)

    icon = _expect_string(data, "icon", "", problems, required=False, max_length=64) or "icon.svg"
    if not _ICON_RE.match(icon):
        problems.add("icon", "must be 'icon.svg' or 'icon.png'")

    screenshots: tuple[str, ...] = ()
    raw_screenshots = data.get("screenshots")
    if raw_screenshots is not None:
        if not isinstance(raw_screenshots, list):
            problems.add("screenshots", f"must be an array, got {_type_name(raw_screenshots)}")
        else:
            if len(raw_screenshots) > MAX_SCREENSHOTS:
                problems.add("screenshots", f"at most {MAX_SCREENSHOTS} screenshots are allowed")
            shots: list[str] = []
            for index, shot in enumerate(raw_screenshots):
                if not isinstance(shot, str):
                    problems.add(f"screenshots[{index}]", "must be a string")
                    continue
                if not _SCREENSHOT_RE.match(shot):
                    problems.add(
                        f"screenshots[{index}]",
                        "must be 'screenshots/<name>.(png|jpg|jpeg|webp)'",
                    )
                    continue
                shots.append(shot)
            screenshots = tuple(shots)

    mime_types: tuple[str, ...] = ()
    raw_mime = data.get("mime_types")
    if raw_mime is not None:
        if not isinstance(raw_mime, list):
            problems.add("mime_types", f"must be an array, got {_type_name(raw_mime)}")
        else:
            types: list[str] = []
            for index, mime in enumerate(raw_mime):
                if not isinstance(mime, str) or not _MIME_RE.match(mime):
                    problems.add(f"mime_types[{index}]", "must look like 'type/subtype'")
                    continue
                types.append(mime)
            mime_types = tuple(dict.fromkeys(types))

    homepage = _expect_string(data, "homepage", "", problems, required=False, max_length=512)
    if homepage is not None and not homepage.startswith(("https://", "http://")):
        problems.add("homepage", "must be an http(s) URL")

    problems.raise_if_any()

    assert identifier and name and version and kind and arch and min_os
    assert description and license_text and author and entry
    return Manifest(
        format=FORMAT_VERSION,
        id=identifier,
        name=name,
        version=version,
        kind=kind,
        arch=arch,
        min_os=min_os,
        description=description,
        license=license_text,
        author=author,
        entry=entry,
        categories=categories,
        runtimes=runtimes,
        permissions=permissions,
        icon=icon,
        screenshots=screenshots,
        mime_types=mime_types,
        homepage=homepage,
    )


def loads(raw: bytes | str) -> Manifest:
    """Parse and validate raw ``MANIFEST.json`` bytes."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManifestError(f"MANIFEST.json is not valid UTF-8: {exc}") from exc
    else:
        text = raw
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"MANIFEST.json is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"
        ) from exc
    return validate_document(document)


def load(path: str | os.PathLike[str]) -> Manifest:
    """Load and validate a ``MANIFEST.json`` file from disk."""
    try:
        with open(os.fspath(path), "rb") as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    return loads(raw)


def dumps(manifest: Manifest) -> bytes:
    """Serialise a manifest in the canonical (signable) form."""
    return manifest.canonical_bytes()
