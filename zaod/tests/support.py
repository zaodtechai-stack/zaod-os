"""Shared fixtures for the Zaod package manager test suite."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_LIB = Path(__file__).resolve().parents[1]
if str(REPO_LIB) not in sys.path:
    sys.path.insert(0, str(REPO_LIB))

from zaodlib import keys, pack
from zaodlib.errors import ZaodError
from zaodlib.paths import Paths

DEFAULT_ENTRY = "payload/bin/hello"


def make_paths(tmp: Path, *, trust: bytes | None = None, os_version: str | None = None) -> Paths:
    root = tmp / "root"
    paths = Paths(root=root, home=tmp / "home")
    paths.apps_dir.mkdir(parents=True, exist_ok=True)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.keys_dir.mkdir(parents=True, exist_ok=True)
    if trust is not None:
        keys.trust_public_key(paths.keys_dir, trust)
    if os_version is not None:
        paths.os_release.parent.mkdir(parents=True, exist_ok=True)
        paths.os_release.write_text(f'ID=zaod\nVERSION_ID="{os_version}"\n', encoding="utf-8")
    return paths


def manifest_dict(app_id: str = "org.zaod.hello", version: str = "1.0.0", **overrides) -> dict:
    manifest = {
        "format": 1,
        "id": app_id,
        "name": "Hello",
        "version": version,
        "kind": "app",
        "arch": "x86_64",
        "min_os": "0.7.0",
        "summary": "Tiny hello world app used by the test suite",
        "description": "Prints a greeting and shows that desktop integration works.",
        "categories": ["Utility"],
        "license": {"spdx": "MIT", "name": "MIT License"},
        "author": {"name": "Zaod Tests"},
        "entry": {"exec": DEFAULT_ENTRY, "args": [], "terminal": True},
        "icon": "icon.svg",
        "permissions": {"network": False, "filesystem": ["documents"], "devices": []},
    }
    manifest.update(overrides)
    return manifest


def make_app_source(
    tmp: Path,
    app_id: str = "org.zaod.hello",
    version: str = "1.0.0",
    *,
    name: str = "hello",
    manifest_overrides: dict | None = None,
) -> Path:
    source = tmp / f"src-{name}-{version}"
    payload = source / "payload" / "bin"
    payload.mkdir(parents=True, exist_ok=True)
    script = payload / "hello"
    script.write_text("#!/bin/sh\necho hello from zaod\n", encoding="utf-8")
    script.chmod(0o755)
    (source / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"/>\n', encoding="utf-8")
    manifest = manifest_dict(app_id, version, **(manifest_overrides or {}))
    (source / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return source


def make_package(tmp: Path, *, key: keys.KeyPair | None = None, name: str = "hello", **kwargs) -> Path:
    source = make_app_source(tmp, name=name, **kwargs)
    key_path = None
    if key is not None:
        key_path = tmp / f"{name}.key"
        key_path.write_text(key.export_private(), encoding="utf-8")
    output = tmp / f"{name}.zaod"
    pack.build_package(source, output, private_key=key_path, level=3)
    return output


def expect_error(testcase, error_type, callable_obj, *args, **kwargs):
    try:
        callable_obj(*args, **kwargs)
    except ZaodError as error:
        testcase.assertIsInstance(error, error_type, f"unexpected error: {error}")
        return error
    testcase.fail(f"expected {error_type.__name__} but no error was raised")
    return None


def corrupt_payload(package: Path, work: Path) -> Path:
    """Rebuild ``package`` with one payload byte changed and stale CHECKSUMS."""
    from zaodlib import archive

    staging = work / "corrupt"
    archive.extract_tree(package, staging)
    target = staging / DEFAULT_ENTRY
    target.write_text("#!/bin/sh\necho tampered\n", encoding="utf-8")
    archive.compress_tree(staging, package)
    return package
