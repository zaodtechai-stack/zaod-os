"""The launcher entries the image ships must run inside the image.

An Exec line built from the build host's path looks correct in the build log and
does nothing on real hardware: this is the check that keeps that from happening
again.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def load_installer():
    spec = importlib.util.spec_from_file_location(
        "install_app_set", REPO / "scripts" / "install-app-set.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_app(apps_dir: Path, slug: str, app_id: str) -> None:
    payload = apps_dir / slug / "payload"
    payload.mkdir(parents=True)
    (payload / "main.py").write_text("print('hi')\n")
    (apps_dir / slug / "MANIFEST.json").write_text(
        json.dumps(
            {
                "id": app_id,
                "name": slug.title(),
                "summary": "test app",
                "entry": {"exec": "payload/main.py"},
                "categories": ["Utility"],
            }
        )
    )
    (apps_dir / slug / "icon.svg").write_text("<svg/>\n")


def test_launcher_exec_uses_the_image_path(tmp_path: Path) -> None:
    installer = load_installer()
    root = tmp_path / "rootfs"
    (root / "etc").mkdir(parents=True)
    apps_dir = tmp_path / "apps"
    make_app(apps_dir, "notes", "org.zaod.notes")

    installed = installer.install(root, apps_dir, dry_run=False)

    assert installed == ["org.zaod.notes"]
    entry = (root / "usr/share/applications/org.zaod.notes.desktop").read_text()
    assert "Exec=/usr/bin/python3 /opt/zaod/apps/notes/payload/main.py" in entry
    # The build host's path must never appear in a launcher.
    assert str(tmp_path) not in entry
    assert (root / "opt/zaod/apps/notes/payload/main.py").is_file()
    assert (root / "usr/share/icons/hicolor/scalable/apps/org.zaod.notes.svg").is_file()


def test_every_shipped_app_points_into_the_image() -> None:
    installer = load_installer()
    apps_dir = REPO / "apps"
    for app in sorted(apps_dir.iterdir()):
        manifest = app / "MANIFEST.json"
        if not manifest.is_file() or not (app / "payload").is_dir():
            continue
        if app.name in installer.SKIP:
            continue
        data = json.loads(manifest.read_text())
        entry = data.get("entry") or {}
        exe = Path(entry.get("exec") or "payload/main.py").name
        assert (
            app / "payload" / exe
        ).is_file(), f"{app.name}: MANIFEST entry {exe} is not in its payload"


def test_installed_apps_import_every_shared_module(tmp_path: Path) -> None:
    """A payload whose helper is missing a module cannot start at all.

    The image shipped every app with only zaodapp.py in payload/lib, while
    zaodapp imports zaod_tokens on its first line, so each app died with
    ModuleNotFoundError before drawing a window.
    """
    pytest.importorskip("PySide6")
    installer = load_installer()
    root = tmp_path / "rootfs"
    (root / "etc").mkdir(parents=True)
    apps_dir = tmp_path / "apps"
    make_app(apps_dir, "calculator", "org.zaod.calculator")
    # the shared helper directory the real apps/ tree carries
    shutil.copytree(REPO / "apps" / "lib", apps_dir / "lib")

    installer.install(root, apps_dir, dry_run=False)

    lib = root / "opt/zaod/apps/calculator/payload/lib"
    for module in sorted((REPO / "apps" / "lib").glob("*.py")):
        assert (lib / module.name).is_file(), f"{module.name} was not installed with the app"


def test_no_payload_depends_on_a_module_that_is_not_shared() -> None:
    """Every `import zaodapp` neighbour in apps/lib must exist there."""
    shared = {p.stem for p in (REPO / "apps" / "lib").glob("*.py")}
    assert "zaodapp" in shared and "zaod_tokens" in shared
    helper = (REPO / "apps" / "lib" / "zaodapp.py").read_text()
    for line in helper.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            name = stripped.split()[1].split(".")[0]
            if name.startswith("zaod"):
                assert name in shared, f"zaodapp imports {name}, which apps/lib does not ship"


def test_studio_ships_with_the_library_it_imports() -> None:
    """Studio packages projects with zaodlib and its own toolkit.

    The payload alone cannot import either: zaodstudio lives at the top of the
    tree and zaodlib is installed to /usr/lib/zaod, so both had to be wired
    explicitly or every Studio build fails with ModuleNotFoundError.
    """
    installer = load_installer()
    assert "studio" in installer.EXTRA_MODULES
    assert any(p.name == "zaodstudio" for p in installer.EXTRA_MODULES["studio"])
    main_py = (REPO / "apps" / "studio" / "payload" / "main.py").read_text()
    assert "/usr/lib/zaod" in main_py
