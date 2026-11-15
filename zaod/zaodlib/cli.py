"""The ``zaod`` command line interface."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, keys, pack, repo, sandbox, util
from .errors import SandboxError, StateError, UsageError, ZaodError
from .install import Installer, verify_package
from .manifest import Manifest, load_manifest
from .paths import Paths

PRIVILEGED = {"install", "remove", "update", "gc", "repo-add", "repo-remove", "repo-sync", "key-trust"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="zaod", description="Zaod package manager and store client")
    parser.add_argument("--version", action="version", version=f"zaod {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install a package file or store app")
    install_parser.add_argument("target", help="path to a .zaod file, or an app id such as org.zaod.hello")
    install_parser.add_argument("--version", dest="package_version", help="store version to install")
    install_parser.add_argument("--allow-unsigned", action="store_true", help="accept an unsigned developer package")
    install_parser.add_argument("--force", action="store_true", help="reinstall or force a downgrade")
    install_parser.set_defaults(handler=cmd_install)

    remove_parser = subparsers.add_parser("remove", help="uninstall an app")
    remove_parser.add_argument("app_id")
    remove_parser.add_argument("--purge", action="store_true", help="also delete the app's user data")
    remove_parser.set_defaults(handler=cmd_remove)

    subparsers.add_parser("list", help="list installed apps").set_defaults(handler=cmd_list)

    info_parser = subparsers.add_parser("info", help="show details for an installed app or a package file")
    info_parser.add_argument("target")
    info_parser.add_argument("--file", action="store_true", help="treat the target as a .zaod file")
    info_parser.set_defaults(handler=cmd_info)

    verify_parser = subparsers.add_parser("verify", help="verify a package file without installing it")
    verify_parser.add_argument("package")
    verify_parser.add_argument("--allow-unsigned", action="store_true")
    verify_parser.set_defaults(handler=cmd_verify)

    update_parser = subparsers.add_parser("update", help="update installed apps from the store")
    update_parser.add_argument("app_ids", nargs="*", help="apps to update (default: all)")
    update_parser.add_argument("--allow-unsigned", action="store_true")
    update_parser.set_defaults(handler=cmd_update)

    search_parser = subparsers.add_parser("search", help="search the store index")
    search_parser.add_argument("query", nargs="?", default="")
    search_parser.add_argument("--refresh", action="store_true", help="sync repositories before searching")
    search_parser.set_defaults(handler=cmd_search)

    pack_parser = subparsers.add_parser("pack", help="build a .zaod package from a project directory")
    pack_parser.add_argument("source")
    pack_parser.add_argument("-o", "--output", required=True)
    pack_parser.add_argument("--manifest", help="manifest file outside the source tree")
    pack_parser.add_argument("--key", help="private key used to sign the package")
    pack_parser.add_argument("--level", type=int, default=19, help="zstd compression level")
    pack_parser.set_defaults(handler=cmd_pack)

    sign_parser = subparsers.add_parser("sign", help="sign an existing .zaod package")
    sign_parser.add_argument("package")
    sign_parser.add_argument("--key", required=True)
    sign_parser.set_defaults(handler=cmd_sign)

    run_parser = subparsers.add_parser("run", help="run an installed app inside the sandbox")
    run_parser.add_argument("app_id")
    run_parser.add_argument("--no-sandbox", action="store_true", help="run without bubblewrap (debugging only)")
    run_parser.add_argument("--print-command", action="store_true", help="show the sandbox command without running it")
    run_parser.add_argument("args", nargs=argparse.REMAINDER)
    run_parser.set_defaults(handler=cmd_run)

    repo_parser = subparsers.add_parser("repo", help="manage store repositories")
    repo_sub = repo_parser.add_subparsers(dest="repo_command", required=True)
    repo_add = repo_sub.add_parser("add", help="add a repository")
    repo_add.add_argument("name")
    repo_add.add_argument("url")
    repo_add.add_argument("--key", help="public key file used to verify this repository")
    repo_add.set_defaults(handler=cmd_repo_add)
    repo_list = repo_sub.add_parser("list", help="list repositories")
    repo_list.set_defaults(handler=cmd_repo_list)
    repo_remove = repo_sub.add_parser("remove", help="remove a repository")
    repo_remove.add_argument("name")
    repo_remove.set_defaults(handler=cmd_repo_remove)
    repo_sync = repo_sub.add_parser("sync", help="download and verify repository indexes")
    repo_sync.add_argument("name", nargs="?")
    repo_sync.set_defaults(handler=cmd_repo_sync)
    repo_build = repo_sub.add_parser("build", help="build and sign an index for a directory of packages")
    repo_build.add_argument("directory")
    repo_build.add_argument("--name", default="core")
    repo_build.add_argument("--key", required=True)
    repo_build.set_defaults(handler=cmd_repo_build)

    key_parser = subparsers.add_parser("key", help="manage signing keys")
    key_sub = key_parser.add_subparsers(dest="key_command", required=True)
    key_generate = key_sub.add_parser("generate", help="create a new signing key pair")
    key_generate.add_argument("--out", required=True, help="path for the private key file")
    key_generate.add_argument("--trust", action="store_true", help="also add the public key to the trust store")
    key_generate.set_defaults(handler=cmd_key_generate)
    key_trust = key_sub.add_parser("trust", help="add a public key to the trusted keyring")
    key_trust.add_argument("public_key")
    key_trust.set_defaults(handler=cmd_key_trust)
    key_list = key_sub.add_parser("list", help="list trusted keys")
    key_list.set_defaults(handler=cmd_key_list)

    gc_parser = subparsers.add_parser("gc", help="remove superseded versions and caches")
    gc_parser.set_defaults(handler=cmd_gc)
    return parser


# --------------------------------------------------------------------- helpers
def resolve_paths() -> Paths:
    return Paths()


def store_indexes(paths: Paths) -> dict[str, dict]:
    reposet = repo.RepoSet(paths)
    indexes: dict[str, dict] = {}
    for entry in reposet.repos:
        if not entry.enabled:
            continue
        try:
            indexes[entry.name] = repo.cached_index(paths, entry.name)
        except ZaodError:
            continue
    return indexes


def sync_all(paths: Paths) -> dict[str, dict]:
    reposet = repo.RepoSet(paths)
    keyring = keys.trusted_keys(paths.keys_dir)
    indexes: dict[str, dict] = {}
    for entry in reposet.repos:
        if not entry.enabled:
            continue
        indexes[entry.name] = repo.sync_repo(entry, paths, keyring)
        reposet.save()
    return indexes


def _repo_url(paths: Paths, name: str) -> str | None:
    try:
        return repo.RepoSet(paths).get(name).url
    except ZaodError:
        return None


def print_permissions(manifest: Manifest) -> None:
    summary = sandbox.permission_summary(manifest)
    print("  permissions: " + (", ".join(summary) if summary else "none"))


def escalate(args) -> int:
    """Re-run a privileged command through the helper with pkexec or sudo."""
    helper = shutil.which("zaod-priv-helper")
    if helper is None:
        raise UsageError("this command needs root; run it as root or install zaod-priv-helper")
    escalator = shutil.which("pkexec") or shutil.which("sudo")
    if escalator is None:
        raise UsageError("this command needs root and neither pkexec nor sudo is available")
    command = [escalator, helper, *sys.argv[1:]]
    return subprocess.call(command)


# -------------------------------------------------------------------- commands
def cmd_install(args) -> int:
    paths = resolve_paths()
    installer = Installer(paths)
    source = "local"
    target = args.target
    package_path = Path(target)
    repo_url = None
    if package_path.suffix != ".zaod" or not package_path.is_file():
        indexes = store_indexes(paths)
        if not indexes:
            indexes = sync_all(paths)
        entry = repo.find_package(indexes, target, args.package_version)
        package_path = repo.download_package(entry, paths, _repo_url(paths, entry["repo"]))
        source = f"repo:{entry['repo']}"
        repo_url = entry["repo"]
    result = installer.install(
        package_path,
        source=source,
        allow_unsigned=args.allow_unsigned,
        force=args.force,
    )
    manifest = result.manifest
    print(f"installed {manifest.name} {result.version} ({manifest.id})")
    if result.previous_version:
        print(f"  updated from {result.previous_version}")
    print(f"  files: {result.files}, source: {source}")
    print_permissions(manifest)
    for warning in result.warnings:
        print(f"  warning: {warning}")
    if repo_url:
        print(f"  repository: {repo_url}")
    return 0


def cmd_remove(args) -> int:
    paths = resolve_paths()
    version = Installer(paths).remove(args.app_id, purge_data=args.purge)
    print(f"removed {args.app_id} {version}")
    return 0


def cmd_list(args) -> int:
    paths = resolve_paths()
    installer = Installer(paths)
    installed = installer.installed()
    if not installed:
        print("no apps installed")
        return 0
    width = max(len(item["id"]) for item in installed)
    print(f"{'ID'.ljust(width)}  VERSION   KIND     NAME")
    for item in sorted(installed, key=lambda entry: entry["id"]):
        print(f"{item['id'].ljust(width)}  {item['version'].ljust(8)}  {item['kind'].ljust(8)} {item.get('name', '')}")
    return 0


def cmd_info(args) -> int:
    paths = resolve_paths()
    if args.file or args.target.endswith(".zaod"):
        verified = verify_package(paths, Path(args.target), allow_unsigned=True)
        manifest = verified.manifest
        print(f"id:        {manifest.id}")
        print(f"name:      {manifest.name}")
        print(f"version:   {manifest.version}")
        print(f"kind:      {manifest.kind}")
        print(f"min_os:    {manifest.min_os}")
        print(f"summary:   {manifest.summary}")
        print(f"license:   {manifest.license['spdx']}")
        print(f"signed:    {'yes, key ' + verified.key_id if verified.signed else 'no'}")
        print_permissions(manifest)
        return 0
    info = Installer(paths).info(args.target)
    for key in ("id", "name", "version", "kind", "summary", "installed_at", "source", "key_id", "license", "author"):
        if key in info:
            print(f"{(key + ':'):<14} {info[key]}")
    summary = sandbox.permission_summary(_manifest_from_info(info))
    print(f"{'permissions:':<14} {', '.join(summary) if summary else 'none'}")
    return 0


def _manifest_from_info(info: dict) -> Manifest:
    class _Shim:
        network = bool((info.get("permissions") or {}).get("network", False))
        filesystem_permissions = (info.get("permissions") or {}).get("filesystem", [])
        device_permissions = (info.get("permissions") or {}).get("devices", [])

    return _Shim()  # type: ignore[return-value]


def cmd_verify(args) -> int:
    paths = resolve_paths()
    verified = verify_package(paths, Path(args.package), allow_unsigned=args.allow_unsigned)
    manifest = verified.manifest
    print(f"OK {manifest.id} {manifest.version} ({len(verified.checksums)} files)")
    print(f"  signed by: {verified.key_id or 'unsigned (accepted with --allow-unsigned)'}")
    print_permissions(manifest)
    return 0


def cmd_update(args) -> int:
    paths = resolve_paths()
    installer = Installer(paths)
    targets = args.app_ids or installer.db.installed_ids()
    indexes = sync_all(paths)
    updated = 0
    for app_id in targets:
        current = installer.current_version(app_id)
        try:
            entry = repo.find_package(indexes, app_id)
        except ZaodError as error:
            print(f"{app_id}: {error}")
            continue
        if current and util.compare_semver(entry["version"], current) <= 0:
            print(f"{app_id}: up to date ({current})")
            continue
        package_path = repo.download_package(entry, paths, _repo_url(paths, entry["repo"]))
        result = installer.install(package_path, source=f"repo:{entry['repo']}", allow_unsigned=args.allow_unsigned)
        print(f"updated {app_id}: {current or '-'} -> {result.version}")
        updated += 1
    print(f"{updated} app(s) updated")
    return 0


def cmd_search(args) -> int:
    paths = resolve_paths()
    indexes = sync_all(paths) if args.refresh else store_indexes(paths)
    if not indexes:
        print("no store repositories configured; add one with 'zaod repo add NAME URL'")
        return 0
    results = repo.search(indexes, args.query)
    if not results:
        print("no matching packages")
        return 0
    width = max(len(item["id"]) for item in results)
    for item in results:
        print(f"{item['id'].ljust(width)}  {item['version'].ljust(8)}  {item['summary']}")
    return 0


def cmd_pack(args) -> int:
    key_path = Path(args.key) if args.key else None
    output, manifest, checksums = pack.build_package(
        Path(args.source),
        Path(args.output),
        manifest_path=Path(args.manifest) if args.manifest else None,
        private_key=key_path,
        level=args.level,
    )
    size = output.stat().st_size
    print(f"built {output} ({util.human_bytes(size)}, {len(checksums)} files)")
    print(f"  id: {manifest.id} {manifest.version}")
    print(f"  sha256: {util.sha256_file(output)}")
    print(f"  signed: {'yes' if key_path else 'no'}")
    return 0


def cmd_sign(args) -> int:
    package = pack.sign_existing(Path(args.package), Path(args.key))
    print(f"signed {package}")
    return 0


def cmd_run(args) -> int:
    paths = resolve_paths()
    installer = Installer(paths)
    record = installer.db.get(args.app_id)
    if record is None:
        raise StateError(f"{args.app_id} is not installed")
    manifest = load_manifest(paths.app_current(args.app_id) / "MANIFEST.json")
    extra = list(args.args)
    if extra and extra[0] == "--":
        extra = extra[1:]
    print_only = args.print_command or "--print-command" in extra
    extra = [item for item in extra if item != "--print-command"]
    if args.no_sandbox:
        command = [str(paths.app_current(args.app_id) / manifest.entry["exec"]), *extra]
        return subprocess.call(command)
    plan = sandbox.build_plan(
        paths,
        manifest,
        wayland_display=os.environ.get("WAYLAND_DISPLAY"),
        runtime_dir=os.environ.get("XDG_RUNTIME_DIR"),
        extra_args=extra or None,
    )
    if print_only:
        print(" ".join(plan.argv))
        return 0
    print(f"running {manifest.name} with: {plan.describe()}", file=sys.stderr)
    try:
        return subprocess.call(plan.argv)
    except FileNotFoundError as error:
        raise SandboxError(f"cannot start the sandbox: {error.filename} is missing") from error


def cmd_repo_add(args) -> int:
    paths = resolve_paths()
    key_ids: list[str] = []
    if args.key:
        public = keys.parse_public_key(Path(args.key))
        keys.trust_public_key(paths.keys_dir, public)
        key_ids.append(keys.key_id(public))
    else:
        keyring = keys.trusted_keys(paths.keys_dir)
        key_ids = sorted(keyring)
    entry = repo.Repo(name=args.name, url=args.url, key_ids=key_ids)
    repo.RepoSet(paths).add(entry)
    print(f"added repository {args.name} -> {args.url}")
    if key_ids:
        print(f"  trusted keys: {', '.join(key_ids)}")
    return 0


def cmd_repo_list(args) -> int:
    paths = resolve_paths()
    entries = repo.RepoSet(paths).repos
    if not entries:
        print("no repositories configured")
        return 0
    for entry in entries:
        state = "enabled" if entry.enabled else "disabled"
        print(f"{entry.name}  {entry.url}  ({state}, last sync: {entry.last_sync or 'never'})")
    return 0


def cmd_repo_remove(args) -> int:
    paths = resolve_paths()
    repo.RepoSet(paths).remove(args.name)
    shutil.rmtree(paths.index_cache_dir / args.name, ignore_errors=True)
    print(f"removed repository {args.name}")
    return 0


def cmd_repo_sync(args) -> int:
    paths = resolve_paths()
    reposet = repo.RepoSet(paths)
    keyring = keys.trusted_keys(paths.keys_dir)
    targets = [reposet.get(args.name)] if args.name else reposet.repos
    for entry in targets:
        index = repo.sync_repo(entry, paths, keyring)
        reposet.save()
        print(f"synced {entry.name}: {len(index['packages'])} packages")
    return 0


def cmd_repo_build(args) -> int:
    key = keys.load_private_key(Path(args.key))
    index_path, signature_path = repo.build_index(Path(args.directory), args.name, key)
    print(f"wrote {index_path} and {signature_path}")
    print(f"  key id: {key.key_id}")
    return 0


def cmd_key_generate(args) -> int:
    paths = resolve_paths()
    pair = keys.generate_keypair()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pair.export_private(), encoding="utf-8")
    out.chmod(0o600)
    print(f"private key: {out} (keep it offline)")
    print(f"public key:  {pair.key_id}")
    public_path = out.with_suffix(".pub")
    public_path.write_text(pair.export_public(), encoding="utf-8")
    print(f"public key file: {public_path}")
    if args.trust:
        keys.trust_public_key(paths.keys_dir, pair.public)
        print(f"trusted in {paths.keys_dir}")
    return 0


def cmd_key_trust(args) -> int:
    paths = resolve_paths()
    public = keys.parse_public_key(Path(args.public_key))
    path = keys.trust_public_key(paths.keys_dir, public)
    print(f"trusted key {keys.key_id(public)} -> {path}")
    return 0


def cmd_key_list(args) -> int:
    paths = resolve_paths()
    keyring = keys.trusted_keys(paths.keys_dir)
    if not keyring:
        print(f"no trusted keys in {paths.keys_dir}")
        return 0
    for key_id in sorted(keyring):
        print(key_id)
    return 0


def cmd_gc(args) -> int:
    paths = resolve_paths()
    removed = Installer(paths).gc()
    print(f"removed {len(removed)} stale path(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in PRIVILEGED:
            paths = Paths()
            if paths.installed and os.geteuid() != 0:
                return escalate(args)
        return args.handler(args)
    except ZaodError as error:
        print(f"zaod: error: {error}", file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":  # pragma: no cover - module entry point
    sys.exit(main())
