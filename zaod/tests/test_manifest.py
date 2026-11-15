import json
import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import manifest as manifest_module
from zaodlib.errors import CompatibilityError, ManifestError


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_parse_valid_manifest(self):
        parsed = manifest_module.parse_manifest(support.manifest_dict())
        self.assertEqual(parsed.id, "org.zaod.hello")
        self.assertEqual(parsed.version, "1.0.0")
        self.assertFalse(parsed.network)
        self.assertEqual(parsed.filesystem_permissions, ["documents"])
        self.assertEqual(parsed.entry["exec"], "payload/bin/hello")

    def test_kind_app_requires_entry(self):
        data = support.manifest_dict()
        data.pop("entry")
        error = support.expect_error(self, ManifestError, manifest_module.parse_manifest, data)
        self.assertIn("requires an entry.exec", str(error))

    def test_unknown_field_rejected(self):
        data = support.manifest_dict(sandbox="none")
        error = support.expect_error(self, ManifestError, manifest_module.parse_manifest, data)
        self.assertIn("unknown field", str(error))

    def test_bad_id_rejected(self):
        error = support.expect_error(self, ManifestError, manifest_module.parse_manifest, support.manifest_dict("Hello"))
        self.assertIn("does not match required pattern", str(error))

    def test_bad_version_rejected(self):
        error = support.expect_error(
            self, ManifestError, manifest_module.parse_manifest, support.manifest_dict(version="1.0")
        )
        self.assertIn("manifest.version", str(error))

    def test_absolute_entry_rejected(self):
        data = support.manifest_dict()
        data["entry"] = {"exec": "/usr/bin/hello"}
        error = support.expect_error(self, ManifestError, manifest_module.parse_manifest, data)
        self.assertIn("does not match required pattern", str(error))

    def test_traversal_path_rejected(self):
        error = support.expect_error(
            self, ManifestError, manifest_module.parse_manifest,
            support.manifest_dict(icon="icon.svg", screenshots=["../escape.png"]),
        )
        self.assertIn("screenshots", str(error))

    def test_min_os_compatibility(self):
        parsed = manifest_module.parse_manifest(support.manifest_dict(min_os="0.9.0"))
        error = support.expect_error(self, CompatibilityError, parsed.check_compatibility, "0.7.0")
        self.assertIn("needs Zaod OS 0.9.0", str(error))

    def test_architecture_compatibility(self):
        parsed = manifest_module.parse_manifest(support.manifest_dict())
        support.expect_error(self, CompatibilityError, parsed.check_compatibility, "0.7.0", "aarch64")

    def test_self_runtime_rejected(self):
        data = support.manifest_dict(runtimes=["org.zaod.hello"])
        support.expect_error(self, ManifestError, manifest_module.parse_manifest, data)

    def test_load_manifest_from_file(self):
        source = support.make_app_source(self.tmp)
        parsed = manifest_module.load_manifest(source / "MANIFEST.json")
        self.assertEqual(parsed.name, "Hello")

    def test_invalid_json(self):
        path = self.tmp / "MANIFEST.json"
        path.write_text("{not json", encoding="utf-8")
        error = support.expect_error(self, ManifestError, manifest_module.load_manifest, path)
        self.assertIn("not valid JSON", str(error))

    def test_canonical_bytes_are_stable(self):
        data = support.manifest_dict()
        reordered = json.loads(json.dumps(data))
        first = manifest_module.parse_manifest(data).canonical
        second = manifest_module.parse_manifest(reordered).canonical
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
