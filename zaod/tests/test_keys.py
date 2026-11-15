import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import keys
from zaodlib.errors import SignatureError


class KeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_generate_sign_verify(self):
        pair = keys.generate_keypair()
        signature = pair.sign(b"payload bytes")
        document = keys.signature_document(pair, b"payload bytes")
        key_id, parsed = keys.parse_signature(document)
        self.assertEqual(key_id, pair.key_id)
        self.assertEqual(parsed, signature)

    def test_private_key_roundtrip(self):
        pair = keys.generate_keypair()
        path = self.tmp / "dev.key"
        path.write_text(pair.export_private(), encoding="utf-8")
        loaded = keys.load_private_key(path)
        self.assertEqual(loaded.public, pair.public)
        self.assertEqual(loaded.seed, pair.seed)

    def test_private_key_header_required(self):
        path = self.tmp / "bad.key"
        path.write_text("garbage\n", encoding="utf-8")
        error = support.expect_error(self, SignatureError, keys.load_private_key, path)
        self.assertIn("not a Zaod private key", str(error))

    def test_trusted_keyring_loads_and_names_match(self):
        pair = keys.generate_keypair()
        directory = self.tmp / "keys"
        keys.trust_public_key(directory, pair.public)
        keyring = keys.trusted_keys(directory)
        self.assertEqual(list(keyring), [pair.key_id])

    def test_keyring_rejects_misnamed_file(self):
        pair = keys.generate_keypair()
        directory = self.tmp / "keys"
        directory.mkdir()
        (directory / "deadbeefdeadbeef.pub").write_text(pair.export_public(), encoding="utf-8")
        support.expect_error(self, SignatureError, keys.trusted_keys, directory)

    def test_untrusted_key_is_refused(self):
        pair = keys.generate_keypair()
        other = keys.generate_keypair()
        directory = self.tmp / "keys"
        keys.trust_public_key(directory, other.public)
        document = keys.signature_document(pair, b"data")
        key_id, signature = keys.parse_signature(document)
        error = support.expect_error(
            self, SignatureError, keys.verify_with_keyring, keys.trusted_keys(directory), key_id, b"data", signature
        )
        self.assertIn("not trusted", str(error))

    def test_tampered_signature_data_refused(self):
        pair = keys.generate_keypair()
        signature = pair.sign(b"good data")
        error = support.expect_error(
            self, SignatureError, keys.verify_with_keyring, {pair.key_id: pair.public}, pair.key_id, b"bad data", signature
        )
        self.assertIn("does not match", str(error))


if __name__ == "__main__":
    unittest.main()
