import tempfile
import unittest
from pathlib import Path

import support
from zaodlib import sandbox
from zaodlib.manifest import parse_manifest


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.paths = support.make_paths(self.tmp)
        self.paths.app_current("org.zaod.hello").parent.mkdir(parents=True, exist_ok=True)

    def plan(self, **overrides):
        manifest = parse_manifest(support.manifest_dict(**overrides))
        return sandbox.build_plan(self.paths, manifest, binary="bwrap")

    def test_no_network_permission_blocks_network(self):
        plan = self.plan()
        self.assertNotIn("--share-net", plan.argv)
        self.assertNotIn("none", plan.describe())

    def test_network_permission_shares_network(self):
        plan = self.plan(permissions={"network": True, "filesystem": [], "devices": []})
        self.assertIn("--share-net", plan.argv)
        self.assertIn("network access", plan.permissions)

    def test_sandbox_isolation_flags(self):
        plan = self.plan()
        for flag in ("--unshare-all", "--die-with-parent", "--new-session", "--clearenv"):
            self.assertIn(flag, plan.argv)
        self.assertIn("/proc", plan.argv)

    def test_only_declared_filesystem_paths_bound(self):
        plan = self.plan()
        binds = [item for item in plan.argv if item.endswith("Documents")]
        self.assertTrue(binds)
        self.assertNotIn("Downloads", " ".join(plan.argv))

    def test_home_permission_binds_home(self):
        plan = self.plan(permissions={"network": False, "filesystem": ["home"], "devices": []})
        self.assertIn(str(self.paths.user_data_dir.parent.parent), plan.argv)

    def test_device_permissions(self):
        plan = self.plan(permissions={"network": False, "filesystem": [], "devices": ["dri", "audio"]})
        self.assertIn("/dev/dri", plan.argv)
        self.assertTrue(any("pipewire" in item for item in plan.argv))

    def test_entry_command_is_last(self):
        plan = self.plan()
        separator = plan.argv.index("--")
        command = plan.argv[separator + 1:]
        self.assertTrue(command[0].endswith("payload/bin/hello"))

    def test_extra_args_are_appended(self):
        manifest = parse_manifest(support.manifest_dict())
        plan = sandbox.build_plan(self.paths, manifest, extra_args=["file.txt"], binary="bwrap")
        self.assertEqual(plan.argv[-1], "file.txt")

    def test_manifest_env_is_set(self):
        plan = self.plan(permissions={"network": False, "filesystem": [], "devices": [], "env": {"ZAOD_MODE": "lite"}})
        self.assertIn("ZAOD_MODE", plan.argv)
        self.assertIn("lite", plan.argv)

    def test_permission_summary_text(self):
        manifest = parse_manifest(support.manifest_dict(permissions={"network": True, "filesystem": ["home"], "devices": ["dri"]}))
        summary = sandbox.permission_summary(manifest)
        self.assertEqual(summary, ["network access", "files: home", "device: dri"])


if __name__ == "__main__":
    unittest.main()
