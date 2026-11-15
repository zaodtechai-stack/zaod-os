"""Studio tests: templates, scaffolding, manifest generation, builds and dev keys."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

STUDIO = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIO.parent
sys.path.insert(0, str(STUDIO))
sys.path.insert(0, str(REPO_ROOT / "zaod"))

from zaodlib import install, keys
from zaodlib import paths as zaod_paths
from zaodstudio import (
    TEMPLATES,
    Project,
    ProjectError,
    build_project,
    developer_keys,
    generate_manifest,
    scaffold,
)
from zaodstudio.project import key_id_of

TOOL_TEMPLATES = {
    "c-cmake": ("cmake", "cc"),
    "shell": ("bash",),
}


def tool_missing(template_name: str) -> str | None:
    for tool in TOOL_TEMPLATES.get(template_name, ()):
        if shutil.which(tool) is None:
            return tool
    return None


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.previous_root = os.environ.get("ZAOD_ROOT")
        self.root = self.tmp / "zaod-root"
        os.environ["ZAOD_ROOT"] = str(self.root)
        # Studio projects default to min_os 0.9.0, so the test system reports 1.0.0.
        (self.root / "etc").mkdir(parents=True, exist_ok=True)
        (self.root / "etc" / "os-release").write_text('VERSION_ID="1.0.0"\n', encoding="utf-8")

    def tearDown(self):
        if self.previous_root is None:
            os.environ.pop("ZAOD_ROOT", None)
        else:
            os.environ["ZAOD_ROOT"] = self.previous_root

    def make(self, template: str, slug: str = "demo"):
        app_id = f"org.zaodstudio.{slug}"
        project = scaffold(template, self.tmp / template, app_id, f"Studio {slug}")
        return project, app_id

    def verify(self, package: pathlib.Path):
        return install.verify_package(zaod_paths.Paths(), package, allow_unsigned=True)


class TemplateTests(StudioTest):
    def test_five_templates_exist(self):
        self.assertEqual(sorted(TEMPLATES), ["c-cmake", "python-cli", "python-qt", "shell", "web-wrapper"])

    def test_scaffold_writes_a_complete_project(self):
        for template_name, template in TEMPLATES.items():
            with self.subTest(template=template_name):
                project, app_id = self.make(template_name)
                self.assertTrue((project.root / "zaod.project.json").is_file())
                self.assertTrue((project.root / "MANIFEST.json").is_file())
                self.assertTrue((project.root / "icon.svg").is_file())
                self.assertTrue((project.root / "README.md").is_file())
                if template.steps:
                    # Compiled templates produce their entry point during the build.
                    self.assertIn(template.entry, template.artifacts.values())
                else:
                    entry = project.root / template.entry
                    self.assertTrue(entry.is_file(), template.entry)
                    self.assertTrue(entry.stat().st_mode & 0o111, f"{template.entry} is not executable")
                self.assertIn(app_id, (project.root / "MANIFEST.json").read_text())

    def test_manifest_defaults_per_template(self):
        project, _ = self.make("python-cli", "cli")
        manifest = generate_manifest(project)
        self.assertEqual(manifest["runtimes"], [])
        self.assertTrue(manifest["entry"]["terminal"])
        self.assertFalse(manifest["permissions"]["network"])

        web, _ = self.make("web-wrapper", "web")
        web_manifest = generate_manifest(web)
        self.assertTrue(web_manifest["permissions"]["network"])
        self.assertEqual(web_manifest["runtimes"], ["org.zaod.runtime.pyside6"])
        self.assertFalse(web_manifest["entry"]["terminal"])

    def test_manifest_has_no_timestamp_so_builds_repeat(self):
        project, _ = self.make("python-cli", "repeat")
        self.assertNotIn("built_at", generate_manifest(project))

    def test_invalid_id_is_refused_early(self):
        with self.assertRaises(ProjectError) as caught:
            scaffold("python-cli", self.tmp / "bad", "Not_A_Reverse_DNS", "Bad")
        self.assertIn("invalid app id", str(caught.exception))

    def test_unknown_template_lists_the_real_ones(self):
        with self.assertRaises(ProjectError) as caught:
            scaffold("cobol", self.tmp / "x", "org.zaodstudio.x", "X")
        self.assertIn("c-cmake", str(caught.exception))

    def test_non_empty_destination_needs_force(self):
        target = self.tmp / "occupied"
        (target / "keep").mkdir(parents=True)
        with self.assertRaises(ProjectError):
            scaffold("shell", target, "org.zaodstudio.occupied", "Occupied")


class BuildTests(StudioTest):
    def test_every_template_builds_and_verifies(self):
        for template_name in TEMPLATES:
            missing = tool_missing(template_name)
            if missing:
                self.skipTest(f"{missing} is not installed for {template_name}")
            with self.subTest(template=template_name):
                project, app_id = self.make(template_name)
                result = build_project(project.root, level=2)
                self.assertTrue(result.package.is_file())
                self.assertEqual(result.manifest["id"], app_id)
                verified = self.verify(result.package)
                self.assertEqual(verified.manifest.id, app_id)
                self.assertIn(project.entry, verified.checksums)

    def test_builds_are_reproducible(self):
        project, _ = self.make("python-cli", "repeatable")
        first = build_project(project.root, level=2)
        second = build_project(project.root, output=self.tmp / "second.zaod", level=2)
        self.assertEqual(first.sha256, second.sha256)

    def test_compiled_template_ships_a_binary(self):
        if tool_missing("c-cmake"):
            self.skipTest("cmake or a C compiler is missing")
        project, _ = self.make("c-cmake", "ctool")
        result = build_project(project.root, level=2)
        entry = project.root / "payload" / "bin" / "app"
        self.assertFalse(entry.exists(), "the compiled binary must live in the build, not the project")
        # The package carries the compiled binary, not the C source.
        verified = self.verify(result.package)
        self.assertIn("payload/bin/app", verified.checksums)
        self.assertNotIn("src/main.c", verified.checksums)

    def test_broken_manifest_fails_without_a_package(self):
        project, _ = self.make("python-cli", "broken")
        data = json.loads((project.root / "zaod.project.json").read_text())
        data["version"] = "1.0"  # not semver
        (project.root / "zaod.project.json").write_text(json.dumps(data), encoding="utf-8")
        output = self.tmp / "should-not-exist.zaod"
        with self.assertRaises(ProjectError) as caught:
            build_project(project.root, output=output, level=2)
        self.assertIn("version", str(caught.exception).lower())
        self.assertFalse(output.exists())

    def test_missing_entry_fails_with_a_precise_error(self):
        project, _ = self.make("python-cli", "noentry")
        (project.root / "payload" / "main.py").unlink()
        with self.assertRaises(ProjectError) as caught:
            build_project(project.root, level=2)
        self.assertIn("payload/main.py", str(caught.exception))

    def test_signed_build_is_verified_by_the_keyring(self):
        project, _ = self.make("shell", "signed")
        private_key, public_key = developer_keys(self.tmp / "home")
        result = build_project(project.root, private_key=private_key, level=2)
        zaod_paths.Paths().keys_dir.mkdir(parents=True, exist_ok=True)
        keys.trust_public_key(zaod_paths.Paths().keys_dir, keys.parse_public_key(public_key))
        verified = install.verify_package(zaod_paths.Paths(), result.package)
        self.assertEqual(verified.key_id, key_id_of(private_key))

    def test_shell_template_runs(self):
        if tool_missing("shell"):
            self.skipTest("bash is missing")
        project, _ = self.make("shell", "runshell")
        result = build_project(project.root, level=2)
        environment = dict(os.environ, ZAOD_ROOT=str(self.root))
        zaod = str(REPO_ROOT / "zaod" / "bin" / "zaod")
        install_result = __import__("subprocess").run(
            [zaod, "install", "--allow-unsigned", str(result.package)],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        self.assertEqual(install_result.returncode, 0, install_result.stderr)

    def test_studio_project_roundtrip(self):
        project, app_id = self.make("python-qt", "editme")
        project.data["version"] = "0.2.0"
        project.write_source("payload/main.py", "# edited\n")
        project.save()
        reloaded = Project.load(project.root)
        self.assertEqual(reloaded.version, "0.2.0")
        self.assertEqual(reloaded.read_source("payload/main.py"), "# edited\n")
        self.assertEqual(reloaded.manifest()["version"], "0.2.0")
        self.assertEqual(reloaded.id, app_id)


class DeveloperKeyTests(StudioTest):
    def test_keys_are_created_once_under_the_home_directory(self):
        home = self.tmp / "developer"
        private_key, public_key = developer_keys(home)
        self.assertTrue(private_key.is_file())
        self.assertTrue(public_key.is_file())
        self.assertEqual(private_key.stat().st_mode & 0o777, 0o600)
        self.assertIn(".zaod/data/org.zaod.studio/keys", str(private_key))

        again_private, _again_public = developer_keys(home)
        self.assertEqual(private_key, again_private)
        self.assertEqual(private_key.read_text(), again_private.read_text())
        self.assertEqual(key_id_of(private_key), key_id_of(again_private))


if __name__ == "__main__":
    unittest.main()
