"""The update channel: what a machine accepts, and what it refuses.

The bundle applier is injected, so these tests exercise the real channel parsing,
the real checksum gate and the real state file, without upgrading the machine the
tests run on. The one rule that matters most is pinned here: an update never writes
inside a home directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UPDATE = REPO / "services" / "zaod-update" / "update.py"


@pytest.fixture()
def update(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("zaod_update", UPDATE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["zaod_update"] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    monkeypatch.setenv("ZAOD_UPDATE_STATE", str(tmp_path / "state" / "update-state.json"))
    module.STATE_PATH = tmp_path / "state" / "update-state.json"
    return module


def publish(tmp_path: Path, version: str = "0.4.3", payload: bytes = b"bundle-bytes") -> tuple[Path, Path]:
    """Write a bundle and the channel that points at it, like a release would."""
    bundle = tmp_path / "release" / f"zaod-{version}.zaodbundle"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(payload)
    channel = tmp_path / "release" / "channel.json"
    channel.write_text(
        json.dumps(
            {
                "format": 1,
                "version": version,
                "published": "2026-11-20T10:00:00Z",
                "summary": "Studio saves faster",
                "bundle": {
                    "url": bundle.resolve().as_uri(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                },
            }
        )
    )
    return channel, bundle


def test_the_channel_says_what_it_offers(update, tmp_path):
    channel, _bundle = publish(tmp_path)
    release, newer = update.check("0.4.2", channel.resolve().as_uri())
    assert release.version == "0.4.3"
    assert release.summary == "Studio saves faster"
    assert newer is True


def test_an_already_installed_version_is_not_newer(update, tmp_path):
    channel, _bundle = publish(tmp_path, version="0.4.3")
    _release, newer = update.check("0.4.3", channel.resolve().as_uri())
    assert newer is False


def test_a_bundle_that_does_not_match_its_checksum_is_refused(update, tmp_path):
    channel, bundle = publish(tmp_path)
    bundle.write_bytes(b"tampered")
    release, _newer = update.check("0.4.2", channel.resolve().as_uri())
    with pytest.raises(update.UpdateError, match="checksum"):
        update.download(release, tmp_path / "downloads")


def test_a_wrong_size_is_refused_even_with_the_right_hash(update, tmp_path):
    channel, _bundle = publish(tmp_path)
    document = json.loads(channel.read_text())
    document["bundle"]["size"] = 999
    channel.write_text(json.dumps(document))
    release, _newer = update.check("0.4.2", channel.resolve().as_uri())
    with pytest.raises(update.UpdateError, match="size"):
        update.download(release, tmp_path / "downloads")


def test_a_good_bundle_is_downloaded_and_applied_once(update, tmp_path):
    channel, bundle = publish(tmp_path)
    release, _newer = update.check("0.4.2", channel.resolve().as_uri())
    downloaded = update.download(release, tmp_path / "downloads")
    assert downloaded.read_bytes() == bundle.read_bytes()

    applied = []
    version = update.apply(release, downloaded, applied.append)
    assert applied == [downloaded]
    assert version == "0.4.3"
    state = json.loads(update.STATE_PATH.read_text())
    assert state["version"] == "0.4.3"
    assert state["summary"] == "Studio saves faster"
    assert update.installed_version() == "0.4.3"


def test_a_failed_apply_leaves_the_installed_version_alone(update, tmp_path):
    channel, _bundle = publish(tmp_path)
    release, _newer = update.check("0.4.2", channel.resolve().as_uri())
    update.record("0.4.2", release)

    def broken(_bundle):
        raise RuntimeError("the journal could not be written")

    with pytest.raises(update.UpdateError, match="could not be applied"):
        update.apply(release, tmp_path / "x.zaodbundle", broken)
    assert update.installed_version() == "0.4.2"


def test_a_channel_without_a_checksum_is_refused(update, tmp_path):
    channel, _bundle = publish(tmp_path)
    document = json.loads(channel.read_text())
    document["bundle"]["sha256"] = ""
    channel.write_text(json.dumps(document))
    with pytest.raises(update.UpdateError, match="sha256"):
        update.check("0.4.2", channel.resolve().as_uri())


def test_no_configured_channel_is_explained(update, tmp_path, monkeypatch):
    monkeypatch.delenv("ZAOD_UPDATE_CHANNEL", raising=False)
    monkeypatch.setattr(update, "CHANNEL_CONFIG", tmp_path / "missing.json")
    with pytest.raises(update.UpdateError, match="no update channel"):
        update.channel_url()


def test_an_update_never_writes_inside_the_home_directory(update, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "Documents" / "project.zaodproj").write_text("mine")
    monkeypatch.setenv("HOME", str(home))

    def snapshot() -> dict[str, float]:
        return {str(p): p.stat().st_mtime for p in home.rglob("*")}

    before = snapshot()
    channel, _bundle = publish(tmp_path)
    release, _newer = update.check("0.4.2", channel.resolve().as_uri())
    update.apply(release, update.download(release, tmp_path / "downloads"), lambda _b: None)
    assert snapshot() == before
    assert not list(home.rglob("*.zaodbundle"))
