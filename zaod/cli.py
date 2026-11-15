"""The ``zaod`` command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from . import archive as archive_mod
from . import build as build_mod
from . import installer as installer_mod
from . import signature as signature_mod
from .errors import ZaodError

PROGRAM = "zaod"


def _installer(args) -> installer_mod.Installer:
    return installer_mod.Installer(
        args.root,
        allow_unsigned=getattr(args, "allow_unsigned", False),
    )


def cmd_install(args) -> int:
    result = _installer(args).install(
        args.package, allow_downgrade=getattr(args, "allow_downgrade", False)
    )
    print(result.summary())
    if result.signed:
        print(f"signed by key {result.key_id}")
    else:
        print("warning: this package was not signed")
    return 0


def cmd_remove(args) -> int:
    result = _installer(args).remove(args.package_id, force=args.force)
    print(f"removed {result.package_id} {result.version}")
    return 0


def cmd_list(args) -> int:
    records = installer_mod.list_installed(args.root)
    if not records:
        print("no packages are installed")
        return 0
    width = max(len(record.id) for record in records)
    for record in records:
        print(f"{record.id.ljust(width)}  {record.version:<12}  {record.name}")
    print(f"\n{len(records)} package(s) installed below {Path(args.root).resolve()}")
    return 0


def cmd_info(args) -> int:
    contents = archive_mod.inspect(args.package)
    try:
        manifest = contents.manifest
        print(f"id:          {manifest.id}")
        print(f"name:        {manifest.name}")
        print(f"version:     {manifest.version}")
        print(f"kind:        {manifest.kind}")
        print(f"arch:        {manifest.arch}")
        print(f"min os:      {manifest.min_os}")
        print(f"license:     {manifest.license}")
        print(f"author:      {manifest.author.name} <{manifest.author.email}>")
        print(f"entry:       {' '.join([manifest.entry.exec] + list(manifest.entry.args))}")
        print(f"members:     {len(contents.members)}")
        print(f"signed:      {'yes' if contents.signature else 'no'}")
        if manifest.categories:
            print(f"categories:  {', '.join(manifest.categories)}")
        summary = manifest.permissions.summary() if hasattr(manifest.permissions, "summary") else ""
        if summary:
            print(f"permissions: {summary}")
    finally:
        archive_mod.close_contents(contents)
    return 0


def cmd_verify(args) -> int:
    contents = archive_mod.inspect(args.package)
    try:
        archive_mod.verify_checksums(contents)
        print(f"checksums: ok ({len(contents.checksums)} files)")
        if contents.signature is None:
            print("signature: none (unsigned package)")
            return 0 if args.allow_unsigned else 1
        import tarfile

        with tarfile.open(contents.tar_path, mode="r:") as archive:
            manifest_bytes = archive.extractfile(archive_mod.MANIFEST_NAME).read()
            checksums_bytes = archive.extractfile(archive_mod.CHECKSUMS_NAME).read()
        key = signature_mod.verify_with_store(
            manifest_bytes=manifest_bytes,
            checksums_bytes=checksums_bytes,
            signature=contents.signature,
            trust=signature_mod.TrustStore(args.root),
        )
        print(f"signature: ok, trusted key {key.key_id} ({key.fingerprint})")
    finally:
        archive_mod.close_contents(contents)
    return 0


def cmd_pack(args) -> int:
    private_key = None
    if args.sign_with:
        raw = Path(args.sign_with).read_bytes().strip()
        private_key = bytes.fromhex(raw.decode("ascii"))
    output = build_mod.build_package(args.source, args.output, private_key=private_key)
    print(f"wrote {output} ({output.stat().st_size} bytes)")
    return 0


def cmd_keys(args) -> int:
    trust = signature_mod.TrustStore(args.root)
    if args.keys_action == "list":
        keys = trust.keys()
        if not keys:
            print(f"no trusted keys in {trust.directory}")
            return 0
        for key in keys:
            print(f"{key.key_id}  {key.fingerprint}  {key.source}")
        return 0
    if args.keys_action == "add":
        source = Path(args.key)
        if source.is_file():
            public_key = bytes.fromhex(source.read_text(encoding="ascii").strip())
        else:
            public_key = bytes.fromhex(args.key)
        key = trust.add(public_key)
        print(f"trusted {key.key_id} ({key.fingerprint})")
        return 0
    if args.keys_action == "remove":
        trust.remove(args.key)
        print(f"removed trusted key {args.key}")
        return 0
    raise ZaodError(f"unknown keys action {args.keys_action}")


def cmd_run(args) -> int:
    from . import sandbox

    record = installer_mod.require_installed(args.root, args.package_id)
    app_dir = Path(args.root) / installer_mod.APPS_DIR / record.id / "current"
    if not app_dir.exists():
        raise ZaodError(f"{record.id} has no installed payload")
    arguments = sandbox.build_arguments(
        command=[args.command or "run"] + list(args.rest),
        data_dir=str(Path(args.root) / "home/user/.local/share/zaod" / record.id),
        permissions=_permissions_stub(),
    )
    print(" ".join(arguments))
    return 0


def _permissions_stub():
    """Permissions are read from the installed manifest in a later revision."""

    class _Permissions:
        network = False
        notifications = False
        tray = False
        devices = ()

        def names(self):
            return []

    return _Permissions()


def cmd_version(args) -> int:
    print(f"{PROGRAM} {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM, description="Zaod OS package manager")
    parser.add_argument("--root", default="/", help="target root (default /)")
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    install = subparsers.add_parser("install", help="install or update a .zaod package")
    install.add_argument("package")
    install.add_argument("--allow-unsigned", action="store_true")
    install.add_argument("--allow-downgrade", action="store_true")
    install.set_defaults(handler=cmd_install)

    remove = subparsers.add_parser("remove", help="remove an installed package")
    remove.add_argument("package_id")
    remove.add_argument("--force", action="store_true")
    remove.set_defaults(handler=cmd_remove)

    listing = subparsers.add_parser("list", help="list installed packages")
    listing.set_defaults(handler=cmd_list)

    info = subparsers.add_parser("info", help="show a package's manifest")
    info.add_argument("package")
    info.set_defaults(handler=cmd_info)

    verify = subparsers.add_parser("verify", help="verify checksums and signature")
    verify.add_argument("package")
    verify.add_argument("--allow-unsigned", action="store_true")
    verify.set_defaults(handler=cmd_verify)

    pack = subparsers.add_parser("pack", help="build a .zaod package")
    pack.add_argument("source")
    pack.add_argument("-o", "--output", required=True)
    pack.add_argument("--sign-with", metavar="SEED_FILE")
    pack.set_defaults(handler=cmd_pack)

    keys = subparsers.add_parser("keys", help="manage the trust store")
    keys.add_argument("keys_action", choices=("list", "add", "remove"))
    keys.add_argument("key", nargs="?")
    keys.set_defaults(handler=cmd_keys)

    run = subparsers.add_parser("run", help="run an installed application sandboxed")
    run.add_argument("package_id")
    run.add_argument("--command")
    run.add_argument("rest", nargs=argparse.REMAINDER)
    run.set_defaults(handler=cmd_run)

    version = subparsers.add_parser("version", help="print the version")
    version.set_defaults(handler=cmd_version)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ZaodError as exc:
        print(f"{PROGRAM}: {exc}", file=sys.stderr)
        return getattr(exc, "exit_code", 1)
    except BrokenPipeError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
