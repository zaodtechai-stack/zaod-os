"""Shared fixtures for the ``zaod`` test suite."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from zaod import build as build_mod
from zaod import signature as signature_mod


def manifest_document(**overrides) -> dict:
    document = {
        "format": 1,
        "id": "os.zaod.notes",
        "name": "Notes",
        "version": "1.0.0",
        "kind": "app",
        "arch": "x86_64",
        "min_os": "1.0.0",
        "description": "A small notes application for testing.",
        "license": "GPL-3.0-or-later",
        "author": {"name": "Zaod", "email": "dev@zaod.os"},
        "entry": {"exec": "payload/notes"},
        "permissions": {"network": False},
    }
    document.update(overrides)
    return document


def make_source(
    directory: Path,
    *,
    files: dict | None = None,
    manifest: dict | None = None,
    icon: bool = True,
) -> Path:
    """Write a package source tree and return its root."""
    directory.mkdir(parents=True, exist_ok=True)
    document = manifest or manifest_document()
    (directory / "MANIFEST.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    payload = directory / "payload"
    payload.mkdir(exist_ok=True)
    for name, content in (files or {"notes": "#!/bin/sh\necho notes\n"}).items():
        target = payload / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        target.chmod(0o755)
    if icon:
        (directory / "icon.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"/>\n', encoding="utf-8"
        )
    return directory


@pytest.fixture
def signing_key() -> tuple:
    return signature_mod.generate_keypair(seed=bytes(range(32)))


@pytest.fixture
def trust_store(tmp_path, signing_key):
    _private, public = signing_key
    store = signature_mod.TrustStore(tmp_path)
    store.add(public)
    return store


@pytest.fixture
def signed_package(tmp_path, signing_key) -> Path:
    private, _public = signing_key
    source = make_source(tmp_path / "source")
    output = tmp_path / "notes-1.0.0.zaod"
    return build_mod.build_package(source, output, private_key=private)


@pytest.fixture
def unsigned_package(tmp_path) -> Path:
    source = make_source(tmp_path / "source-unsigned")
    output = tmp_path / "notes-unsigned.zaod"
    return build_mod.build_package(source, output)


@pytest.fixture
def target_root(tmp_path) -> Path:
    root = tmp_path / "root"
    (root / "etc/zaod").mkdir(parents=True)
    (root / "etc/zaod/os-version").write_text("1.0.0\n", encoding="utf-8")
    return root
