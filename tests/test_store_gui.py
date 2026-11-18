"""Clicking a store card must open its details with the right action.

The owner's requirement, in his words: clicking any app shows its details with
the install/open/remove buttons. That is a UI behaviour, so it is driven here on
a real window with a real click, not on the functions behind it.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / "apps" / "store" / "payload"
SHARED = REPO / "apps" / "lib"


def load_store():
    for path in (str(PAYLOAD), str(SHARED)):
        if path not in sys.path:
            sys.path.insert(0, path)
    spec = importlib.util.spec_from_file_location("store_gui", PAYLOAD / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["store_gui"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("ZAOD_THEME", "dark")
    from PySide6.QtWidgets import QApplication

    sys.path.insert(0, str(SHARED))
    import zaodapp

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(zaodapp.stylesheet())
    return app


@pytest.fixture()
def window(qt_app, tmp_path, monkeypatch):
    """An empty install tree, so the cards come from what the test writes."""
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "org.zaod.notes.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Notes\n"
        "Comment=Write things down and keep them\n"
        "Exec=/usr/bin/python3 /opt/zaod/apps/notes/payload/main.py\n"
        "Icon=org.zaod.notes\n"
        "X-Zaod-AppId=org.zaod.notes\n"
    )
    (applications / "org.zaod.clock.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Clock\n"
        "Comment=Alarms, timers and stopwatch\n"
        "Exec=/usr/bin/python3 /opt/zaod/apps/clock/payload/main.py\n"
        "Icon=org.zaod.clock\n"
        "X-Zaod-AppId=org.zaod.clock\n"
    )
    optional = tmp_path / "optional"
    (optional / "webapps").mkdir(parents=True)
    (optional / "webapps" / "webapps.json").write_text('{"apps": []}')

    module = load_store()
    monkeypatch.setattr(module, "APPLICATIONS", applications)
    monkeypatch.setattr(module, "OPTIONAL_ROOT", optional)
    monkeypatch.setattr(module, "USER_APPLICATIONS", tmp_path / "user-apps")
    monkeypatch.setattr(module, "USER_ICONS", tmp_path / "user-icons")
    monkeypatch.setattr(module, "USER_APPS", tmp_path / "user-apps-data")

    win = module.build_window()
    win.show()
    qt_app.processEvents()
    return module, win


def visible_text(window) -> str:
    """Everything a person can read in the window, description pane included."""
    from PySide6.QtWidgets import QLabel, QTextBrowser

    parts = [w.text() or "" for w in window.findChildren(QLabel) if w.isVisible()]
    parts += [
        w.toPlainText() for w in window.findChildren(QTextBrowser) if w.isVisible()
    ]
    return " \n".join(parts)


def details_pane(window) -> str:
    """Only the description pane, not the cards that repeat a summary."""
    from PySide6.QtWidgets import QTextBrowser

    return " ".join(
        w.toPlainText() for w in window.findChildren(QTextBrowser) if w.isVisible()
    )


def cards(window):
    """The app cards only - the category chips are buttons too."""
    from PySide6.QtWidgets import QPushButton

    return [
        b
        for b in window.findChildren(QPushButton)
        if b.objectName() == "card" and b.isVisible()
    ]


def wait_for(app, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_every_listed_app_is_a_clickable_card(window):
    _module, win = window
    names = visible_text(win)
    assert "Notes" in names and "Clock" in names, names
    assert len(cards(win)) >= 2, "the grid drew no clickable cards"


def card_named(win, name: str):
    """The card whose own labels say `name`."""
    from PySide6.QtWidgets import QLabel

    for button in cards(win):
        for label in button.findChildren(QLabel):
            if (label.text() or "").strip() == name:
                return button
    return None


def test_clicking_a_card_shows_its_details_and_actions(window, qt_app):
    """The first app is shown on open; picking another one must switch to it."""
    _module, win = window
    notes = card_named(win, "Notes")
    assert notes is not None, "no card for Notes"

    notes.click()
    assert wait_for(
        qt_app, lambda: "Write things down and keep them" in visible_text(win)
    ), "clicking a card did not show its description"
    assert "Write things down and keep them" in details_pane(win)
    assert "Alarms, timers and stopwatch" not in details_pane(win), (
        "the details pane did not switch to the picked app"
    )
    pane = visible_text(win)
    assert any(word in pane for word in ("Open", "Install", "Add")), pane


def test_a_selected_card_is_marked(window, qt_app):
    _module, win = window
    tile = cards(win)[0]
    tile.click()
    assert wait_for(qt_app, lambda: tile.isChecked()), "the picked card is not marked selected"
    checked = [c for c in cards(win) if c.isChecked()]
    assert len(checked) == 1, "more than one card looks selected"
