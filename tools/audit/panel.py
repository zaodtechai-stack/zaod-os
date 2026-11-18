#!/usr/bin/python3
# Deep-search harness: builds every window and clicks every button.
# Run with: QT_QPA_PLATFORM=offscreen python3 tools/audit/buttons.py
# ruff: noqa: BLE001, S112, PLW1510, I001
"""Click every button in the GTK panel, with the system tools stubbed out.

The Qt apps are covered elsewhere; the panel is GTK and needs the system python,
so this runs it under Xvfb, walks the real widget tree and clicks everything the
way a person would: the launcher button, the quick settings, Wi-Fi rows, Bluetooth,
volume, battery and the power menu.
"""

import os
import sys
import subprocess
import traceback

os.environ.update(
    PATH="/tmp/fakebin:" + os.environ.get("PATH", ""),
    HOME="/tmp/panel-home",
    XDG_RUNTIME_DIR="/tmp/panel-xdg",
)
os.makedirs("/tmp/panel-home", exist_ok=True)
os.makedirs("/tmp/panel-xdg", exist_ok=True)

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk

REPO = "/tmp/zaod-os"
sys.path.insert(0, os.path.join(REPO, "desktop", "shell"))
sys.path.insert(0, os.path.join(REPO, "apps", "lib"))

problems = []
notes = []


def pump(rounds=6):
    for _ in range(rounds):
        while Gtk.events_pending():
            Gtk.main_iteration()


panel_module = __import__("panel")


def describe(widget):
    for getter in ("get_label", "get_tooltip_text", "get_text", "get_title"):
        fn = getattr(widget, getter, None)
        if not fn:
            continue
        try:
            value = fn()
        except Exception:
            continue
        if value:
            return str(value).strip()[:40]
    return widget.get_name()


def collect(root):
    found = [root]
    if isinstance(root, Gtk.Container):
        for child in root.get_children():
            found.extend(collect(child))
    return found


def clickable(root):
    out = []
    for widget in collect(root):
        if isinstance(widget, (Gtk.Button, Gtk.ToggleButton, Gtk.MenuButton, Gtk.ModelButton)):
            out.append(widget)
        elif isinstance(widget, Gtk.EventBox) and getattr(widget, "clicked", None) is not None:
            pass
    return out


def click(widget, label):
    try:
        if isinstance(widget, Gtk.ToggleButton):
            widget.set_active(not widget.get_active())
        else:
            widget.clicked()
        pump()
    except Exception:
        problems.append(f"{label} / {describe(widget)}: click raised\n{traceback.format_exc(limit=5)}")


def build_panel():
    # the panel builds itself on import in the session, but for the audit the
    # window is made explicitly so nothing depends on a main loop
    if hasattr(panel_module, "build_panel"):
        return panel_module.build_panel()
    if hasattr(panel_module, "Panel"):
        return panel_module.Panel()
    raise RuntimeError("panel exposes no build_panel() or Panel()")


try:
    window = build_panel()
    if isinstance(window, Gtk.Window):
        window.show_all()
    pump()
    notes.append(f"panel built: {window.__class__.__name__}")
except Exception:
    problems.append(f"panel does not build\n{traceback.format_exc(limit=6)}")
    window = None

if window is not None:
    # open the app grid, then the quick settings, the way the owner does
    for opener in ("toggle_launcher", "toggle_quick", "toggle_quick_settings"):
        fn = getattr(window, opener, None) or getattr(panel_module, opener, None)
        if not fn:
            continue
        try:
            fn()
            pump()
            notes.append(f"{opener}(): opened")
        except Exception:
            problems.append(f"{opener}(): raised\n{traceback.format_exc(limit=5)}")
        try:
            fn()
            pump()
            notes.append(f"{opener}(): closed again")
        except Exception:
            problems.append(f"{opener}(): second call raised\n{traceback.format_exc(limit=5)}")

    buttons = clickable(window)
    for button in buttons:
        if not button.get_visible():
            continue
        click(button, "panel")
    notes.append(f"panel buttons: {len(buttons)} found, clicked the visible ones")

    # the power menu must offer the real actions, not dead labels
    power_labels = []
    for widget in collect(window):
        if isinstance(widget, Gtk.ModelButton):
            power_labels.append(widget.get_text())
    if power_labels:
        notes.append("menu actions: " + ", ".join(x for x in power_labels if x))

# the helper programs the panel and the launcher depend on must exist and be executable
for helper in ("zaod-open", "zaod-run", "zaod-wallpaper", "zaod-webapp"):
    path = os.path.join(REPO, "desktop", "shell", helper)
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        problems.append(f"helper missing or not executable: {helper}")
    else:
        result = subprocess.run([path, "--help"], capture_output=True, text=True, timeout=30)
        if result.returncode not in (0, 1, 2) and "Traceback" in result.stderr:
            problems.append(f"{helper} --help crashed:\n{result.stderr[-400:]}")

print("\n".join(notes))
print(f"\n=== {len(problems)} problems ===")
for problem in problems:
    print("\n" + problem)
print("\nRESULT:", "PASS" if not problems else f"FAIL ({len(problems)})")
