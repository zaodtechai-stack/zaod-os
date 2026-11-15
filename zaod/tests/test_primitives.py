"""Version, manifest and checksum primitives."""

from __future__ import annotations

import pytest
from conftest import manifest_document

from zaod import checksums, manifest, semver
from zaod.errors import ChecksumError, ManifestError, SemverError


class TestSemver:
    def test_parses_a_release(self):
        parsed = semver.parse("1.2.3")
        assert (parsed.major, parsed.minor, parsed.patch) == (1, 2, 3)
        assert not parsed.is_prerelease

    def test_parses_a_prerelease(self):
        assert semver.parse("1.2.3-rc.1").is_prerelease

    def test_str_round_trips(self):
        for text in ("0.0.0", "1.2.3", "10.20.30-beta.2"):
            assert str(semver.parse(text)) == text

    @pytest.mark.parametrize("text", ["1.2", "1", "01.2.3", "1.2.3-", "v1.2.3", "", "1.2.3.4"])
    def test_rejects_invalid(self, text):
        with pytest.raises(SemverError):
            semver.parse(text)

    def test_ordering(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-beta", "1.0.0-rc.1", "1.0.0", "1.0.1"]
        assert sorted(ordered, key=semver.parse) == ordered

    def test_build_metadata_does_not_change_precedence(self):
        assert semver.parse("1.0.0+build.5") == semver.parse("1.0.0")

    def test_compare_returns_sign(self):
        assert semver.compare("2.0.0", "1.9.9") > 0
        assert semver.compare("1.9.9", "2.0.0") < 0
        assert semver.compare("1.0.0", "1.0.0") == 0

    def test_caret_constraint(self):
        assert semver.satisfies("1.4.2", "^1.2.0")
        assert not semver.satisfies("2.0.0", "^1.2.0")

    def test_exact_constraint(self):
        assert semver.satisfies("1.2.3", "=1.2.3")
        assert not semver.satisfies("1.2.4", "=1.2.3")


class TestManifest:
    def test_accepts_a_minimal_document(self):
        parsed = manifest.validate_document(manifest_document())
        assert parsed.id == "os.zaod.notes"
        assert parsed.icon == "icon.svg"

    def test_rejects_an_absolute_entry(self):
        document = manifest_document(entry={"exec": "/usr/bin/notes"})
        with pytest.raises(ManifestError):
            manifest.validate_document(document)

    def test_rejects_traversal_in_entry(self):
        document = manifest_document(entry={"exec": "payload/../../escape"})
        with pytest.raises(ManifestError):
            manifest.validate_document(document)

    def test_rejects_an_unknown_top_level_key(self):
        document = manifest_document()
        document["surprise"] = True
        with pytest.raises(ManifestError):
            manifest.validate_document(document)

    def test_rejects_a_bad_identifier(self):
        with pytest.raises(ManifestError):
            manifest.validate_document(manifest_document(id="Notes"))

    def test_rejects_an_unknown_kind(self):
        with pytest.raises(ManifestError):
            manifest.validate_document(manifest_document(kind="library"))

    def test_rejects_an_unknown_permission(self):
        with pytest.raises(ManifestError):
            manifest.validate_document(manifest_document(permissions={"telepathy": True}))

    def test_canonical_bytes_are_stable_and_sorted(self):
        parsed = manifest.validate_document(manifest_document())
        first = parsed.canonical_bytes()
        second = manifest.loads(first.decode()).canonical_bytes()
        assert first == second
        assert first.startswith(b"{\n  \"arch\"")

    def test_round_trip_through_loads(self):
        parsed = manifest.validate_document(manifest_document())
        again = manifest.loads(parsed.canonical_bytes())
        assert again.to_dict() == parsed.to_dict()

    def test_permission_summary_is_human_readable(self):
        parsed = manifest.validate_document(manifest_document())
        assert isinstance(parsed.permissions.summary(), str)
        assert parsed.permissions.summary()


class TestChecksums:
    def test_round_trip(self):
        entries = [
            checksums.ChecksumEntry(path="payload/b", size=2, sha256="b" * 64),
            checksums.ChecksumEntry(path="payload/a", size=1, sha256="a" * 64),
        ]
        formatted = checksums.format_checksums(entries)
        parsed = checksums.parse_checksums(formatted)
        assert [entry.path for entry in parsed] == ["payload/a", "payload/b"]

    def test_format_is_sorted(self):
        entries = [
            checksums.ChecksumEntry(path="payload/z", size=1, sha256="0" * 64),
            checksums.ChecksumEntry(path="payload/a", size=1, sha256="0" * 64),
        ]
        lines = checksums.format_checksums(entries).decode().strip().splitlines()
        assert lines[0].endswith("payload/a")

    def test_rejects_a_malformed_line(self):
        with pytest.raises(ChecksumError):
            checksums.parse_checksums("sha256:nothex 1 payload/a\n")

    def test_rejects_a_duplicate_path(self):
        line = f"sha256:{'a' * 64} 1 payload/a\n"
        with pytest.raises(ChecksumError):
            checksums.parse_checksums(line + line)

    def test_verify_entry_accepts_a_match(self):
        entry = checksums.ChecksumEntry(path="payload/a", size=3, sha256=checksums.sha256_bytes(b"abc"))
        checksums.verify_entry(entry, checksums.sha256_bytes(b"abc"), 3)

    def test_verify_entry_rejects_a_digest_mismatch(self):
        entry = checksums.ChecksumEntry(path="payload/a", size=3, sha256="a" * 64)
        with pytest.raises(ChecksumError):
            checksums.verify_entry(entry, checksums.sha256_bytes(b"abc"), 3)

    def test_verify_entry_rejects_a_size_mismatch(self):
        digest = checksums.sha256_bytes(b"abc")
        entry = checksums.ChecksumEntry(path="payload/a", size=99, sha256=digest)
        with pytest.raises(ChecksumError):
            checksums.verify_entry(entry, digest, 3)

    def test_sha256_file_matches_bytes(self, tmp_path):
        target = tmp_path / "sample.bin"
        target.write_bytes(b"payload" * 1000)
        digest, size = checksums.sha256_file(str(target))
        assert digest == checksums.sha256_bytes(b"payload" * 1000)
        assert size == 7000
