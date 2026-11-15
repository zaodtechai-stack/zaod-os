"""Zaod Studio project handling: scaffold, manifest generation, build, dev keys.

A Studio project is a directory with ``zaod.project.json`` at its root. The
manifest is generated from that file, so the two can never drift. Builds copy the
project into a staging tree, run the template's build steps there, and hand the
result to ``zaodlib.pack.build_package``, which validates the manifest, rejects
bad projects before writing any archive, and produces byte-reproducible output.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT / "zaod", Path("/usr/lib/zaod")):
    if (candidate / "zaodlib" / "__init__.py").is_file():
        sys.path.insert(0, str(candidate))
        break

from zaodlib import DEFAULT_OS_VERSION, keys, pack
from zaodlib import manifest as manifest_module
from zaodlib.errors import ZaodError

from .templates import TEMPLATES

PROJECT_FILE = "zaod.project.json"
PROJECT_FORMAT = 1
ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9][a-z0-9_-]*)+$")
IGNORED = {".git", "build", "__pycache__", ".venv", "node_modules"}
# Icon tones are colour roles, never literals: the accent family is the only
# set with a declared onAccent contrast pair, so a generated icon stays legible
# in both themes. Falls back to currentColor when the token module is absent
# (Studio run straight from a checkout rather than from a .zaod package).
ICON_TONE_ROLES = ("accent", "accentHover", "accentPressed")


class ProjectError(RuntimeError):
    """A Studio project could not be created, read or built."""


@dataclass
class BuildResult:
    package: Path
    sha256: str
    manifest: dict
    log: list = field(default_factory=list)

    @property
    def size(self) -> int:
        return self.package.stat().st_size


def _tokens():
    """The generated token module, or None when Studio runs from a checkout."""
    try:
        import zaod_tokens
    except ImportError:
        return None
    return zaod_tokens


def icon_svg(app_id: str) -> str:
    """Deterministic placeholder icon derived from the app id.

    The tile colour is a token role, never a literal, so a generated project
    icon matches the design system and stays legible in both themes.
    """
    tokens = _tokens()
    if tokens is None:
        tile, letter_colour, radius = "currentColor", "currentColor", 12
    else:
        colours = tokens.role_map("light")
        tile = colours[ICON_TONE_ROLES[sum(app_id.encode()) % len(ICON_TONE_ROLES)]]
        letter_colour = colours["onAccent"]
        radius = tokens.RADII["lg"]
    letter = app_id.split(".")[-1][:1].upper() or "Z"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        f'  <rect x="4" y="4" width="56" height="56" rx="{radius}" fill="{tile}"/>\n'
        '  <text x="32" y="42" font-family="Inter, sans-serif" font-size="28" font-weight="600" '
        f'fill="{letter_colour}" text-anchor="middle">{letter}</text>\n'
        "</svg>\n"
    )


def _template(template_name: str):
    try:
        return TEMPLATES[template_name]
    except KeyError as error:
        raise ProjectError(
            f"unknown template {template_name!r}; choose one of {', '.join(sorted(TEMPLATES))}"
        ) from error


def validate_id(app_id: str) -> str:
    if not ID_PATTERN.match(app_id):
        raise ProjectError(
            f"invalid app id {app_id!r}: use reverse-DNS lowercase such as org.example.myapp"
        )
    return app_id


@dataclass
class Project:
    """A Studio project rooted at ``root``."""

    root: Path
    data: dict

    @classmethod
    def load(cls, root: Path) -> Project:
        root = Path(root).expanduser().resolve()
        project_file = root / PROJECT_FILE
        if not project_file.is_file():
            raise ProjectError(f"{root} is not a Studio project (no {PROJECT_FILE})")
        try:
            data = json.loads(project_file.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ProjectError(f"{PROJECT_FILE} is not valid JSON: {error}") from error
        if data.get("format") != PROJECT_FORMAT:
            raise ProjectError(f"unsupported project format {data.get('format')!r}")
        for key in ("id", "name", "version", "template"):
            if not data.get(key):
                raise ProjectError(f"{PROJECT_FILE} is missing {key!r}")
        validate_id(data["id"])
        _template(data["template"])
        return cls(root=root, data=data)

    # ---- metadata -----------------------------------------------------------
    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def name(self) -> str:
        return self.data["name"]

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def template(self):
        return _template(self.data["template"])

    @property
    def entry(self) -> str:
        return self.data.get("entry") or self.template.entry

    def save(self) -> None:
        (self.root / PROJECT_FILE).write_text(
            json.dumps(self.data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    # ---- files --------------------------------------------------------------
    def source_files(self) -> list[Path]:
        files = []
        for path in sorted(self.root.rglob("*")):
            parts = set(path.relative_to(self.root).parts)
            if parts & IGNORED or path.name.endswith(".zaod"):
                continue
            if path.is_file() and path.name not in {"MANIFEST.json", "CHECKSUMS"}:
                files.append(path)
        return files

    def read_source(self, relative: str) -> str:
        path = self.root / relative
        if not path.is_file():
            raise ProjectError(f"{relative} does not exist in this project")
        return path.read_text(encoding="utf-8", errors="replace")

    def write_source(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if path.suffix in (".py", ".sh") or "bin/" in relative:
            path.chmod(0o755)
        return path

    # ---- manifest -----------------------------------------------------------
    def manifest(self) -> dict:
        return generate_manifest(self)

    def write_manifest(self) -> Path:
        path = self.root / "MANIFEST.json"
        path.write_text(json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def generate_manifest(project: Project) -> dict:
    """Build a manifest from the project file, filled in with template defaults."""
    template = project.template
    data = project.data
    defaults = template.defaults or {}
    manifest = {
        "format": 1,
        "id": project.id,
        "name": project.name,
        "version": project.version,
        "kind": data.get("kind", "app"),
        "arch": data.get("arch", "x86_64"),
        # Default to the OS release this toolkit targets, so a project built
        # here stays installable on the platform that ships it.
        "min_os": data.get("min_os", DEFAULT_OS_VERSION),
        "summary": data.get("summary") or f"{project.name} built with Zaod Studio",
        "description": data.get("description") or template.summary,
        "categories": data.get("categories") or ["Utility"],
        "license": data.get("license") or {"spdx": "MIT", "name": "MIT License"},
        "author": data.get("author") or {"name": os.environ.get("USER", "Zaod developer")},
        "entry": {"exec": project.entry, "args": [], "terminal": template.terminal},
        "icon": "icon.svg",
        "permissions": data.get("permissions") or defaults.get("permissions", {}),
        "runtimes": data.get("runtimes", defaults.get("runtimes", [])),
        "build": {"recipe": "zaod-studio", "reproducible": True},
    }
    if data.get("associations"):
        manifest["associations"] = data["associations"]
    if data.get("template"):
        manifest["build"]["source"] = PROJECT_FILE
    try:
        manifest_module.parse_manifest(manifest)
    except ZaodError as error:
        raise ProjectError(str(error)) from error
    return manifest


# ---- scaffolding -----------------------------------------------------------
README = """# {name}

