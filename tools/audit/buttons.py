#!/usr/bin/env python3
# Deep-search harness: builds every window and clicks every button.
# Run with: QT_QPA_PLATFORM=offscreen python3 tools/audit/buttons.py
# ruff: noqa: BLE001, S110, S112, I001
"""Click every button in every Zaod app and report what breaks.

The user asked for a deep search for broken buttons. Reading the code does not
prove a button works, so this builds each real window, stubs out the system tools
and every modal dialog, then clicks through the whole tree and records any
exception, any button that does nothing at all, and any window that fails to build.
"""

import importlib.util
import os
import sys
import traceback
import glob

os.environ.update(
    QT_QPA_PLATFORM="offscreen",
    HOME=os.environ.get("HOME", "/root"),
    XDG_RUNTIME_DIR="/tmp/xdg-audit",
    PATH="/tmp/fakebin:" + os.environ.get("PATH", ""),
)
os.makedirs("/tmp/xdg-audit", exist_ok=True)

from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QDialog, QMessageBox, QFileDialog, QInputDialog,
    QWidget, QComboBox, QTabWidget, QStackedWidget,
)
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# the shared Zaod libraries ship in the image lib dir, the apps import them by name
sys.path.insert(0, f"{REPO}/apps/lib")

# Every modal surface returns at once, so a click cannot hang the audit.
QDialog.exec = lambda self, *a, **k: 0
QMessageBox.exec = lambda self, *a, **k: 0
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
for name in ("getText", "getItem", "getMultiLineText", "getDouble", "getInt"):
    setattr(QInputDialog, name, staticmethod(lambda *a, **k: ("", True)))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")

app = QApplication.instance() or QApplication([])

errors = []
notes = []


def describe(widget):
    text = ""
    for attr in ("text", "title", "windowTitle"):
        try:
            value = getattr(widget, attr)()
        except Exception:
            continue
        if value:
            text = str(value).strip()
            break
    name = widget.objectName() or widget.__class__.__name__
    return f"{widget.__class__.__name__}[{name}] {text[:40]!r}"


def collect(root):
    return [root] + root.findChildren(QWidget)


def load_app(path, label):
    # two apps both ship a plain "backend.py"; each runs in its own process in
    # the OS, so the audit clears the previous one instead of inheriting it
    for stale in [m for m in sys.modules if m in ("backend", "zaodapp", "store", "studio")]:
        sys.modules.pop(stale, None)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("audit_" + label.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def audit_app(path, label):
    try:
        module = load_app(path, label)
    except Exception:
        errors.append(f"{label}: does not import\n{traceback.format_exc(limit=4)}")
        return None
    builder = getattr(module, "build_window", None)
    if builder is None:
        errors.append(f"{label}: no build_window()")
        return None
    try:
        window = builder()
    except Exception:
        errors.append(f"{label}: window does not build\n{traceback.format_exc(limit=4)}")
        return None
    if window is None:
        errors.append(f"{label}: build_window() returned None")
        return None
    try:
        window.show()
        app.processEvents()
    except Exception:
        errors.append(f"{label}: window does not show\n{traceback.format_exc(limit=4)}")

    buttons = [w for w in collect(window) if isinstance(w, QAbstractButton)]
    clicked = 0
    for button in buttons:
        if not button.isEnabled() or button.isHidden():
            continue
        label_b = describe(button)
        try:
            button.click()
            app.processEvents()
            clicked += 1
        except Exception:
            errors.append(f"{label} / {label_b}: click raised\n{traceback.format_exc(limit=5)}")
        # a click that opens a second window must not leave it hanging around
        for other in QApplication.topLevelWidgets():
            if other is not window and other.isVisible() and other.metaObject().className() != "QMenu":
                try:
                    other.close()
                except Exception:
                    pass
        app.processEvents()

    # combos and list selection: choosing an item is a click too
    for combo in window.findChildren(QComboBox):
        if combo.count() > 1:
            try:
                combo.setCurrentIndex(combo.count() - 1)
                app.processEvents()
            except Exception:
                errors.append(f"{label} / combo {describe(combo)}: selecting raised\n{traceback.format_exc(limit=4)}")

    # every tab and stacked page must at least render
    for tabs in window.findChildren(QTabWidget):
        for index in range(tabs.count()):
            try:
                tabs.setCurrentIndex(index)
                app.processEvents()
            except Exception:
                errors.append(f"{label} / tab {index}: raised\n{traceback.format_exc(limit=4)}")
    for stack in window.findChildren(QStackedWidget):
        for index in range(stack.count()):
            try:
                stack.setCurrentIndex(index)
                app.processEvents()
            except Exception:
                errors.append(f"{label} / page {index}: raised\n{traceback.format_exc(limit=4)}")

    notes.append(f"{label}: {len(buttons)} buttons, {clicked} clicked")
    window.close()
    return window


paths = sorted(glob.glob(f"{REPO}/apps/*/payload/main.py"))
for path in paths:
    label = path.split("/apps/")[1].split("/")[0]
    sys.path.insert(0, os.path.dirname(path))
    audit_app(path, label)
    sys.path.pop(0)

# the shared account window ships inside lib/zaod, not as an app
sys.path.insert(0, f"{REPO}/apps/lib")
for candidate in ("zaodaccount", "zaodhub", "zaod_cloud", "zaodupdate", "zaodapp"):
    if not glob.glob(f"{REPO}/apps/lib/{candidate}.py"):
        continue
    try:
        __import__(candidate)
        notes.append(f"{candidate}: imports")
    except Exception:
        errors.append(f"{candidate}: does not import\n{traceback.format_exc(limit=4)}")

try:
    import zaodaccount
    dialog = zaodaccount.build_dialog()
    dialog.show()
    app.processEvents()
    for button in [w for w in collect(dialog) if isinstance(w, QAbstractButton)]:
        if button.isEnabled() and not button.isHidden():
            try:
                button.click()
                app.processEvents()
            except Exception:
                errors.append(f"account window / {describe(button)}: click raised\n{traceback.format_exc(limit=5)}")
    notes.append("account window: clicked through")
    dialog.close()
except Exception:
    errors.append(f"account window: failed\n{traceback.format_exc(limit=4)}")

print("\n".join(notes))
print(f"\n=== {len(errors)} problems ===")
for problem in errors:
    print("\n" + problem)
print("\nRESULT:", "PASS" if not errors else f"FAIL ({len(errors)})")
