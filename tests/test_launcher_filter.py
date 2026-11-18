"""The app grid shows apps, not the plumbing that came with the distro.

The recording that complained about a Python logo in the OS was showing the grid,
where "Python 3.13" sat between the real apps because every installed .desktop file
was listed. The rule lives in panel.py and is pure, so it is tested here.
"""
from __future__ import annotations

import ast
from pathlib import Path

PANEL = Path(__file__).resolve().parents[1] / "desktop" / "shell" / "panel.py"


def _load_helper():
    tree = ast.parse(PANEL.read_text())
    wanted = [node for node in tree.body
              if isinstance(node, ast.FunctionDef) and node.name == "entry_is_hidden"]
    assert wanted, "panel.py no longer defines entry_is_hidden"
    module = ast.Module(body=wanted + [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "HIDDEN_ENTRY_IDS" for t in node.targets)
    ], type_ignores=[])
    namespace: dict[str, object] = {}
    exec(compile(module, str(PANEL), "exec"), namespace)  # noqa: S102 - only panel.py code
    return namespace["entry_is_hidden"]


def test_zaod_apps_are_always_listed():
    hidden = _load_helper()
    for app_id in ("org.zaod.editor.desktop", "org.zaod.store.desktop",
                   "org.zaod.notes.desktop", "org.zaod.control-center.desktop"):
        assert hidden(app_id) is False, app_id


def test_python_and_toolkit_entries_are_hidden():
    hidden = _load_helper()
    for app_id in ("python3.13.desktop", "qt6ct.desktop", "gvim.desktop",
                   "xdg-desktop-portal-gtk.desktop", "org.freedesktop.Xwayland.desktop",
                   "thunar-bulk-rename.desktop"):
        assert hidden(app_id) is True, app_id


def test_ordinary_third_party_apps_survive():
    hidden = _load_helper()
    for app_id in ("org.xfce.thunar.desktop", "chromium.desktop", "org.gnome.Calculator.desktop"):
        assert hidden(app_id) is False, app_id


def test_grid_is_rebuilt_every_time_the_launcher_opens():
    """An app added from the store has to show up without logging out.

    The store writes a .desktop file into ~/.local/share/applications while the
    panel keeps running; filling the grid only in __init__ hid the new app until
    the next session.
    """
    import re

    source = PANEL.read_text()
    body = source.split("def toggle_launcher", 1)[1].split("def launch", 1)[0]
    assert re.search(r"launcher\.fill\(\)", body), "toggle_launcher must refresh the grid"


def test_panel_pins_every_gi_version_it_imports():
    """Importing Gdk without require_version made the panel log a PyGIWarning."""
    source = PANEL.read_text()
    imported = {"Gtk", "Gdk"}
    for namespace in imported:
        assert f'gi.require_version("{namespace}"' in source, namespace
