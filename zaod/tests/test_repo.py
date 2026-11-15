import json
import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import keys, repo, util
from zaodlib.errors import RepoError


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.key = keys.generate_keypair()
        self.paths = support.make_paths(self.tmp, trust=self.key.public)
        self.repo_dir = self.tmp / "repo"
        self.repo_dir.mkdir()
        support.make_package(self.tmp, key=self.key, name="hello1", version="1.0.0")
        support.make_package(self.tmp, key=self.key, name="hello2", version="2.0.0")
        for package in self.tmp.glob("*.zaod"):
            package.replace(self.repo_dir / package.name)
        repo.build_index(self.repo_dir, "core", self.key)
        self.url = self.repo_dir.as_uri()

    def test_index_is_signed_and_valid(self):
        raw = (self.repo_dir / "index.json").read_bytes()
        signature = (self.repo_dir / "index.json.sig").read_bytes()
        index = repo.verify_index(raw, signature, keys.trusted_keys(self.paths.keys_dir), [self.key.key_id])
        self.assertEqual(index["name"], "core")
        self.assertEqual(len(index["packages"]), 2)
        self.assertEqual(index["packages"][0]["id"], "org.zaod.hello")

    def test_tampered_index_rejected(self):
        raw = json.loads((self.repo_dir / "index.json").read_text(encoding="utf-8"))
        raw["packages"][0]["summary"] = "Tampered summary text"
        signature = (self.repo_dir / "index.json.sig").read_bytes()
        error = support.expect_error(
            self, Exception, repo.verify_index, json.dumps(raw).encode(),
            signature, keys.trusted_keys(self.paths.keys_dir), None,
        )
        self.assertIn("does not match", str(error))

    def test_untrusted_signing_key_rejected(self):
        other = keys.generate_keypair()
        raw = (self.repo_dir / "index.json").read_bytes()
        signature = json.dumps(
            {"format": 1, "key_id": other.key_id, "sig": keys.base64.b64encode(other.sign(raw)).decode()}
        ).encode()
        error = support.expect_error(
            self, RepoError, repo.verify_index, raw, signature, keys.trusted_keys(self.paths.keys_dir),
            [self.key.key_id],
        )
        self.assertIn("does not trust", str(error))

    def test_repo_set_add_and_remove(self):
        reposet = repo.RepoSet(self.paths)
        reposet.add(repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id]))
        self.assertEqual(reposet.get("core").url, self.url)
        support.expect_error(self, RepoError, reposet.add, repo.Repo(name="core", url=self.url))
        reposet.remove("core")
        self.assertEqual(reposet.repos, [])

    def test_sync_caches_index(self):
        entry = repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id])
        index = repo.sync_repo(entry, self.paths, keys.trusted_keys(self.paths.keys_dir))
        self.assertEqual(len(index["packages"]), 2)
        cached = repo.cached_index(self.paths, "core")
        self.assertEqual(cached["name"], "core")
        self.assertIsNotNone(entry.last_sync)

    def test_search_matches_name_and_summary(self):
        entry = repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id])
        index = repo.sync_repo(entry, self.paths, keys.trusted_keys(self.paths.keys_dir))
        results = repo.search({"core": index}, "hello")
        self.assertTrue(results)
        self.assertEqual(repo.search({"core": index}, "nothing-matches"), [])

    def test_find_package_prefers_highest_version(self):
        entry = repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id])
        index = repo.sync_repo(entry, self.paths, keys.trusted_keys(self.paths.keys_dir))
        found = repo.find_package({"core": index}, "org.zaod.hello")
        self.assertEqual(found["version"], "2.0.0")
        support.expect_error(self, RepoError, repo.find_package, {"core": index}, "org.zaod.none")

    def test_download_verifies_hash(self):
        entry = repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id])
        index = repo.sync_repo(entry, self.paths, keys.trusted_keys(self.paths.keys_dir))
        package = repo.find_package({"core": index}, "org.zaod.hello")
        downloaded = repo.download_package(package, self.paths, self.url)
        self.assertEqual(util.sha256_file(downloaded), package["sha256"])

    def test_download_rejects_corrupted_file(self):
        entry = repo.Repo(name="core", url=self.url, key_ids=[self.key.key_id])
        index = repo.sync_repo(entry, self.paths, keys.trusted_keys(self.paths.keys_dir))
        package = repo.find_package({"core": index}, "org.zaod.hello")
        target = self.repo_dir / package["filename"]
        target.write_bytes(b"corrupted package data")
        error = support.expect_error(self, RepoError, repo.download_package, package, self.paths, self.url)
        self.assertIn("does not match the signed index", str(error))

    def test_missing_repository_index_reports_action(self):
        support.expect_error(self, RepoError, repo.cached_index, self.paths, "absent")

    def test_build_index_writes_signature_file(self):
        self.assertTrue((self.repo_dir / "index.json.sig").is_file())
        underlying = json.loads((self.repo_dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(underlying["format"], 1)


if __name__ == "__main__":
    unittest.main()
