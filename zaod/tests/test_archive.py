"""Archive building, inspection and extraction safety."""

from __future__ import annotations

import io
import tarfile

import pytest
from conftest import make_source

from zaod import archive
from zaod.errors import ArchiveError, ManifestError, UnsafeArchiveError


class TestBuildAndRead:
    def test_build_then_inspect(self, unsigned_package):
        contents = archive.inspect(unsigned_package)
        try:
            assert contents.manifest.id == "os.zaod.notes"
            assert archive.MANIFEST_NAME in contents.members
            assert archive.CHECKSUMS_NAME in contents.members
            assert "payload/notes" in contents.members
            assert contents.signature is None
        finally:
            archive.close_contents(contents)

    def test_checksums_verify(self, unsigned_package):
        contents = archive.inspect(unsigned_package)
        try:
            archive.verify_checksums(contents)
        finally:
            archive.close_contents(contents)

    def test_build_is_deterministic(self, tmp_path):
        source = make_source(tmp_path / "deterministic")
        first = archive.build_archive(
            manifest_bytes=b'{"a":1}\n',
            payload_dir=source / "payload",
            output=tmp_path / "one.zaod",
            extra_files={"icon.svg": source / "icon.svg"},
        )
        second = archive.build_archive(
            manifest_bytes=b'{"a":1}\n',
            payload_dir=source / "payload",
            output=tmp_path / "two.zaod",
            extra_files={"icon.svg": source / "icon.svg"},
        )
        assert first.read_bytes() == second.read_bytes()

    def test_reads_a_plain_tar_package(self, tmp_path):
        tar_path = tmp_path / "plain.tar"
        manifest_bytes = b'{"format":1}\n'
        with tarfile.open(tar_path, "w") as handle:
            for name, data in (
                (archive.MANIFEST_NAME, manifest_bytes),
                (archive.CHECKSUMS_NAME, b""),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                handle.addfile(info, io.BytesIO(data))
        # The tar header was recognised, so the failure is manifest validation.
        with pytest.raises(ManifestError):
            archive.inspect(tar_path)

    def test_rejects_a_missing_file(self, tmp_path):
        with pytest.raises(ArchiveError):
            archive.inspect(tmp_path / "absent.zaod")

    def test_rejects_a_non_archive(self, tmp_path):
        broken = tmp_path / "broken.zaod"
        broken.write_bytes(b"not an archive at all")
        with pytest.raises(ArchiveError):
            archive.inspect(broken)


class TestMemberSafety:
    @pytest.mark.parametrize(
        "name",
        ["/etc/passwd", "../escape", "payload/../../escape", "C:/windows", "a\\b", "a/\x01/b", ""],
    )
    def test_rejects_unsafe_names(self, name):
        with pytest.raises(UnsafeArchiveError):
            archive.safe_member_name(name)

    @pytest.mark.parametrize("name", ["payload/app", "icon.svg", "./payload/app", "screenshots/a.png"])
    def test_accepts_safe_names(self, name):
        assert archive.safe_member_name(name)

    def test_rejects_a_symlink_escape(self, tmp_path):
        tar_path = tmp_path / "evil.tar"
        with tarfile.open(tar_path, "w") as handle:
            data = b"{}"
            info = tarfile.TarInfo(archive.MANIFEST_NAME)
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("payload/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../etc/passwd"
            handle.addfile(link)
        with pytest.raises(UnsafeArchiveError):
            archive.inspect(tar_path)

    def test_rejects_a_hard_link(self, tmp_path):
        tar_path = tmp_path / "hard.tar"
        with tarfile.open(tar_path, "w") as handle:
            data = b"{}"
            info = tarfile.TarInfo(archive.MANIFEST_NAME)
            info.size = len(data)
            handle.addfile(info, io.BytesIO(data))
            link = tarfile.TarInfo("payload/hard")
            link.type = tarfile.LNKTYPE
            link.linkname = "payload/other"
            handle.addfile(link)
        with pytest.raises(UnsafeArchiveError):
            archive.inspect(tar_path)

    def test_rejects_a_duplicate_member(self, tmp_path):
        tar_path = tmp_path / "dup.tar"
        with tarfile.open(tar_path, "w") as handle:
            for _ in range(2):
                data = b"{}"
                info = tarfile.TarInfo(archive.MANIFEST_NAME)
                info.size = len(data)
                handle.addfile(info, io.BytesIO(data))
        with pytest.raises((UnsafeArchiveError, ArchiveError)):
            archive.inspect(tar_path)

    def test_member_limit(self, tmp_path):
        source = make_source(tmp_path / "many", files={f"file{i}": "x" for i in range(12)})
        package = archive.build_archive(
            manifest_bytes=b'{"format":1}\n',
            payload_dir=source / "payload",
            output=tmp_path / "many.zaod",
        )
        with pytest.raises(UnsafeArchiveError):
            archive.inspect(package, archive.Limits(max_members=5))


class TestUnpack:
    def test_unpacks_the_payload(self, unsigned_package, tmp_path):
        contents = archive.inspect(unsigned_package)
        try:
            destination = archive.unpack(contents, tmp_path / "unpacked")
            assert (destination / "payload/notes").is_file()
            assert (destination / "MANIFEST.json").is_file()
        finally:
            archive.close_contents(contents)

    def test_refuses_to_overwrite(self, unsigned_package, tmp_path):
        contents = archive.inspect(unsigned_package)
        try:
            destination = tmp_path / "unpacked"
            (destination / "payload").mkdir(parents=True)
            (destination / "payload/notes").write_text("existing\n")
            with pytest.raises(UnsafeArchiveError):
                archive.unpack(contents, destination)
            assert (destination / "payload/notes").read_text() == "existing\n"
        finally:
            archive.close_contents(contents)

    def test_reads_the_icon(self, unsigned_package):
        contents = archive.inspect(unsigned_package)
        try:
            icon = archive.read_icon(contents)
            assert icon is not None and b"<svg" in icon
        finally:
            archive.close_contents(contents)
