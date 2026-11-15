"""Update bundle tests: creation, verification, applying and rollback."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from zaodlib import archive, install, keys, pack, update
from zaodlib import paths as zaod_paths
from zaodlib.errors import HashError, SignatureError, StateError
from zaodlib.install import Installer

OS_RELEASE = 'VERSION_ID="1.0.0"\n'


def make_package(directory: pathlib.Path, app_id: str, version: str, *, key: pathlib.Path | None = None) -> pathlib.Path:
    """Build a tiny valid app package for tests."""
    staging = directory / f"stage-{app_id}-{version}"
    (staging / "payload").mkdir(parents=True, exist_ok=True)
    script = staging / "payload" / "main.sh"
    script.write_text(f"#!/bin/bash\necho {app_id} {version}\n", encoding="utf-8")
    script.chmod(0o755)
    (staging / "icon.svg").write_text("<svg/>\n", encoding="utf-8")
    manifest = {
        "format": 1,
        "id": app_id,
        "name": app_id,
        "version": version,
        "kind": "app",
        "arch": "x86_64",
        "min_os": "0.9.0",
        "summary": "test app",
        "license": {"spdx": "MIT", "name": "MIT License"},
        "author": {"name": "tests"},
        "entry": {"exec": "payload/main.sh", "args": [], "terminal": True},
        "icon": "icon.svg",
        "permissions": {"network": False, "filesystem": [], "devices": []},
        "runtimes": [],
    }
    (staging / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    target = directory / f"{app_id}-{version}.zaod"
    pack.build_package(staging, target, private_key=key, level=2)
    return target


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.previous_root = os.environ.get("ZAOD_ROOT")
        self.root = self.tmp / "root"
        os.environ["ZAOD_ROOT"] = str(self.root)
        (self.root / "etc").mkdir(parents=True)
        (self.root / "etc" / "os-release").write_text(OS_RELEASE, encoding="utf-8")
        self.paths = zaod_paths.Paths()
        self.key = keys.generate_keypair()
        self.key_path = self.tmp / "release.key"
        self.key_path.write_text(self.key.export_private(), encoding="utf-8")
        keys.trust_public_key(self.paths.keys_dir, self.key.public)

    def tearDown(self):
        if self.previous_root is None:
            os.environ.pop("ZAOD_ROOT", None)
        else:
            os.environ["ZAOD_ROOT"] = self.previous_root

    def bundle(self, packages, *, target="1.1.0", base="1.0.0", name="bundle.zaodbundle", key=...):
        signing_key = self.key_path if key is ... else key
        return update.create_bundle(
            packages,
            self.tmp / name,
            base_version=base,
            target_version=target,
            notes="test release",
            key=signing_key,
            level=2,
        )

    def install_version(self, app_id: str, version: str) -> pathlib.Path:
        package = make_package(self.tmp / "packages", app_id, version, key=self.key_path)
        Installer(self.paths).install(package, allow_unsigned=True, force=True)
        return package

    def test_bundle_roundtrip_and_signature(self):
        package = self.install_version("org.example.app", "1.0.0")
        bundle = self.bundle([package])
        self.assertTrue(bundle.path.is_file())
        self.assertEqual(bundle.key_id, self.key.key_id)

        verified = update.verify_bundle(bundle.path, keys.trusted_keys(self.paths.keys_dir))
        self.assertEqual(verified.target_version, "1.1.0")
        self.assertEqual(verified.base_version, "1.0.0")
        self.assertEqual(len(verified.packages), 1)
        self.assertEqual(verified.key_id, self.key.key_id)

    def test_unsigned_bundle_is_refused_by_default(self):
        package = self.install_version("org.example.app", "1.0.0")
        bundle = self.bundle([package], key=None)
        with self.assertRaises(SignatureError):
            update.verify_bundle(bundle.path, keys.trusted_keys(self.paths.keys_dir))
        accepted = update.verify_bundle(bundle.path, {}, allow_unsigned=True)
        self.assertFalse(accepted.signed)

    def test_untrusted_key_is_refused(self):
        package = self.install_version("org.example.app", "1.0.0")
        bundle = self.bundle([package])
        stranger = keys.generate_keypair()
        with self.assertRaises(SignatureError):
            update.verify_bundle(bundle.path, {stranger.key_id: stranger.public})

    def test_tampered_package_file_is_detected(self):
        package = self.install_version("org.example.app", "1.0.0")
        bundle = self.bundle([package])
        extracted = self.tmp / "extracted"
        archive.extract_tree(bundle.path, extracted)
        entry = next((extracted / "packages").iterdir())
        entry.write_bytes(entry.read_bytes() + b"tamper")
        tampered = self.tmp / "tampered.zaodbundle"
        archive.compress_tree(extracted, tampered, level=2)
        with self.assertRaises((HashError, SignatureError)):
            update.verify_bundle(tampered, keys.trusted_keys(self.paths.keys_dir), allow_unsigned=True)

    def test_apply_installs_newer_version(self):
        package = self.install_version("org.example.app", "1.0.0")
        newer = make_package(self.tmp / "packages", "org.example.app", "1.1.0", key=self.key_path)
        bundle = self.bundle([newer])
        report = update.apply_bundle(self.paths, bundle.path)
        self.assertEqual(report.installed, ["org.example.app"])
        self.assertEqual(Installer(self.paths).current_version("org.example.app"), "1.1.0")
        self.assertTrue((report.journal / "journal.json").is_file())
        self.assertGreater(package.stat().st_size, 0)

    def test_failed_apply_rolls_everything_back(self):
        self.install_version("org.example.first", "1.0.0")
        newer_first = make_package(self.tmp / "packages", "org.example.first", "1.1.0", key=self.key_path)
        self.install_version("org.example.second", "1.0.0")
        newer_second = make_package(self.tmp / "packages", "org.example.second", "1.1.0", key=self.key_path)
        bundle = self.bundle([newer_first, newer_second])

        class FailingInstaller(Installer):
            def install(self, package, **kwargs):
                if str(package).endswith("second-1.1.0.zaod"):
                    raise StateError("simulated disk error")
                return super().install(package, **kwargs)

        with self.assertRaises(StateError) as caught:
            update.apply_bundle(self.paths, bundle.path, installer=FailingInstaller(self.paths))
        self.assertIn("rolled back", str(caught.exception))
        installer = Installer(self.paths)
        self.assertEqual(installer.current_version("org.example.first"), "1.0.0")
        self.assertEqual(installer.current_version("org.example.second"), "1.0.0")

    def test_rollback_journal_can_be_replayed(self):
        self.install_version("org.example.app", "1.0.0")
        newer = make_package(self.tmp / "packages", "org.example.app", "1.1.0", key=self.key_path)
        bundle = self.bundle([newer])
        report = update.apply_bundle(self.paths, bundle.path)
        self.assertEqual(Installer(self.paths).current_version("org.example.app"), "1.1.0")
        restored = update.rollback_journal(self.paths, report.journal)
        self.assertEqual(restored, ["org.example.app 1.0.0"])
        self.assertEqual(Installer(self.paths).current_version("org.example.app"), "1.0.0")

    def test_bundle_without_packages_is_refused(self):
        with self.assertRaises(StateError):
            self.bundle([])

    def test_bundle_entry_point_of_package_is_still_verified(self):
        package = self.install_version("org.example.app", "1.0.0")
        bundle = self.bundle([package])
        report = update.apply_bundle(self.paths, bundle.path)
        verified = install.verify_package(self.paths, package, allow_unsigned=True)
        self.assertEqual(verified.manifest.id, "org.example.app")
        self.assertEqual(report.target_version, "1.1.0")


if __name__ == "__main__":
    unittest.main()
