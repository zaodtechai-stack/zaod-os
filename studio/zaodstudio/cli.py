"""`zaod-studio` command line: scaffold, build, verify and run projects."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .project import (
    ProjectError,
    build_project,
    developer_keys,
    run_package,
    scaffold,
)
from .templates import TEMPLATES


def command_new(arguments) -> int:
    project = scaffold(
        arguments.template,
        Path(arguments.folder),
        arguments.app_id,
        arguments.name,
        version=arguments.version,
    )
    print(f"created {project.id} at {project.root}")
    print(f"  template: {project.template.name}")
    print(f"  entry:    {project.entry}")
    return 0


def command_build(arguments) -> int:
    private_key = Path(arguments.key) if arguments.key else None
    if arguments.sign:
        private_key, _public = developer_keys(Path(arguments.home) if arguments.home else None)
    result = build_project(
        Path(arguments.project),
        private_key=private_key,
        output=Path(arguments.out) if arguments.out else None,
        level=arguments.level,
    )
    for line in result.log:
        print(line)
    print(f"package {result.package}")
    print(f"sha256  {result.sha256}")
    return 0


def command_verify(arguments) -> int:
    from zaodlib import install
    from zaodlib import paths as zaod_paths

    verified = install.verify_package(zaod_paths.Paths(), Path(arguments.package), allow_unsigned=not arguments.strict)
    print(f"ok {verified.manifest.id} {verified.manifest.version} ({len(verified.checksums)} files)")
    print(f"signed by {verified.key_id}" if verified.signed else "unsigned developer package")
    return 0


def command_run(arguments) -> int:
    completed = run_package(Path(arguments.package), arguments.app_id, Path(arguments.root) if arguments.root else None)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def command_list(arguments) -> int:
    for name, template in TEMPLATES.items():
        print(f"{name:14s} {template.language:8s} {template.summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zaod-studio", description="Create and build .zaod projects")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new = subparsers.add_parser("new", help="scaffold a project from a template")
    new.add_argument("template", choices=sorted(TEMPLATES))
    new.add_argument("folder")
    new.add_argument("--id", dest="app_id", required=True, help="reverse-DNS app id")
    new.add_argument("--name")
    new.add_argument("--version", default="0.1.0")
    new.set_defaults(handler=command_new)

    build = subparsers.add_parser("build", help="build and package a project")
    build.add_argument("project")
    build.add_argument("--key", help="Ed25519 private key to sign with")
    build.add_argument("--sign", action="store_true", help="sign with the developer key in your home directory")
    build.add_argument("--home", help="home directory holding the developer key")
    build.add_argument("--out", help="output .zaod path")
    build.add_argument("--level", type=int, default=12)
    build.set_defaults(handler=command_build)

    verify = subparsers.add_parser("verify", help="verify a built package")
    verify.add_argument("package")
    verify.add_argument("--strict", action="store_true", help="require a trusted signature")
    verify.set_defaults(handler=command_verify)

    run = subparsers.add_parser("run", help="install into a development root and run")
    run.add_argument("package")
    run.add_argument("--id", dest="app_id", required=True)
    run.add_argument("--root")
    run.set_defaults(handler=command_run)

    listing = subparsers.add_parser("templates", help="list the available templates")
    listing.set_defaults(handler=command_list)

    arguments = parser.parse_args(argv)
    try:
        return arguments.handler(arguments)
    except ProjectError as error:
        print(f"zaod-studio: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
