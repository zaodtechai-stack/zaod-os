import json
import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import archive, keys
from zaodlib.errors import HashError, ManifestError, SignatureError
from zaodlib.verify import parse_checksums, verify_staged


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.key = keys.generate_keypair()
        self.paths = support.make_paths(self.tmp, trust=self.key.public)
        self.package = support.make_package(self.tmp, key=self.key)

    def extract(self):
        target = self.tmp / "stage"
        archive.extract_tree(self.package, target)
        return target

    def test_signed_package_verifies(self):
        verified = verify_staged(self.extract(), keyring=keys.trusted_keys(self.paths.keys_dir))
        self.assertTrue(verified.signed)
        self.assertEqual(verified.key_id, self.key.key_id)
        self.assertIn("payload/bin/hello", verified.checksums)

    def test_unsigned_package_requires_explicit_consent(self):
        unsigned = support.make_package(self.tmp, name="unsigned")
        staging = self.tmp / "unsigned-stage"
        archive.extract_tree(unsigned, staging)
        error = support.expect_error(self, SignatureError, verify_staged, staging)
        self.assertIn("unsigned", str(error))
        verified = verify_staged(staging, allow_unsigned=True)
        self.assertFalse(verified.signed)

    def test_tampered_payload_rejected(self):
        staging = self.extract()
        (staging / support.DEFAULT_ENTRY).write_text("#!/bin/sh\necho tampered\n", encoding="utf-8")
        error = support.expect_error(self, HashError, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir))
        self.assertIn("tampered", str(error))

    def test_missing_payload_file_rejected(self):
        staging = self.extract()
        (staging / support.DEFAULT_ENTRY).unlink()
        error = support.expect_error(self, HashError, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir))
        self.assertIn("missing", str(error))

    def test_unlisted_extra_file_rejected(self):
        staging = self.extract()
        (staging / "payload" / "bin" / "extra").write_text("surprise", encoding="utf-8")
        error = support.expect_error(self, HashError, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir))
        self.assertIn("not listed", str(error))

    def test_manifest_tamper_breaks_signature(self):
        staging = self.extract()
        manifest_file = staging / "MANIFEST.json"
        manifest_file.write_text(manifest_file.read_text(encoding="utf-8").replace("Hello", "Evil"), encoding="utf-8")
        support.expect_error(self, SignatureError, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir))

    def test_missing_checksums(self):
        staging = self.extract()
        (staging / "CHECKSUMS").unlink()
        support.expect_error(self, ManifestError, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir))

    def test_entry_must_be_in_payload(self):
        unsigned = support.make_package(self.tmp, name="badentry")
        staging = self.tmp / "badentry-stage"
        archive.extract_tree(unsigned, staging)
        data = json.loads((staging / "MANIFEST.json").read_text(encoding="utf-8"))
        data["entry"]["exec"] = "payload/bin/other"
        (staging / "MANIFEST.json").write_text(json.dumps(data), encoding="utf-8")
        error = support.expect_error(self, ManifestError, verify_staged, staging, allow_unsigned=True)
        self.assertIn("not part of the package payload", str(error))

    def test_min_os_enforced(self):
        newer = support.make_package(
            self.tmp, key=self.key, name="newer", manifest_overrides={"min_os": "0.9.0"},
        )
        staging = self.tmp / "newer-stage"
        archive.extract_tree(newer, staging)
        support.expect_error(self, Exception, verify_staged, staging, keyring=keys.trusted_keys(self.paths.keys_dir), os_version="0.7.0")

    def test_parse_checksums_validates_format(self):
        with self.assertRaises(ManifestError):
            parse_checksums("deadbeef  payload/a\n")
        with self.assertRaises(ManifestError):
            parse_checksums("")


if __name__ == "__main__":
    unittest.main()
