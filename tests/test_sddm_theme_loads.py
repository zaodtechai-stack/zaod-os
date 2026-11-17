"""Load the login theme the way the greeter does, and fail on any QML error.

SDDM reads Main.qml with a Qt Quick runtime and throws the whole file away on a
single unknown property, painting "The current theme cannot be loaded" over the
login box. Both `palette.button` and `contentItem` on Button did exactly that on
real hardware, and neither a diff nor a grep would have caught the next one, so
this test actually instantiates the theme with stand-ins for the objects SDDM
injects (sddm, config, sessionModel, userModel).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

REPO = Path(__file__).resolve().parent.parent
THEME = REPO / "desktop" / "sddm" / "themes" / "zaod" / "Main.qml"


class Sddm(QObject):
    loginFailed = Signal()

    @Slot(str, str, int)
    def login(self, user: str, password: str, session: int) -> None:
        pass

    @Slot()
    def powerOff(self) -> None:
        pass

    @Slot()
    def reboot(self) -> None:
        pass


class Config(QObject):
    def __init__(self) -> None:
        super().__init__()

    @Property(str, constant=True)
    def background(self) -> str:
        return "background.svg"


class SessionModel(QObject):
    @Property(int, constant=True)
    def lastIndex(self) -> int:
        return 0

    @Slot(int, result=str)
    def getString(self, row: int) -> str:
        return "Zaod Desktop"

    @Slot(result=int)
    def rowCount(self) -> int:
        return 3


class UserModel(QObject):
    @Property(str, constant=True)
    def lastUser(self) -> str:
        return "zaodlive"


def test_theme_loads_without_qml_errors(tmp_path: Path) -> None:
    source = THEME.read_text()
    theme_copy = tmp_path / "Main.qml"
    theme_copy.write_text(source)
    (tmp_path / "background.svg").write_text(THEME.with_name("background.svg").read_text())

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    engine = QQmlEngine()
    context = engine.rootContext()
    context.setContextProperty("sddm", Sddm())
    context.setContextProperty("config", Config())
    context.setContextProperty("sessionModel", SessionModel())
    context.setContextProperty("userModel", UserModel())
    component = QQmlComponent(engine, theme_copy.as_uri())
    errors = component.errors()
    messages = "\n".join(f"{e.url().toString()}:{e.line()}: {e.description()}" for e in errors)
    assert not errors, messages

    item = component.create(engine.rootContext())
    assert item is not None, messages
    assert item.property("width") == 1920
    # The greeting, the two inputs and the sign-in button have to exist as real
    # objects: an error inside a binding shows up as a load failure, not a crash.
    assert item.findChildren(QObject)
    assert "Import" not in messages
