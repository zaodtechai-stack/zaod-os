"""Store backend tests against a real signed file:// repository."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
os.environ.setdefault("ZAOD_LIB", str(REPO_ROOT / "zaod"))
sys.path.insert(0, str(REPO_ROOT / "zaod"))

from zaodlib import keys, pack, repo
from zaodlib import paths as zaod_paths


def load_backend():
    entry = REPO_ROOT / "apps" / "store" / "payload" / "backend.py"
    spec = importlib.util.spec_from_file_location("store_backend", entry)
    module = importlib.util.module_from_spec(spec)
    sys.modules["store_backend"] = module
    spec.loader.exec_module(module)
    return module


store_backend = load_backend()


def make_package(tmp: pathlib.Path, version: str, app_id: str = "org.zaod.demo", name: str = "Demo", key=None, key_path=None):
    source = tmp / f"src-{version}"
    (source / "payload" / "bin").mkdir(parents=True, exist_ok=True)
    script = source / "payload" / "bin" / "demo"
    script.write_text("#!/bin/sh\necho demo\n", encoding="utf-8")
    script.chmod(0o755)
    (source / "icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8")
    manifest = {
        "format": 1,
        "id": app_id,
        "name": name,
        "version": version,
        "kind": "app",
        "arch": "x86_64",
        "min_os": "0.7.0",
        "summary": f"{name} demo app",
        "description": f"{name} used by the store tests.",
        "categories": ["Utility"],
        "license": {"spdx": "MIT"},
        "author": {"name": "Zaod Tests"},
        "entry": {"exec": "payload/bin/demo", "terminal": True},
        "icon": "icon.svg",
        "permissions": {"network": False, "filesystem": ["documents"], "devices": []},
    }
    (source / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    output = tmp / f"{app_id}-{version}.zaod"
    pack.build_package(source, output, private_key=key_path, level=3)
    return output


class StoreBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.key = keys.generate_keypair()
        self.key_path = self.tmp / "store.key"
        self.key_path.write_text(self.key.export_private(), encoding="utf-8")
        self.repo_dir = self.tmp / "repo"
        self.repo_dir.mkdir()
        make_package(self.tmp, "1.1.0", app_id="org.zaod.demo", name="Demo", key_path=self.key_path).replace(
            self.repo_dir / "demo-1.1.0.zaod"
        )
        make_package(self.tmp, "2.0.0", app_id="org.zaod.extra", name="Extra", key_path=self.key_path).replace(
            self.repo_dir / "extra-2.0.0.zaod"
        )
        repo.build_index(self.repo_dir, "core", self.key)

        self.root = self.tmp / "root"
        os.environ["ZAOD_ROOT"] = str(self.root)
        self.paths = zaod_paths.Paths()
        self.paths.apps_dir.mkdir(parents=True, exist_ok=True)
        self.paths.keys_dir.mkdir(parents=True, exist_ok=True)
        keys.trust_public_key(self.paths.keys_dir, self.key.public)
        repo.RepoSet(self.paths).add(
            repo.Repo(name="core", url=self.repo_dir.as_uri(), key_ids=[self.key.key_id])
        )
        self.calls = []
        self.store = store_backend.StoreBackend(paths=self.paths, run=self.calls.append)

    def tearDown(self):
        os.environ.pop("ZAOD_ROOT", None)

    def test_sync_then_catalogue(self):
        indexes = self.store.sync()
        self.assertIn("core", indexes)
        items = self.store.catalogue()
        self.assertEqual([item["id"] for item in items], ["org.zaod.demo", "org.zaod.extra"])
        self.assertEqual({item["state"] for item in items}, {"new"})

    def test_update_state_when_newer_version_is_indexed(self):
        self.paths.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.db_file.write_text(
            json.dumps({"format": 1, "apps": {"org.zaod.demo": {"name": "Demo", "version": "1.0.0", "kind": "app"}}}),
            encoding="utf-8",
        )
        self.store.sync()
        items = {item["id"]: item for item in self.store.catalogue()}
        self.assertEqual(items["org.zaod.demo"]["state"], "update")
        self.assertEqual(items["org.zaod.demo"]["installed_version"], "1.0.0")
        self.assertEqual(items["org.zaod.extra"]["state"], "new")
        self.assertEqual([item["id"] for item in self.store.updates_available()], ["org.zaod.demo"])

    def test_installed_version_equal_means_installed(self):
        self.paths.db_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.db_file.write_text(
            json.dumps({"format": 1, "apps": {"org.zaod.demo": {"name": "Demo", "version": "1.1.0", "kind": "app"}}}),
            encoding="utf-8",
        )
        self.store.sync()
        item = self.store.details("org.zaod.demo")
        self.assertEqual(item["state"], "installed")

    def test_search_matches_name_summary_and_category(self):
        self.store.sync()
        self.assertEqual([item["id"] for item in self.store.catalogue("extra")], ["org.zaod.extra"])
        self.assertEqual([item["id"] for item in self.store.catalogue("utility")], ["org.zaod.demo", "org.zaod.extra"])
        self.assertEqual(self.store.catalogue("nothing here"), [])

    def test_install_and_remove_use_privileged_helper(self):
        self.store.sync()
        self.store.install("org.zaod.demo")
        self.store.remove("org.zaod.demo")
        self.store.update("org.zaod.demo")
        self.store.update_all()
        self.assertEqual(
            self.calls,
            [
                ["install", "org.zaod.demo"],
                ["remove", "org.zaod.demo"],
                ["update", "org.zaod.demo"],
                ["update"],
            ],
        )

    def test_offline_behaviour_without_cache(self):
        self.assertTrue(self.store.offline())
        self.assertEqual(self.store.catalogue(), [])

    def test_cached_index_works_offline(self):
        self.store.sync()
        self.repo_dir.rename(self.tmp / "repo-moved")
        self.assertFalse(self.store.offline())
        self.assertEqual(len(self.store.catalogue()), 2)

    def test_permission_summary(self):
        item = {"permissions": {"network": True, "filesystem": ["documents"], "devices": ["dri"]}}
        self.assertEqual(
            self.store.permission_summary(item),
            ["network access", "files: documents", "device: dri"],
        )
        self.assertEqual(self.store.permission_summary({"permissions": {}}), ["no extra permissions"])

    def test_version_comparison(self):
        compare = store_backend._compare_versions
        self.assertEqual(compare("1.10.0", "1.9.0"), 1)
        self.assertEqual(compare("1.0.0", "1.0.0"), 0)
        self.assertEqual(compare("0.9", "1.0.0"), -1)

    def test_unknown_app_details(self):
        self.store.sync()
        with self.assertRaises(store_backend.StoreError):
            self.store.details("org.zaod.missing")


if __name__ == "__main__":
    unittest.main()