`{app_id}` is a Zaod application created with Zaod Studio from the {template} template.

```bash
zaod-studio build .            # or: python3 -m zaodstudio.cli build .
zaod verify build/out/{app_id}-{version}.zaod
```

- Entry point: `{entry}`
- Version: {version}
- Template: {template} ({language})

Edit `zaod.project.json` to change the name, version, permissions or runtimes. The
`MANIFEST.json` shipped inside the package is generated from it on every build.
"""

GITIGNORE = """build/
*.zaod
__pycache__/
"""


def scaffold(
    template_name: str,
    destination: Path,
    app_id: str,
    name: str | None = None,
    *,
    version: str = "0.1.0",
    author: str | None = None,
    force: bool = False,
) -> Project:
    """Create a new project from one of the five templates."""
    template = _template(template_name)
    validate_id(app_id)
    destination = Path(destination).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()) and not force:
        raise ProjectError(f"{destination} is not empty; choose another folder or pass force=True")
    destination.mkdir(parents=True, exist_ok=True)

    display_name = name or app_id.split(".")[-1].replace("-", " ").title()
    for relative, content in template.render(app_id, display_name).items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755 if path.suffix in (".py", ".sh") else 0o644)

    (destination / "icon.svg").write_text(icon_svg(app_id), encoding="utf-8")
    (destination / "README.md").write_text(
        README.format(
            name=display_name,
            app_id=app_id,
            version=version,
            template=template.name,
            language=template.language,
            entry=template.entry,
        ),
        encoding="utf-8",
    )
    (destination / ".gitignore").write_text(GITIGNORE, encoding="utf-8")

    data = {
        "format": PROJECT_FORMAT,
        "id": app_id,
        "name": display_name,
        "version": version,
        "template": template.name,
        "entry": template.entry,
        "summary": f"{display_name} built with Zaod Studio",
        "description": template.summary,
        "categories": ["Utility"],
        "license": {"spdx": "MIT", "name": "MIT License"},
        "author": {"name": author or os.environ.get("USER", "Zaod developer")},
        "permissions": template.defaults.get("permissions", {}),
        "runtimes": template.defaults.get("runtimes", []),
    }
    project = Project(root=destination, data=data)
    project.save()
    project.write_manifest()
    return project


# ---- building --------------------------------------------------------------
def _run_step(argv: list[str], cwd: Path) -> list[str]:
    log = [f"$ {' '.join(argv)}"]
    result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=900)
    if result.stdout.strip():
        log.extend(result.stdout.strip().splitlines())
    if result.stderr.strip():
        log.extend(result.stderr.strip().splitlines())
    if result.returncode != 0:
        raise ProjectError(f"build step failed ({result.returncode}): {' '.join(argv)}")
    return log


def build_project(
    root: Path,
    *,
    private_key: Path | None = None,
    output: Path | None = None,
    level: int = 12,
    keep_staging: bool = False,
) -> BuildResult:
    """Build ``root`` into a signed ``.zaod`` package.

    The project is copied to a work tree, build steps run there, and only the
    shipped parts (manifest, icon, screenshots, ``payload/``) are assembled into
    the package. Compiler sources therefore never leak into the archive.
    """
    project = Project.load(root)
    log: list[str] = []
    staging = Path(tempfile.mkdtemp(prefix=f"zaod-studio-{project.id}-"))
    stage = staging / project.id
    work = staging / "work"
    stage.mkdir(parents=True)
    work.mkdir(parents=True)
    try:
        for path in project.source_files():
            relative = path.relative_to(project.root)
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if path.stat().st_mode & 0o111:
                target.chmod(0o755)
        log.append(f"project {project.id} {project.version} ({project.template.name})")

        for step in project.template.steps:
            argv = [part.replace("{{APP_ID}}", project.id) for part in step]
            log.extend(_run_step(argv, work))

        for name in ("icon.svg", "screenshots"):
            source = project.root / name
            if source.is_dir():
                shutil.copytree(source, stage / name)
            elif source.is_file():
                shutil.copy2(source, stage / name)
        log.append("icon.svg")

        payload_source = work / "payload"
        if payload_source.is_dir():
            shutil.copytree(payload_source, stage / "payload")

        for source, target in project.template.artifacts.items():
            source_path = work / source.replace("{{APP_ID}}", project.id)
            if not source_path.is_file():
                raise ProjectError(f"build did not produce {source_path.relative_to(work)}")
            target_path = stage / target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            target_path.chmod(0o755)
            log.append(f"artifact {target}")

        entry = stage / project.entry
        if not entry.is_file():
            raise ProjectError(f"entry point {project.entry} is missing from the build")
        entry.chmod(0o755)

        (stage / "MANIFEST.json").write_text(
            json.dumps(project.manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        target_package = Path(output) if output else project.root / "build" / "out" / f"{project.id}-{project.version}.zaod"
        target_package.parent.mkdir(parents=True, exist_ok=True)
        try:
            pack.build_package(stage, target_package, private_key=private_key, level=level)
        except ZaodError as error:
            target_package.unlink(missing_ok=True)
            raise ProjectError(str(error)) from error
        digest = hashlib.sha256(target_package.read_bytes()).hexdigest()
        log.append(f"packed {target_package.name} sha256 {digest[:16]}")
        return BuildResult(package=target_package, sha256=digest, manifest=project.manifest(), log=log)
    finally:
        if keep_staging:
            log.append(f"staging kept at {staging}")
        else:
            shutil.rmtree(staging, ignore_errors=True)


# ---- developer keys --------------------------------------------------------
def developer_keys(home: Path | None = None) -> tuple[Path, Path]:
    """Return ``(private, public)`` developer keys stored under the user's home."""
    base = Path(home).expanduser() if home else Path(os.environ.get("HOME", "~")).expanduser()
    directory = base / ".zaod" / "data" / "org.zaod.studio" / "keys"
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / "developer.key"
    public_path = directory / "developer.pub"
    if not private_path.is_file():
        pair = keys.generate_keypair()
        private_path.write_text(pair.export_private(), encoding="utf-8")
        private_path.chmod(0o600)
        public_path.write_text(pair.export_public(), encoding="utf-8")
        public_path.chmod(0o644)
    return private_path, public_path


def key_id_of(private_key: Path) -> str:
    return keys.load_private_key(Path(private_key)).key_id


# ---- running ---------------------------------------------------------------
def run_package(package: Path, app_id: str, root: Path | None = None) -> subprocess.CompletedProcess:
    """Install a built package into a development root and run it sandboxed."""
    environment = dict(os.environ)
    if root:
        environment["ZAOD_ROOT"] = str(Path(root))
    zaod = str(REPO_ROOT / "zaod" / "bin" / "zaod")
    installed = subprocess.run(
        [zaod, "install", str(package)], capture_output=True, text=True, check=False, env=environment, timeout=600
    )
    if installed.returncode != 0:
        raise ProjectError(installed.stderr.strip() or "install failed")
    return subprocess.run(
        [zaod, "run", app_id], capture_output=True, text=True, check=False, env=environment, timeout=120
    )
