"""Signatures, the installed database, the installer and the CLI."""

from __future__ import annotations

import json

import pytest
from conftest import make_source, manifest_document

from zaod import build as build_mod
from zaod import cli, db, installer, manifest, sandbox, signature
from zaod.errors import InstallError, PackageError, SandboxError, SignatureError


class TestSignature:
    def test_sign_and_verify_round_trip(self, signing_key):
        private, public = signing_key
        document = signature.signing_document(b'{"a":1}\n', b"sha256:aa 1 payload/a\n")
        assert b"zaod-format-v1" in document
        signed = signature.sign_package(b'{"a":1}\n', b"sha256:aa 1 payload/a\n", private)
        signature.verify_package_signature(
            manifest_bytes=b'{"a":1}\n',
            checksums_bytes=b"sha256:aa 1 payload/a\n",
            signature=signed,
            public_key=public,
        )

    def test_signature_is_deterministic(self, signing_key):
        private, _public = signing_key
        first = signature.sign_package(b"{}\n", b"", private)
        second = signature.sign_package(b"{}\n", b"", private)
        assert first == second

    def test_wrong_key_fails(self, signing_key):
        private, _public = signing_key
        _, other_public = signature.generate_keypair(seed=bytes(range(32, 64)))
        signed = signature.sign_package(b"{}\n", b"", private)
        with pytest.raises(SignatureError):
            signature.verify_package_signature(
                manifest_bytes=b"{}\n", checksums_bytes=b"", signature=signed, public_key=other_public
            )

    def test_tampered_manifest_fails(self, signing_key):
        private, public = signing_key
        signed = signature.sign_package(b"{}\n", b"", private)
        with pytest.raises(SignatureError):
            signature.verify_package_signature(
                manifest_bytes=b'{"a":2}\n', checksums_bytes=b"", signature=signed, public_key=public
            )

    def test_tampered_checksums_fail(self, signing_key):
        private, public = signing_key
        signed = signature.sign_package(b"{}\n", b"", private)
        with pytest.raises(SignatureError):
            signature.verify_package_signature(
                manifest_bytes=b"{}\n",
                checksums_bytes=b"sha256:bb 1 payload/a\n",
                signature=signed,
                public_key=public,
            )

    def test_key_id_is_sixteen_hex_characters(self, signing_key):
        _private, public = signing_key
        key_id = signature.key_id_for(public)
        assert len(key_id) == 16
        assert all(character in "0123456789abcdef" for character in key_id)

    def test_fingerprint_is_grouped(self, signing_key):
        _private, public = signing_key
        key = signature.Key(key_id=signature.key_id_for(public), public_key=public, source="test")
        assert key.fingerprint.count(":") == 3

    def test_trust_store_add_and_get(self, tmp_path, signing_key):
        _private, public = signing_key
        store = signature.TrustStore(tmp_path)
        key = store.add(public)
        assert store.get(key.key_id) is not None
        assert store.get(key.key_id).public_key == public

    def test_trust_store_remove(self, tmp_path, signing_key):
        _private, public = signing_key
        store = signature.TrustStore(tmp_path)
        key = store.add(public)
        store.remove(key.key_id)
        assert store.get(key.key_id) is None

    def test_trust_store_require_reports_unknown_key(self, tmp_path):
        store = signature.TrustStore(tmp_path)
        with pytest.raises(SignatureError):
            store.require("0123456789abcdef")

    def test_generate_keypair_honours_the_seed(self):
        first = signature.generate_keypair(seed=bytes(range(32)))
        second = signature.generate_keypair(seed=bytes(range(32)))
        assert first == second


class TestDatabase:
    def test_empty_load(self, target_root):
        database = db.Database(target_root)
        assert database.load() == {}

    def test_save_and_load_round_trip(self, target_root):
        database = db.Database(target_root)
        database.load()
        database.put(
            db.InstalledPackage(
                id="os.zaod.notes",
                version="1.0.0",
                kind="app",
                name="Notes",
                installed_at="2026-01-01T00:00:00Z",
                files=[("notes", 12)],
            )
        )
        database.save()
        again = db.Database(target_root)
        again.load()
        assert again.require("os.zaod.notes").version == "1.0.0"
        assert again.require("os.zaod.notes").files == [["notes", 12]]

    def test_database_is_written_as_json(self, target_root):
        database = db.Database(target_root)
        database.load()
        database.save()
        document = json.loads((target_root / db.DB_RELATIVE_PATH).read_text())
        assert document["format"] == db.DB_FORMAT

    def test_corrupt_database_raises(self, target_root):
        path = target_root / db.DB_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        with pytest.raises(PackageError):
            db.Database(target_root).load()

    def test_wrong_format_raises(self, target_root):
        path = target_root / db.DB_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"format": 99, "packages": []}))
        with pytest.raises(PackageError):
            db.Database(target_root).load()

    def test_require_missing_package_raises(self, target_root):
        with pytest.raises(PackageError):
            db.Database(target_root).require("os.zaod.absent")


