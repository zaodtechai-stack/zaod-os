"""The signed index and the store client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_source

from zaod import build as build_mod
from zaod import db, repo, signature, store
from zaod.errors import NetworkError, PackageError, SignatureError


def index_entry(package_id="os.zaod.notes", version="1.0.0", **overrides):
    entry = {
        "id": package_id,
        "version": version,
        "channel": "stable",
        "sha256": "a" * 64,
        "size": 1024,
        "url": f"file:///tmp/{package_id}-{version}.zaod",
        "permissions": ["network"],
    }
    entry.update(overrides)
    return entry


@pytest.fixture
def keypair():
    return signature.generate_keypair(seed=bytes(range(32)))


@pytest.fixture
def trust(tmp_path, keypair):
    _private, public = keypair
    store_dir = signature.TrustStore(tmp_path)
    store_dir.add(public)
    return store_dir


@pytest.fixture
def signed_index(tmp_path, keypair, trust):
    private, _public = keypair
    document = repo.build_index([index_entry(), index_entry(version="1.1.0")])
    signed = repo.sign_index(document, private)
    path = repo.write_index(signed, tmp_path / "index.json")
    return path


class TestIndexDocument:
    def test_build_sorts_by_id_and_version(self):
        document = repo.build_index(
            [index_entry(version="1.2.0"), index_entry(version="1.0.0")]
        )
        versions = [entry["version"] for entry in document["packages"]]
        assert versions == ["1.0.0", "1.2.0"]

    def test_build_sets_an_expiry(self):
        document = repo.build_index([index_entry()], ttl_days=7)
        assert document["expires"] > document["generated"]

    def test_signature_covers_the_body(self, keypair):
        private, _public = keypair
        signed = repo.sign_index(repo.build_index([index_entry()]), private)
        assert signed["signature"]["algorithm"] == "ed25519"
        assert len(signed["signature"]["value"]) == 128

    def test_canonical_excludes_the_signature(self, keypair):
        private, _public = keypair
        signed = repo.sign_index(repo.build_index([index_entry()]), private)
        assert b"signature" not in repo.canonical(signed)

    def test_verify_accepts_a_good_index(self, signed_index, trust):
        document = repo.verify_index(repo.read_index(signed_index), trust)
        assert document["repo"] == "zaod-main"

    def test_verify_rejects_a_tampered_entry(self, signed_index, trust):
        document = repo.read_index(signed_index)
        document["packages"][0]["size"] = 999_999
        with pytest.raises(SignatureError):
            repo.verify_index(document, trust)

    def test_verify_rejects_an_untrusted_key(self, signed_index, tmp_path):
        empty = signature.TrustStore(tmp_path / "empty")
        with pytest.raises(SignatureError):
            repo.verify_index(repo.read_index(signed_index), empty)

    def test_verify_rejects_an_expired_index(self, keypair, trust):
        private, _public = keypair
        old = datetime.now(UTC) - timedelta(days=90)
        signed = repo.sign_index(repo.build_index([index_entry()], generated=old, ttl_days=1), private)
        with pytest.raises(SignatureError):
            repo.verify_index(signed, trust)

    def test_verify_rejects_an_unsigned_index(self, trust):
        with pytest.raises(SignatureError):
            repo.verify_index(repo.build_index([index_entry()]), trust)

    def test_verify_rejects_an_invalid_digest(self, keypair, trust):
        private, _public = keypair
        document = repo.build_index([])
        document["packages"] = [index_entry(sha256="nothex")]
        signed = repo.sign_index(document, private)
        with pytest.raises(PackageError):
            repo.verify_index(signed, trust)

    def test_verify_rejects_an_unknown_channel(self, keypair, trust):
        private, _public = keypair
        document = repo.build_index([])
        document["packages"] = [index_entry(channel="nightly")]
        signed = repo.sign_index(document, private)
        with pytest.raises(PackageError):
            repo.verify_index(signed, trust)

    def test_latest_picks_the_highest_version(self, signed_index):
        document = repo.read_index(signed_index)
        assert repo.latest(document, "os.zaod.notes").version == "1.1.0"

    def test_latest_returns_none_for_an_absent_package(self, signed_index):
        assert repo.latest(repo.read_index(signed_index), "os.zaod.absent") is None

    def test_beta_channel_sees_stable_packages(self):
        document = repo.build_index(
            [index_entry(), index_entry(version="2.0.0", channel="beta")]
        )
        assert repo.latest(document, "os.zaod.notes", "beta").version == "2.0.0"
        assert repo.latest(document, "os.zaod.notes", "stable").version == "1.0.0"

    def test_channels_for_lists_both(self):
        document = repo.build_index(
            [index_entry(), index_entry(version="2.0.0", channel="beta")]
        )
        assert repo.channels_for(document, "os.zaod.notes") == ["beta", "stable"]


class TestStoreClient:
    def _store(self, tmp_path, signed_index, trust):
        client = store.Store(trust=trust, root=tmp_path / "root", url=f"file://{signed_index}")
        return client

    def test_refresh_reads_and_verifies(self, tmp_path, signed_index, trust):
        client = self._store(tmp_path, signed_index, trust)
        document = client.refresh()
        assert len(document["packages"]) == 2
        assert client.offline is False

    def test_refresh_caches_the_index(self, tmp_path, signed_index, trust):
        client = self._store(tmp_path, signed_index, trust)
        client.refresh()
        assert client.cache.load() is not None

    def test_offline_falls_back_to_the_cache(self, tmp_path, signed_index, trust):
        client = self._store(tmp_path, signed_index, trust)
        client.refresh()
        client.document = None
        client.url = f"file://{tmp_path / 'gone.json'}"
        document = client.load()
        assert client.offline is True
        assert len(document["packages"]) == 2

    def test_no_index_and_no_cache_raises(self, tmp_path, trust):
        client = store.Store(trust=trust, root=tmp_path / "root", url=f"file://{tmp_path / 'gone.json'}")
        with pytest.raises(NetworkError):
            client.load()

    def test_search_matches_substrings(self, tmp_path, signed_index, trust):
        client = self._store(tmp_path, signed_index, trust)
        assert len(client.search("notes")) == 2
        assert client.search("nothing") == []

    def test_updates_plans_an_install_for_absent_packages(self, tmp_path, signed_index, trust):
        client = self._store(tmp_path, signed_index, trust)
        plan = client.updates()
        assert [update.action for update in plan] == ["install"]

    def test_updates_plans_an_upgrade(self, tmp_path, signed_index, trust):
        root = tmp_path / "root"
        database = db.Database(root)
        database.load()
        database.put(
            db.InstalledPackage(
                id="os.zaod.notes",
                version="0.9.0",
                kind="app",
                name="Notes",
                installed_at="2026-01-01T00:00:00Z",
            )
        )
        database.save()
        client = store.Store(trust=trust, root=root, url=f"file://{signed_index}")
        plan = client.updates()
        assert plan[0].action == "update"
        assert (plan[0].current, plan[0].candidate) == ("0.9.0", "1.1.0")

    def test_updates_ignores_a_package_that_is_current(self, tmp_path, signed_index, trust):
        root = tmp_path / "root"
        database = db.Database(root)
        database.load()
        database.put(
            db.InstalledPackage(
                id="os.zaod.notes",
                version="1.1.0",
                kind="app",
                name="Notes",
                installed_at="2026-01-01T00:00:00Z",
            )
        )
        database.save()
        client = store.Store(trust=trust, root=root, url=f"file://{signed_index}")
        assert client.updates() == []

    def test_download_verifies_the_digest(self, tmp_path, trust):
        payload = b"signed package bytes"
        source = tmp_path / "pkg.zaod"
        source.write_bytes(payload)
        update = store.Update(
            package_id="os.zaod.notes",
            current=None,
            candidate="1.0.0",
            size=len(payload),
            sha256=__import__("hashlib").sha256(payload).hexdigest(),
            url=f"file://{source}",
            action="install",
        )
        client = store.Store(trust=trust, root=tmp_path / "root")
        target = client.download(update, tmp_path / "cache/pkg.zaod")
        assert target.read_bytes() == payload

    def test_download_rejects_a_bad_digest(self, tmp_path, trust):
        source = tmp_path / "pkg.zaod"
        source.write_bytes(b"tampered")
        update = store.Update(
            package_id="os.zaod.notes",
            current=None,
            candidate="1.0.0",
            size=8,
            sha256="b" * 64,
            url=f"file://{source}",
            action="install",
        )
        client = store.Store(trust=trust, root=tmp_path / "root")
        with pytest.raises(PackageError):
            client.download(update, tmp_path / "cache/pkg.zaod")

    def test_download_rejects_a_size_mismatch(self, tmp_path, trust):
        source = tmp_path / "pkg.zaod"
        source.write_bytes(b"short")
        update = store.Update(
            package_id="os.zaod.notes",
            current=None,
            candidate="1.0.0",
            size=999,
            sha256=__import__("hashlib").sha256(b"short").hexdigest(),
            url=f"file://{source}",
            action="install",
        )
        client = store.Store(trust=trust, root=tmp_path / "root")
        with pytest.raises(PackageError):
            client.download(update, tmp_path / "cache/pkg.zaod")

    def test_unsupported_scheme_is_refused(self, tmp_path, trust):
        client = store.Store(trust=trust, root=tmp_path / "root", url="ftp://example.invalid/index.json")
        with pytest.raises(NetworkError):
            client.refresh()

    def test_a_real_package_can_be_indexed_and_downloaded(self, tmp_path, trust, keypair):
        private, _public = keypair
        source = make_source(tmp_path / "src")
        package = build_mod.build_package(source, tmp_path / "notes.zaod", private_key=private)
        payload = package.read_bytes()
        digest = __import__("hashlib").sha256(payload).hexdigest()
        document = repo.build_index(
            [index_entry(sha256=digest, size=len(payload), url=f"file://{package}")]
        )
        signed = repo.sign_index(document, private)
        path = repo.write_index(signed, tmp_path / "index.json")

        client = store.Store(trust=trust, root=tmp_path / "root", url=f"file://{path}")
        plan = client.updates()
        assert plan[0].package_id == "os.zaod.notes"
        fetched = client.download(plan[0], tmp_path / "cache/notes.zaod")
        assert fetched.read_bytes() == payload
