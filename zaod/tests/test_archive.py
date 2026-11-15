import io
import tarfile
import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import archive
from zaodlib.errors import PackageError


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_backend_available(self):
        self.assertIn(archive.backend(), ("cli", "zstandard", "ctypes"))

    def test_roundtrip_tree(self):
        source = self.tmp / "staging"
        (source / "payload" / "bin").mkdir(parents=True)
        (source / "payload" / "bin" / "hello").write_text("hi\n", encoding="utf-8")
        (source / "MANIFEST.json").write_text("{}", encoding="utf-8")
        package = self.tmp / "pkg.zaod"
        archive.compress_tree(source, package, level=3)
        restored = self.tmp / "restored"
        archive.extract_tree(package, restored)
        self.assertEqual((restored / "payload" / "bin" / "hello").read_text(encoding="utf-8"), "hi\n")

    def test_rejects_parent_traversal(self):
        evil = self.tmp / "evil.tar"
        with tarfile.open(evil, "w") as tar:
            info = tarfile.TarInfo("../escape.txt")
            payload = b"owned"
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        package = self.tmp / "evil.zaod"
        archive.compress_file(evil, package)
        error = support.expect_error(self, PackageError, archive.extract_tree, package, self.tmp / "out")
        self.assertIn("escapes the package root", str(error))
        self.assertFalse((self.tmp / "escape.txt").exists())

    def test_rejects_absolute_symlink(self):
        evil = self.tmp / "link.tar"
        with tarfile.open(evil, "w") as tar:
            info = tarfile.TarInfo("payload/link")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/shadow"
            tar.addfile(info)
        package = self.tmp / "link.zaod"
        archive.compress_file(evil, package)
        error = support.expect_error(self, PackageError, archive.extract_tree, package, self.tmp / "out2")
        self.assertIn("absolute", str(error))

    def test_non_tar_payload_rejected(self):
        broken = self.tmp / "broken.zaod"
        broken.write_bytes(b"not a zstd frame")
        support.expect_error(self, PackageError, archive.extract_tree, broken, self.tmp / "out3")


if __name__ == "__main__":
    unittest.main()
