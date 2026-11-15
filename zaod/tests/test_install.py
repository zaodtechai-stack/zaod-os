import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from zaodlib import db as db_module
from zaodlib import keys, util
from zaodlib.errors import HashError, SignatureError, StateError
from zaodlib.install import Installer


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.key = keys.generate_keypair()
        self.paths = support.make_paths(self.tmp, trust=self.key.public)
        self.installer = Installer(self.paths)
        self.package = support.make_package(self.tmp, key=self.key)

    def test_install_records_app_and_state(self):
        result = self.installer.install(self.package)
        self.assertEqual(result.version, "1.0.0")
        self.assertTrue(result.signed)
        record = self.installer.db.get("org.zaod.hello")
        self.assertEqual(record["version"], "1.0.0")
        self.assertEqual(record["key_id"], self.key.key_id)
        current = self.paths.app_current("org.zaod.hello")
        self.assertTrue(current.is_symlink())
        self.assertTrue((current / "payload" / "bin" / "hello").is_file())

    def test_installed_payload_is_read_only(self):
        self.installer.install(self.package)
        target = self.paths.app_version_dir("org.zaod.hello", "1.0.0")
        mode = (target / "payload" / "bin" / "hello").stat().st_mode
        self.assertEqual(mode & 0o222, 0)

    def test_desktop_entry_created_and_removed(self):
        self.installer.install(self.package)
        entry = self.paths.desktop_file("org.zaod.hello")
        text = entry.read_text(encoding="utf-8")
        self.assertIn("Exec=", text)
        self.assertIn("X-Zaod-AppId=org.zaod.hello", text)
        self.installer.remove("org.zaod.hello")
        self.assertFalse(entry.exists())

    def test_unsigned_package_rejected_by_default(self):
        unsigned = support.make_package(self.tmp, name="unsigned")
        support.expect_error(self, SignatureError, self.installer.install, unsigned)
        self.assertIsNone(self.installer.db.get("org.zaod.hello"))

    def test_unsigned_package_with_explicit_consent(self):
        unsigned = support.make_package(self.tmp, name="unsigned")
        result = self.installer.install(unsigned, allow_unsigned=True)
        self.assertFalse(result.signed)
        self.assertIn("unsigned", " ".join(result.warnings))

    def test_tampered_package_leaves_no_install(self):
        support.corrupt_payload(self.package, self.tmp)
        support.expect_error(self, HashError, self.installer.install, self.package)
        self.assertIsNone(self.installer.db.get("org.zaod.hello"))
        self.assertFalse(self.paths.app_version_dir("org.zaod.hello", "1.0.0").exists())
        self.assertFalse(self.paths.app_current("org.zaod.hello").is_symlink())

    def test_reinstall_requires_force(self):
        self.installer.install(self.package)
        support.expect_error(self, StateError, self.installer.install, self.package)
        self.installer.install(self.package, force=True)
        self.assertTrue(self.paths.app_current("org.zaod.hello").is_symlink())

    def test_downgrade_refused_without_force(self):
        newer = support.make_package(self.tmp, key=self.key, name="hello2", version="2.0.0")
        older = support.make_package(self.tmp, key=self.key, name="hello1", version="1.0.0")
        self.installer.install(newer)
        error = support.expect_error(self, StateError, self.installer.install, older)
        self.assertIn("downgrade", str(error))
        self.assertEqual(self.installer.db.get("org.zaod.hello")["version"], "2.0.0")

    def test_update_keeps_previous_version_for_rollback(self):
        self.installer.install(self.package)
        newer = support.make_package(self.tmp, key=self.key, name="hello2", version="1.1.0")
        result = self.installer.install(newer)
        self.assertEqual(result.previous_version, "1.0.0")
        self.assertEqual(self.installer.db.get("org.zaod.hello")["version"], "1.1.0")
        self.assertTrue(self.paths.app_version_dir("org.zaod.hello", "1.0.0").is_dir())

    def test_interrupted_update_preserves_previous_install(self):
        self.installer.install(self.package)
        newer = support.make_package(self.tmp, key=self.key, name="hello2", version="1.1.0")
        with (
            mock.patch.object(db_module.Database, "record_install", side_effect=RuntimeError("disk full")),
            self.assertRaises(RuntimeError),
        ):
            self.installer.install(newer)
        record = self.installer.db.get("org.zaod.hello")
        self.assertEqual(record["version"], "1.0.0")
        current = self.paths.app_current("org.zaod.hello").resolve()
        self.assertEqual(current.name, "1.0.0")
        self.assertFalse(self.paths.app_version_dir("org.zaod.hello", "1.1.0").exists())

    def test_gc_removes_superseded_versions(self):
        self.installer.install(self.package)
        newer = support.make_package(self.tmp, key=self.key, name="hello2", version="1.1.0")
        self.installer.install(newer)
        removed = self.installer.gc()
        self.assertTrue(any("1.0.0" in path for path in removed))
        self.assertTrue(self.paths.app_version_dir("org.zaod.hello", "1.1.0").is_dir())
        self.assertEqual(self.installer.db.get("org.zaod.hello")["version"], "1.1.0")

    def test_remove_deletes_files_and_keeps_user_data(self):
        self.installer.install(self.package)
        data = self.paths.app_data_dir("org.zaod.hello")
        data.mkdir(parents=True, exist_ok=True)
        (data / "notes.txt").write_text("keep me", encoding="utf-8")
        self.installer.remove("org.zaod.hello")
        self.assertFalse(self.paths.app_dir("org.zaod.hello").exists())
        self.assertTrue((data / "notes.txt").exists())

    def test_purge_removes_user_data(self):
        self.installer.install(self.package)
        data = self.paths.app_data_dir("org.zaod.hello")
        data.mkdir(parents=True, exist_ok=True)
        self.installer.remove("org.zaod.hello", purge_data=True)
        self.assertFalse(data.exists())

    def test_remove_unknown_app(self):
        support.expect_error(self, StateError, self.installer.remove, "org.zaod.missing")

    def test_info_reports_manifest_details(self):
        self.installer.install(self.package)
        info = self.installer.info("org.zaod.hello")
        self.assertEqual(info["license"], "MIT")
        self.assertEqual(info["permissions"]["filesystem"], ["documents"])

    def test_installed_list_is_sorted(self):
        self.installer.install(self.package)
        second = support.make_package(self.tmp, key=self.key, name="alpha", app_id="org.zaod.alpha")
        self.installer.install(second)
        self.assertEqual(self.installer.db.installed_ids(), ["org.zaod.alpha", "org.zaod.hello"])

    def test_associations_written_to_mimeapps(self):
        package = support.make_package(
            self.tmp, key=self.key, name="assoc", manifest_overrides={"associations": ["text/plain"]}
        )
        self.installer.install(package)
        text = self.paths.path("/etc/xdg/mimeapps.list").read_text(encoding="utf-8")
        self.assertIn("text/plain=org.zaod.hello.desktop", text)
        self.assertTrue(util.sha256_file(self.paths.app_current("org.zaod.hello") / "MANIFEST.json"))


if __name__ == "__main__":
    unittest.main()
