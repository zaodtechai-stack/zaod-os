"""Drive the real Control Center window: scan, wrong password, then the right one.

The unit tests prove the nmcli layer. This one proves the *window*: it builds the
actual Control Center, clicks Wi-Fi, presses Scan, picks a network, types a wrong
password, checks the person is told the password is wrong (and is not connected),
types the real password and checks the window reports a connection. Qt runs
offscreen, so this is the same widget tree the live session draws.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PAYLOAD = REPO / "apps" / "control-center" / "payload"
SHARED = REPO / "apps" / "lib"


def _fakes_module():
    spec = importlib.util.spec_from_file_location("conn_fakes", REPO / "tests" / "test_connectivity.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def fake_tools(tmp_path, monkeypatch):
    fakes = _fakes_module()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("nmcli", fakes.NMCLI), ("bluetoothctl", fakes.BLUETOOTHCTL)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    nm_state = tmp_path / "nm.json"
    nm_state.write_text(
        json.dumps(
            {
                "radio": True,
                "connected": None,
                "saved": [],
                "aps": [
                    {"ssid": "HomeNet", "signal": 82, "security": "WPA2", "bssid": "AA:BB:CC:DD:EE:01", "password": "correct horse"},
                    {"ssid": "Cafe: Free", "signal": 58, "security": "", "bssid": "AA:BB:CC:DD:EE:03", "password": ""},
                ],
            }
        )
    )
    bt_state = tmp_path / "bt.json"
    bt_state.write_text(json.dumps({"adapter": True, "power": True, "devices": {}}))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_NM_STATE", str(nm_state))
    monkeypatch.setenv("FAKE_NM_LOG", str(tmp_path / "nm.log"))
    monkeypatch.setenv("FAKE_BT_STATE", str(bt_state))
    monkeypatch.setenv("FAKE_BT_LOG", str(tmp_path / "bt.log"))
    monkeypatch.setenv("ZAOD_THEME", "dark")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    return {"nm_state": nm_state, "log": tmp_path / "nm.log"}


@pytest.fixture(scope="module")
def qt_app():
    """A real Qt app dressed exactly like a Zaod app window (as zaodapp.run does)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("ZAOD_THEME", "dark")
    sys.path.insert(0, str(REPO / "apps" / "lib"))
    import zaodapp
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(zaodapp.stylesheet())
    return app


def load_control_center():
    sys.path.insert(0, str(PAYLOAD))
    sys.path.insert(0, str(SHARED))
    for name in list(sys.modules):
        if name in {"backend", "connectivity", "settings", "zaodapp", "zaod_tokens"}:
            del sys.modules[name]
    spec = importlib.util.spec_from_file_location("cc_main", PAYLOAD / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cc_main"] = module
    spec.loader.exec_module(module)
    return module


def wait_until(app, predicate, timeout=15.0):
    """Pump the Qt event loop until predicate() is true or time runs out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    app.processEvents()
    return predicate()


def find(widget, text, cls=None, which=slice(None)):
    """Every widget whose visible text matches, breadth first."""
    from PySide6.QtWidgets import QAbstractButton, QLabel

    hits = []

    def walk(item):
        for child in item.children():
            if isinstance(child, (QAbstractButton, QLabel)) and (
                cls is None or isinstance(child, cls)
            ):
                label = child.text() if hasattr(child, "text") else ""
                if text in (label or ""):
                    hits.append(child)
            walk(child)

    walk(widget)
    return hits[which]


def test_scan_wrong_password_then_the_real_one(qt_app, fake_tools):
    from PySide6.QtWidgets import QLineEdit

    module = load_control_center()
    window = module.build_window()
    window.show()
    qt_app.processEvents()

    # 1. the Wi-Fi page, found the way a person finds it: by clicking "Wi-Fi"
    nav = find(window, "Wi-Fi")
    assert nav, "the sidebar has no Wi-Fi entry"
    nav[0].click()
    qt_app.processEvents()

    # 2. Scan is a real button that fills the list
    scan = next(b for b in find(window, "Scan") if hasattr(b, "click"))
    scan.click()
    assert wait_until(qt_app, lambda: any("HomeNet" in (b.text() or "") for b in find(window, "HomeNet"))), \
        "the nearby list never showed HomeNet"

    # 3. picking the secured network asks for a password
    from PySide6.QtWidgets import QAbstractButton

    def clickable_around(lbl):
        """The row is a button whose labels are its children."""
        widget = lbl
        while widget is not None and not isinstance(widget, QAbstractButton):
            widget = widget.parent()
        return widget

    row = clickable_around(find(window, "HomeNet")[0])
    assert row is not None, "the network row is not clickable"
    row.click()
    qt_app.processEvents()
    field = [w for w in window.findChildren(QLineEdit) if w.isVisible() and w.echoMode() == QLineEdit.EchoMode.Password]
    assert field, "a WPA2 network did not ask for a password"
    field = field[0]

    # 4. a wrong password is refused, and the window says so
    field.setText("wrong password")
    connect = next(b for b in find(window, "Connect") if hasattr(b, "click"))
    connect.click()
    from PySide6.QtWidgets import QLabel

    def visible_text() -> str:
        return " ".join(
            (w.text() or "") for w in window.findChildren(QLabel) if w.isVisible()
        ).lower()

    def says_wrong_password() -> bool:
        return "wrong password" in visible_text()

    assert wait_until(qt_app, says_wrong_password), "a wrong password produced no message"
    state = json.loads(fake_tools["nm_state"].read_text())
    assert state["connected"] is None, "a wrong password still connected"

    # 5. the real password connects
    field.setText("correct horse")
    connect = next(b for b in find(window, "Connect") if hasattr(b, "click"))
    connect.click()
    assert wait_until(qt_app, lambda: json.loads(fake_tools["nm_state"].read_text())["connected"] == "HomeNet"), \
        "the right password did not connect"
    def says_connected() -> bool:
        return "connected to" in visible_text()

    assert wait_until(qt_app, says_connected), "the window did not report the connection"

    # 6. the password never reached a command line, where ps would show it
    log = fake_tools["log"].read_text().splitlines()
    assert log, "nmcli was never called"
    assert all("correct horse" not in line and "wrong password" not in line for line in log), \
        "a Wi-Fi password appeared on a command line"

    window.grab().save("/tmp/shots/control-center-wifi.png")
    window.close()