class TestInstaller:
    def test_refuses_an_unsigned_package_by_default(self, unsigned_package, target_root):
        with pytest.raises(SignatureError):
            installer.Installer(target_root).install(unsigned_package)

    def test_installs_an_unsigned_package_when_allowed(self, unsigned_package, target_root):
        result = installer.Installer(target_root, allow_unsigned=True).install(unsigned_package)
        assert result.action == "installed"
        assert result.files >= 2
        assert not result.signed

    def test_files_land_in_the_version_directory(self, unsigned_package, target_root):
        installer.Installer(target_root, allow_unsigned=True).install(unsigned_package)
        installed = target_root / installer.APPS_DIR / "os.zaod.notes" / "1.0.0" / "payload/notes"
        assert installed.is_file()
        assert "notes" in installed.read_text()

    def test_current_symlink_points_at_the_version(self, unsigned_package, target_root):
        installer.Installer(target_root, allow_unsigned=True).install(unsigned_package)
        link = target_root / installer.APPS_DIR / "os.zaod.notes" / "current"
        assert link.is_symlink()
        assert link.resolve() == (target_root / installer.APPS_DIR / "os.zaod.notes" / "1.0.0").resolve()

    def test_desktop_entry_is_written(self, unsigned_package, target_root):
        installer.Installer(target_root, allow_unsigned=True).install(unsigned_package)
        entry = target_root / installer.APPLICATIONS_DIR / "os.zaod.notes.desktop"
        text = entry.read_text()
        assert "[Desktop Entry]" in text
        assert "X-Zaod-Package=os.zaod.notes" in text
        assert "Exec=" in text

    def test_database_records_the_install(self, unsigned_package, target_root):
        installer.Installer(target_root, allow_unsigned=True).install(unsigned_package)
        records = installer.list_installed(target_root)
        assert [record.id for record in records] == ["os.zaod.notes"]

    def test_reinstall_reports_reinstalled(self, unsigned_package, target_root):
        engine = installer.Installer(target_root, allow_unsigned=True)
        engine.install(unsigned_package)
        again = engine.install(unsigned_package)
        assert again.action == "reinstalled"

    def test_upgrade_records_the_previous_version(self, tmp_path, unsigned_package, target_root):
        engine = installer.Installer(target_root, allow_unsigned=True)
        engine.install(unsigned_package)
        source = make_source(tmp_path / "source-2", manifest=manifest_document(version="1.1.0"))
        upgraded = build_mod.build_package(source, tmp_path / "notes-1.1.0.zaod")
        result = engine.install(upgraded)
        assert result.action == "updated"
        assert result.previous_version == "1.0.0"
        assert result.version == "1.1.0"
        assert engine.database.require("os.zaod.notes").version == "1.1.0"

    def test_downgrade_is_refused(self, tmp_path, unsigned_package, target_root):
        source = make_source(tmp_path / "source-new", manifest=manifest_document(version="2.0.0"))
        newer = build_mod.build_package(source, tmp_path / "new.zaod")
        engine = installer.Installer(target_root, allow_unsigned=True)
        engine.install(newer)
        with pytest.raises(InstallError):
            engine.install(unsigned_package)

    def test_downgrade_is_allowed_when_asked(self, tmp_path, unsigned_package, target_root):
        source = make_source(tmp_path / "source-new2", manifest=manifest_document(version="2.0.0"))
        newer = build_mod.build_package(source, tmp_path / "new2.zaod")
        engine = installer.Installer(target_root, allow_unsigned=True)
        engine.install(newer)
        result = engine.install(unsigned_package, allow_downgrade=True)
        assert result.version == "1.0.0"

    def test_min_os_is_enforced(self, tmp_path, target_root):
        source = make_source(
            tmp_path / "future", manifest=manifest_document(version="1.0.0", min_os="9.0.0")
        )
        package = build_mod.build_package(source, tmp_path / "future.zaod")
        with pytest.raises(InstallError):
            installer.Installer(target_root, allow_unsigned=True).install(package)

    def test_remove_cleans_up(self, unsigned_package, target_root):
        engine = installer.Installer(target_root, allow_unsigned=True)
        engine.install(unsigned_package)
        result = engine.remove("os.zaod.notes")
        assert result.action == "removed"
        assert not (target_root / installer.APPS_DIR / "os.zaod.notes").exists()
        assert not (target_root / installer.APPLICATIONS_DIR / "os.zaod.notes.desktop").exists()
        assert installer.list_installed(target_root) == []

    def test_remove_of_absent_package_raises(self, target_root):
        with pytest.raises(PackageError):
            installer.Installer(target_root).remove("os.zaod.absent")

    def test_signed_install_records_the_signing_key(self, signed_package, target_root, trust_store):
        engine = installer.Installer(target_root, trust=trust_store)
        result = engine.install(signed_package)
        assert result.signed
        assert result.key_id == trust_store.keys()[0].key_id

    def test_signature_from_an_untrusted_key_is_refused(self, signed_package, target_root, tmp_path):
        empty_trust = signature.TrustStore(tmp_path / "empty-root")
        with pytest.raises(SignatureError):
            installer.Installer(target_root, trust=empty_trust).install(signed_package)

    def test_failed_install_leaves_nothing_behind(self, tmp_path, unsigned_package, target_root):
        document = manifest_document(version="3.0.0", min_os="99.0.0")
        broken = build_mod.build_package(
            make_source(tmp_path / "broken-src", manifest=document), tmp_path / "broken.zaod"
        )
        engine = installer.Installer(target_root, allow_unsigned=True)
        with pytest.raises(InstallError):
            engine.install(broken)
        assert not (target_root / installer.APPS_DIR / "os.zaod.notes").exists()
        assert installer.list_installed(target_root) == []


