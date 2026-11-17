#!/usr/bin/env python3
"""The Zaod panel: launcher, running apps, clock and quick settings.

This is the desktop. There is no Plasma, no KDE and no third-party shell in the
image: the session starts labwc as the Wayland compositor and this panel on top
of it, and every visible surface is drawn from the Zaod design tokens.

* The left button opens the app grid, built from the installed .desktop entries,
  so an app that the store installs shows up without the panel knowing about it.
* The middle shows the pinned first-party apps (store, files, browser, editor,
  notes, settings).
* The right has the clock and quick settings: volume, theme, and power.

The panel asks for the Wayland layer-shell protocol when gtk-layer-shell is
present and falls back to an undecorated dock window otherwise, so a missing
optional library cannot leave the session with no panel at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

ACCENT = "#0067C0"
ACCENT_TEXT = "#06121F"
SURFACE = "#14161A"
SURFACE_HIGH = "#1B1D21"
TEXT = "#F6F7F9"
MUTED = "#9AA3AD"
DANGER = "#FFB4AB"
HEIGHT = 44
RADIUS = 12

# Apps that sit on the panel itself. Ids are the manifest ids the app set
# installs, so the pin list is stable even if a binary name changes.
PINNED = [
    "org.zaod.store",
    "thunar",
    "foot",
    "org.zaod.editor",
    "org.zaod.notes",
    "org.zaod.control-center",
]

CSS = f"""
window.zaod-panel {{
  background: transparent;
}}
.zaod-bar {{
  background: {SURFACE};
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: {RADIUS}px;
  padding: 5px 10px;
}}
.zaod-bar button {{
  background: transparent;
  border: none;
  border-radius: 10px;
  color: {TEXT};
  padding: 6px 10px;
  box-shadow: none;
  text-shadow: none;
}}
.zaod-bar button:hover {{
  background: rgba(255, 255, 255, 0.10);
}}
.zaod-bar button:active {{
  background: rgba(255, 255, 255, 0.16);
}}
.zaod-brand {{
  background: {ACCENT};
  color: {ACCENT_TEXT};
  font-weight: 700;
  border-radius: 9px;
  padding: 5px 12px;
}}
.zaod-brand:hover {{
  background: #1A7AD4;
}}
.zaod-clock {{
  color: {TEXT};
  font-weight: 600;
  padding: 0 8px;
}}
.zaod-launcher {{
  background: {SURFACE_HIGH};
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 16px;
  padding: 12px;
}}
.zaod-launcher entry {{
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  color: {TEXT};
  padding: 8px 10px;
  caret-color: {ACCENT};
}}
.zaod-tile {{
  background: rgba(255, 255, 255, 0.045);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  color: {TEXT};
  padding: 14px 10px;
}}
.zaod-tile:hover {{
  background: rgba(0, 103, 192, 0.28);
  border-color: rgba(0, 103, 192, 0.55);
}}
.zaod-tile label {{
  color: {TEXT};
}}
.zaod-title {{
  color: {MUTED};
  font-size: 11px;
  font-weight: 700;
}}
popover.zaod-popover, popover.zaod-popover > box {{
  background: {SURFACE_HIGH};
  border-radius: 12px;
  color: {TEXT};
  padding: 6px;
}}
popover.zaod-popover button {{
  background: transparent;
  border: none;
  border-radius: 8px;
  color: {TEXT};
  padding: 6px 10px;
}}
popover.zaod-popover button:hover {{
  background: rgba(255, 255, 255, 0.10);
}}
popover.zaod-popover scale trough {{
  background: rgba(255, 255, 255, 0.14);
  border-radius: 4px;
  min-height: 6px;
}}
popover.zaod-popover scale highlight {{
  background: {ACCENT};
  border-radius: 4px;
}}
"""


def theme_variant() -> str:
    return os.environ.get("ZAOD_THEME") or (
        "light" if os.environ.get("ZAOD_COLOR_SCHEME") == "light" else "dark"
    )


def run(*command: str) -> bool:
    """Start a detached command. Returns False when the binary is not there."""
    if not shutil.which(command[0]):
        return False
    try:
        subprocess.Popen(command, start_new_session=True)
        return True
    except OSError:
        return False


def desktop_apps() -> list[Gio.AppInfo]:
    apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
    seen = set()
    unique = []
    for app in apps:
        name = app.get_id() or app.get_name()
        if name in seen:
            continue
        seen.add(name)
        unique.append(app)
    unique.sort(key=lambda a: (a.get_name() or "").lower())
    return unique


def app_for(app_id: str) -> Gio.AppInfo | None:
    for info in Gio.AppInfo.get_all():
        identifier = (info.get_id() or "").removesuffix(".desktop")
        if identifier == app_id:
            return info
    # A package id may differ from its desktop entry (org.zaod.editor vs
    # editor.desktop), so fall back to the first id that carries the prefix.
    for info in Gio.AppInfo.get_all():
        identifier = (info.get_id() or "").removesuffix(".desktop")
        if identifier.split(".")[-1] == app_id.split(".")[-1]:
            return info
    return None


class Launcher(Gtk.Window):
    """The app grid: every installed app, filtered by what you type."""

    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.get_style_context().add_class("zaod-launcher")
        self.set_default_size(720, 520)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.get_style_context().add_class("zaod-launcher")
        self.add(outer)

        title = Gtk.Label(label="Apps", xalign=0)
        title.get_style_context().add_class("zaod-title")
        outer.pack_start(title, False, False, 0)

        self.search = Gtk.Entry()
        self.search.set_placeholder_text("Search apps")
        self.search.connect("changed", lambda *_: self.fill())
        self.search.connect("activate", self.launch_first)
        outer.pack_start(self.search, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        outer.pack_start(scroller, True, True, 0)

        self.grid = Gtk.FlowBox()
        self.grid.set_valign(Gtk.Align.START)
        self.grid.set_max_children_per_line(6)
        self.grid.set_min_children_per_line(3)
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_row_spacing(8)
        self.grid.set_column_spacing(8)
        scroller.add(self.grid)

        self.connect("key-press-event", self.on_key)
        self.fill()

    def fill(self) -> None:
        for child in self.grid.get_children():
            self.grid.remove(child)
        needle = self.search.get_text().strip().lower()
        for info in desktop_apps():
            name = info.get_name() or ""
            if needle and needle not in name.lower():
                continue
            self.grid.add(self.tile(info))

    def tile(self, info: Gio.AppInfo) -> Gtk.Widget:
        button = Gtk.Button()
        button.get_style_context().add_class("zaod-tile")
        button.set_relief(Gtk.ReliefStyle.NONE)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        icon = Gtk.Image()
        try:
            themed = info.get_icon()
            if themed is not None:
                icon.set_from_gicon(themed, Gtk.IconSize.DIALOG)
            else:
                icon.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        except GLib.Error:
            icon.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(48)
        inner.pack_start(icon, False, False, 0)
        label = Gtk.Label(label=info.get_name() or "")
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_max_width_chars(14)
        inner.pack_start(label, False, False, 0)
        button.add(inner)
        button.connect("clicked", lambda *_: self.launch(info))
        return button

    def launch(self, info: Gio.AppInfo) -> None:
        try:
            info.launch([], None)
        except GLib.Error as error:
            print(f"zaod-panel: cannot launch {info.get_name()}: {error}", file=sys.stderr)
        self.hide()

    def launch_first(self, *_args) -> None:
        children = self.grid.get_children()
        if not children:
            return
        button = children[0].get_child()
        if button is not None:
            button.clicked()

    def on_key(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False


class Panel(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_title("Zaod panel")
        self.launcher = Launcher()

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.get_style_context().add_class("zaod-bar")
        self.add(bar)

        brand = Gtk.Button(label="Zaod")
        brand.get_style_context().add_class("zaod-brand")
        brand.set_tooltip_text("All apps")
        brand.connect("clicked", self.toggle_launcher)
        bar.pack_start(brand, False, False, 0)

        for app_id in PINNED:
            info = app_for(app_id)
            if info is None:
                continue
            button = Gtk.Button()
            button.set_tooltip_text(info.get_name() or app_id)
            try:
                themed = info.get_icon()
                image = Gtk.Image()
                if themed is not None:
                    image.set_from_gicon(themed, Gtk.IconSize.BUTTON)
                else:
                    image.set_from_icon_name("application-x-executable", Gtk.IconSize.BUTTON)
                button.set_image(image)
            except GLib.Error:
                button.set_label((info.get_name() or app_id)[:2])
            button.connect("clicked", lambda _b, i=info: self.launch(i))
            bar.pack_start(button, False, False, 0)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.pack_start(spacer, True, True, 0)

        self.clock = Gtk.Label(label="")
        self.clock.get_style_context().add_class("zaod-clock")
        bar.pack_start(self.clock, False, False, 0)

        quick = Gtk.MenuButton()
        quick.set_relief(Gtk.ReliefStyle.NONE)
        quick.set_popover(self.build_quick_settings())
        quick.set_image(Gtk.Image.new_from_icon_name("preferences-system", Gtk.IconSize.BUTTON))
        quick.set_tooltip_text("Quick settings")
        bar.pack_end(quick, False, False, 0)

        self.connect("destroy", Gtk.main_quit)
        GLib.timeout_add_seconds(1, self.tick)
        self.tick()

    def tick(self) -> bool:
        self.clock.set_text(GLib.DateTime.new_now_local().format("%a %H:%M"))
        return True

    def toggle_launcher(self, *_args) -> None:
        if self.launcher.get_visible():
            self.launcher.hide()
            return
        self.launcher.show_all()
        self.launcher.present()
        self.launcher.search.grab_focus()

    def launch(self, info: Gio.AppInfo) -> None:
        try:
            info.launch([], None)
        except GLib.Error as error:
            print(f"zaod-panel: cannot launch {info.get_name()}: {error}", file=sys.stderr)

    def build_quick_settings(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        popover.get_style_context().add_class("zaod-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.get_style_context().add_class("zaod-popover")
        box.set_border_width(8)
        popover.add(box)

        theme = Gtk.Label(label=f"Theme: {theme_variant()}", xalign=0)
        box.pack_start(theme, False, False, 0)

        volume_label = Gtk.Label(label="Volume", xalign=0)
        volume_label.get_style_context().add_class("zaod-title")
        box.pack_start(volume_label, False, False, 0)
        volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        volume.set_value(60)
        volume.set_draw_value(False)
        volume.connect("value-changed", self.set_volume)
        box.pack_start(volume, False, False, 0)

        for label, command in (
            ("Lock", ["/usr/bin/labwc", "-k"]),
            ("Sleep", ["/usr/bin/systemctl", "suspend"]),
            ("Restart", ["/usr/bin/systemctl", "reboot"]),
            ("Shut down", ["/usr/bin/systemctl", "poweroff"]),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, c=command: run(*c))
            box.pack_start(button, False, False, 0)

        box.show_all()
        return popover

    def set_volume(self, scale: Gtk.Scale) -> None:
        level = int(scale.get_value())
        run("/usr/bin/pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%")


def attach(window: Gtk.Window) -> None:
    """Put the panel on the edge of the screen, layer-shell when available."""
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell as layer
    except (ValueError, ImportError):
        # No gtk-layer-shell: an undecorated window that asks the compositor to
        # keep it above everything is still a usable panel.
        window.set_keep_above(True)
        window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        return
    layer.init_for_window(window)
    layer.set_layer(window, layer.Layer.TOP)
    layer.set_anchor(window, layer.Edge.BOTTOM, True)
    layer.set_anchor(window, layer.Edge.LEFT, True)
    layer.set_anchor(window, layer.Edge.RIGHT, True)
    layer.set_margin(window, layer.Edge.BOTTOM, 8)
    layer.set_margin(window, layer.Edge.LEFT, 8)
    layer.set_margin(window, layer.Edge.RIGHT, 8)
    layer.set_exclusive_zone(window, HEIGHT + 8)
    layer.set_namespace(window, "zaod-panel")


def main() -> int:
    css = Gtk.CssProvider()
    css.load_from_data(CSS.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    panel = Panel()
    attach(panel)
    panel.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
