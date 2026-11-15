import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from zaodlib import cli, keys, util


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.key = keys.generate_keypair()
        self.paths = support.make_paths(self.tmp, trust=self.key.public)
        self.env = mock.patch.dict(
            os.environ,
            {"ZAOD_ROOT": str(self.paths.root), "HOME": str(self.tmp / "home")},
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.key_file = self.tmp / "signing.key"
        self.key_file.write_text(self.key.export_private(), encoding="utf-8")
        self.public_file = self.tmp / "signing.pub"
        self.public_file.write_text(self.key.export_public(), encoding="utf-8")

    def run_cli(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = cli.main(list(argv))
        return code, buffer.getvalue()

    def test_pack_install_list_info_remove_flow(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "hello.zaod"
        code, output = self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        self.assertEqual(code, 0, output)
        self.assertTrue(package.is_file())

        code, output = self.run_cli("install", str(package))
        self.assertEqual(code, 0, output)
        self.assertIn("installed Hello 1.0.0", output)

        code, output = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("org.zaod.hello", output)

        code, output = self.run_cli("info", "org.zaod.hello")
        self.assertEqual(code, 0, output)
        self.assertIn("MIT", output)

        code, output = self.run_cli("verify", str(package))
        self.assertEqual(code, 0, output)
        self.assertIn("OK org.zaod.hello 1.0.0", output)

        code, output = self.run_cli("remove", "org.zaod.hello")
        self.assertEqual(code, 0, output)
        self.assertIn("removed org.zaod.hello", output)

    def test_install_from_repository_by_app_id(self):
        repo_dir = self.tmp / "repo"
        repo_dir.mkdir()
        source = support.make_app_source(self.tmp)
        package = repo_dir / "hello.zaod"
        self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        code, output = self.run_cli("repo", "build", str(repo_dir), "--name", "core", "--key", str(self.key_file))
        self.assertEqual(code, 0, output)
        code, output = self.run_cli("repo", "add", "core", repo_dir.as_uri(), "--key", str(self.public_file))
        self.assertEqual(code, 0, output)
        code, output = self.run_cli("repo", "sync")
        self.assertEqual(code, 0, output)
        self.assertIn("1 packages", output)

        code, output = self.run_cli("search", "hello")
        self.assertEqual(code, 0, output)
        self.assertIn("org.zaod.hello", output)

        code, output = self.run_cli("install", "org.zaod.hello")
        self.assertEqual(code, 0, output)
        self.assertIn("repository", output)
        self.assertTrue(self.paths.app_current("org.zaod.hello").is_symlink())

    def test_install_missing_app_id_reports_error(self):
        code, output = self.run_cli("install", "org.zaod.nothing")
        self.assertEqual(code, 9, output)
        self.assertIn("not found", output)

    def test_install_unsigned_needs_flag(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "unsigned.zaod"
        self.run_cli("pack", str(source), "-o", str(package))
        code, output = self.run_cli("install", str(package))
        self.assertEqual(code, 4, output)
        self.assertIn("unsigned", output)
        code, output = self.run_cli("install", str(package), "--allow-unsigned")
        self.assertEqual(code, 0, output)

    def test_key_generate_and_list(self):
        out = self.tmp / "dev.key"
        code, output = self.run_cli("key", "generate", "--out", str(out), "--trust")
        self.assertEqual(code, 0, output)
        self.assertTrue(out.is_file())
        code, output = self.run_cli("key", "list")
        self.assertEqual(code, 0, output)
        self.assertIn(self.key.key_id, output)

    def test_pack_reports_hash(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "hello.zaod"
        code, output = self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        self.assertEqual(code, 0, output)
        self.assertIn(util.sha256_file(package), output)

    def test_run_prints_sandbox_command(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "hello.zaod"
        self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        self.run_cli("install", str(package))
        with mock.patch("zaodlib.sandbox.shutil.which", return_value="/usr/bin/bwrap"):
            code, output = self.run_cli("run", "org.zaod.hello", "--print-command")
        self.assertEqual(code, 0, output)
        self.assertIn("--unshare-all", output)
        self.assertIn("payload/bin/hello", output)

    def test_gc_command(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "hello.zaod"
        self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        self.run_cli("install", str(package))
        code, output = self.run_cli("gc")
        self.assertEqual(code, 0, output)
        self.assertIn("removed", output)

    def test_info_on_package_file(self):
        source = support.make_app_source(self.tmp)
        package = self.tmp / "hello.zaod"
        self.run_cli("pack", str(source), "-o", str(package), "--key", str(self.key_file))
        code, output = self.run_cli("info", str(package))
        self.assertEqual(code, 0, output)
        self.assertIn("signed", output)
        self.assertIn(self.key.key_id, output)


if __name__ == "__main__":
    unittest.main()