class TestSandbox:
    def _permissions(self, **overrides):
        document = manifest_document(permissions={"network": overrides.get("network", False)})
        return manifest.validate_document(document).permissions

    def test_network_is_unshared_by_default(self):
        arguments = sandbox.build_arguments(
            command=["notes"], data_dir="/home/user/.local/share/zaod/os.zaod.notes",
            permissions=self._permissions(),
        )
        assert "--unshare-net" in arguments
        assert "--share-net" not in arguments
        assert arguments[0] == sandbox.BWRAP
        assert arguments[-1] == "notes"

    def test_network_permission_shares_the_network(self):
        arguments = sandbox.build_arguments(
            command=["notes"], data_dir="/data", permissions=self._permissions(network=True)
        )
        assert "--share-net" in arguments

    def test_die_with_parent_is_always_set(self):
        arguments = sandbox.build_arguments(
            command=["notes"], data_dir="/data", permissions=self._permissions()
        )
        assert "--die-with-parent" in arguments

    def test_empty_command_is_refused(self):
        with pytest.raises(SandboxError):
            sandbox.build_arguments(command=[], data_dir="/data", permissions=self._permissions())

    def test_describe_uses_the_permission_summary(self):
        assert sandbox.describe(self._permissions())


class TestCli:
    def test_version(self, capsys):
        assert cli.main(["version"]) == 0
        assert "zaod" in capsys.readouterr().out

    def test_list_when_empty(self, target_root, capsys):
        assert cli.main(["--root", str(target_root), "list"]) == 0
        assert "no packages are installed" in capsys.readouterr().out

    def test_install_then_list(self, unsigned_package, target_root, capsys):
        assert cli.main(["--root", str(target_root), "install", str(unsigned_package), "--allow-unsigned"]) == 0
        assert cli.main(["--root", str(target_root), "list"]) == 0
        assert "os.zaod.notes" in capsys.readouterr().out

    def test_install_without_allow_unsigned_fails(self, unsigned_package, target_root, capsys):
        code = cli.main(["--root", str(target_root), "install", str(unsigned_package)])
        assert code != 0
        assert "signature" in capsys.readouterr().err.lower()

    def test_verify_reports_checksums(self, unsigned_package, target_root, capsys):
        code = cli.main(["--root", str(target_root), "verify", str(unsigned_package), "--allow-unsigned"])
        assert code == 0
        assert "checksums: ok" in capsys.readouterr().out

    def test_info_prints_the_manifest(self, unsigned_package, capsys):
        assert cli.main(["info", str(unsigned_package)]) == 0
        output = capsys.readouterr().out
        assert "os.zaod.notes" in output
        assert "1.0.0" in output

    def test_keys_add_and_list(self, target_root, signing_key, capsys):
        _private, public = signing_key
        assert cli.main(["--root", str(target_root), "keys", "add", public.hex()]) == 0
        assert cli.main(["--root", str(target_root), "keys", "list"]) == 0
        assert signature.key_id_for(public) in capsys.readouterr().out

    def test_pack_writes_an_archive(self, tmp_path, capsys):
        source = make_source(tmp_path / "cli-source")
        output = tmp_path / "cli.zaod"
        assert cli.main(["pack", str(source), "-o", str(output)]) == 0
        assert output.is_file()
        assert "wrote" in capsys.readouterr().out
