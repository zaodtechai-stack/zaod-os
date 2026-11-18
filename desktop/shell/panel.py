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
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

for candidate in ("/usr/lib/zaod", str(Path(__file__).resolve().parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

try:
    from connectivity import BluetoothManager, NetworkError, WifiManager
except ImportError:  # a panel without the network layer still has to start
    WifiManager = BluetoothManager = None

    class NetworkError(RuntimeError):
        """Raised when the network layer is not installed."""


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
/* quick settings: a compact control panel, not a wall of labels */
.zaod-quick-title {{
  color: {MUTED};
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  margin-top: 2px;
}}
.zaod-note {{
  color: {MUTED};
  font-size: 12px;
}}
.zaod-net-row {{
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  color: {TEXT};
  padding: 7px 10px;
  min-height: 22px;
}}
.zaod-net-row:hover {{
  background: rgba(76, 194, 255, 0.18);
  border-color: rgba(76, 194, 255, 0.45);
}}
.zaod-net-row:active {{
  background: rgba(76, 194, 255, 0.28);
}}
.zaod-quick-tile {{
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  color: {TEXT};
  padding: 8px 10px;
  min-height: 26px;
}}
.zaod-quick-tile:checked {{
  background: {ACCENT};
  border-color: {ACCENT};
  color: {ACCENT_TEXT};
  font-weight: 600;
}}
.zaod-quick-tile:hover {{
  border-color: rgba(255, 255, 255, 0.22);
}}
.zaod-quick-entry {{
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  color: {TEXT};
  padding: 7px 9px;
  caret-color: {ACCENT};
}}
.zaod-quick-entry:focus {{
  border-color: {ACCENT};
}}
scale.zaod-volume trough {{
  min-height: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
}}
scale.zaod-volume highlight {{
  border-radius: 999px;
  background: {ACCENT};
}}
scale.zaod-volume slider {{
  background: {TEXT};
  border-radius: 999px;
  min-width: 14px;
  min-height: 14px;
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


# Desktop entries that belong to the plumbing, not to the person using the
# computer. They shipped in /usr/share/applications, so the grid listed
# "Python 3.13" (with the Python logo), qt6ct, gvim, Xwayland and the portal
# helpers between the real apps. None of them is something you open on purpose.
HIDDEN_ENTRY_IDS = {
    "python3", "python3.13", "idle3", "idle", "qt6ct", "gvim", "vim",
    "xdg-desktop-portal-gtk", "org.freedesktop.Xwayland", "xwayland",
    "thunar-bulk-rename", "thunar-settings", "avahi-discover", "blueman-manager",
    "qv4l2", "qvidcap", "htop", "btop", "neofetch", "nvim", "micro",
}


def entry_is_hidden(app_id: str) -> bool:
    """True for toolkit and plumbing entries that should never be in the grid."""
    identifier = (app_id or "").removesuffix(".desktop")
    if identifier.startswith("org.zaod"):
        return False
    if identifier.lower() in HIDDEN_ENTRY_IDS:
        return True
    lowered = identifier.lower()
    parts = lowered.split(".")
    if lowered in HIDDEN_ENTRY_IDS or parts[-1] in HIDDEN_ENTRY_IDS:
        return True
    head = parts[0]
    return head.startswith("python") or head in {"gvim", "vim", "nvim"}


def desktop_apps() -> list[Gio.AppInfo]:
    apps = [a for a in Gio.AppInfo.get_all()
            if a.should_show() and not entry_is_hidden(a.get_id() or "")]
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
        # ---- quick settings state ----
        self.pending_ssid: str | None = None
        self._password_handler: int | None = None

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

    # ---- quick settings: Wi-Fi, Bluetooth, sound, battery, power ----------
    def build_quick_settings(self) -> Gtk.Popover:
        """The control panel behind the clock.

        Wi-Fi here is the real thing: it lists the networks nmcli can see, asks
        for the password of a secured one and only then joins it, and says what
        went wrong instead of failing silently.
        """
        popover = Gtk.Popover()
        popover.get_style_context().add_class("zaod-popover")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.get_style_context().add_class("zaod-popover")
        box.set_border_width(12)
        box.set_size_request(340, -1)
        popover.add(box)

        self.wifi = WifiManager() if WifiManager else None
        self.bluetooth = BluetoothManager() if BluetoothManager else None
        self.net_status = Gtk.Label(label="", xalign=0)
        self.net_status.get_style_context().add_class("zaod-note")
        self.net_status.set_line_wrap(True)
        self.net_password = Gtk.Entry()
        self.net_password.set_visibility(False)
        self.net_password.set_placeholder_text("Wi-Fi password")
        self.net_password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.net_connect = Gtk.Button(label="Connect")
        self.net_password_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.net_password_row.pack_start(self.net_password, True, True, 0)
        self.net_password_row.pack_start(self.net_connect, False, False, 0)
        self.net_password_row.hide()
        self.pending_ssid = ""

        # tiles: Wi-Fi, Bluetooth, night light
        tiles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.wifi_tile = Gtk.ToggleButton(label="Wi-Fi")
        self.wifi_tile.get_style_context().add_class("zaod-tile")
        self.wifi_tile.connect("toggled", self.on_wifi_toggle)

        self.bt_tile = Gtk.ToggleButton(label="Bluetooth")
        self.bt_tile.get_style_context().add_class("zaod-tile")
        self.bt_tile.connect("toggled", self.on_bt_toggle)

        night = Gtk.ToggleButton(label="Night light")
        night.get_style_context().add_class("zaod-tile")
        night.connect("toggled", self.on_night_light)

        for tile in (self.wifi_tile, self.bt_tile, night):
            tiles.pack_start(tile, True, True, 0)
        box.pack_start(tiles, False, False, 0)

        box.pack_start(self.net_status, False, False, 0)
        self.net_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(self.net_list, False, False, 0)
        box.pack_start(self.net_password_row, False, False, 0)

        refresh = Gtk.Button(label="Scan for networks")
        refresh.connect("clicked", lambda _b: self.refresh_networks(scan=True))
        box.pack_start(refresh, False, False, 0)

        # sound
        volume_title = Gtk.Label(label="Volume", xalign=0)
        volume_title.get_style_context().add_class("zaod-title")
        box.pack_start(volume_title, False, False, 0)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.volume.set_draw_value(False)
        self.volume.set_value(self.read_volume())
        self.volume.get_style_context().add_class("zaod-volume")
        self.volume.connect("value-changed", self.set_volume)
        box.pack_start(self.volume, False, False, 0)

        self.battery_label = Gtk.Label(label=self.battery_text(), xalign=0)
        self.battery_label.get_style_context().add_class("zaod-note")
        box.pack_start(self.battery_label, False, False, 0)

        power_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for label, command in (
            ("Lock", ["/usr/bin/labwc", "-k"]),
            ("Reboot", ["/usr/bin/systemctl", "reboot"]),
            ("Shut down", ["/usr/bin/systemctl", "poweroff"]),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", lambda _b, c=command: run(*c))
            power_row.pack_start(button, True, True, 0)
        box.pack_start(power_row, False, False, 0)

        popover.connect("show", self.on_quick_shown)
        box.show_all()
        self.net_password_row.hide()
        return popover

    # ---- networking --------------------------------------------------------
    def on_quick_shown(self, *_args) -> None:
        self.battery_label.set_text(self.battery_text())
        if self.wifi is not None:
            try:
                self.wifi_tile.set_active(self.wifi.radio_enabled())
            except NetworkError:
                pass
            self.refresh_networks(scan=False)
        else:
            self.net_status.set_text("The network layer is not installed.")

    def refresh_networks(self, scan: bool = True) -> None:
        if self.wifi is None:
            return
        for child in self.net_list.get_children():
            child.destroy()
        self.net_status.set_text("Looking for networks…")

        def work() -> None:
            try:
                points = self.wifi.scan(rescan=scan)
                # active() returns (ssid, ip) or None; the menu only says what it
                # is joined to, so keep the name.
                active = self.wifi.active()
                connected = active[0] if active else None
                error = None
            except NetworkError as exc:
                points, connected, error = [], None, str(exc)
            GLib.idle_add(self.show_networks, points, connected, error)

        threading.Thread(target=work, daemon=True).start()

    def show_networks(self, points, connected, error) -> bool:
        for child in self.net_list.get_children():
            child.destroy()
        if error:
            self.net_status.set_text(error)
            return False
        if not points:
            self.net_status.set_text("No networks found nearby.")
            return False
        self.net_status.set_text(
            f"Connected to {connected}" if connected else f"{len(points)} networks nearby"
        )
        for point in points:
            label = f"{point.ssid}   {point.signal}%"
            if point.secured:
                label += "  🔒"
            if point.in_use:
                label += "  ✓"
            button = Gtk.Button(label=label)
            button.get_style_context().add_class("zaod-net-row")
            button.connect("clicked", self.on_network_clicked, point)
            button.show()
            self.net_list.pack_start(button, False, False, 0)
        return False

    def on_network_clicked(self, _button, point) -> None:
        if point.in_use:
            self.tell(self.wifi.disconnect())
            self.refresh_networks(scan=False)
            return
        if not point.secured:
            self.join_network(point.ssid, None)
            return
        self.pending_ssid = point.ssid
        self.net_password.set_text("")
        self.net_status.set_text(f"{point.ssid} needs its password.")
        self.net_password_row.show_all()
        try:
            self.net_connect.handler_disconnect(self._password_handler)
        except (AttributeError, TypeError):
            pass
        self._password_handler = self.net_connect.connect("clicked", self.submit_password)
        self.net_password.grab_focus()

    def submit_password(self, *_args) -> None:
        secret = self.net_password.get_text()
        ssid = self.pending_ssid
        if not ssid:
            return
        if len(secret) < 8:
            self.net_status.set_text("A Wi-Fi password is at least 8 characters.")
            return
        self.net_password_row.hide()
        self.join_network(ssid, secret)

    def join_network(self, ssid: str, secret: str | None) -> None:
        self.net_status.set_text(f"Connecting to {ssid}…")

        def work() -> None:
            try:
                message, error = self.wifi.connect(ssid, secret), None
            except NetworkError as exc:
                message, error = None, str(exc)
            GLib.idle_add(self.finish_join, message, error)

        threading.Thread(target=work, daemon=True).start()

    def finish_join(self, message, error) -> bool:
        if error:
            self.net_status.set_text(error)
            if "password" in error.lower():
                self.net_password_row.show_all()
                self.net_password.set_text("")
                self.net_password.grab_focus()
        else:
            self.net_status.set_text(message or "Connected.")
        self.refresh_networks(scan=False)
        return False

    def tell(self, message: str) -> None:
        self.net_status.set_text(message)

    def on_wifi_toggle(self, tile: Gtk.ToggleButton) -> None:
        if self.wifi is None:
            return
        want = tile.get_active()

        def work() -> None:
            try:
                self.wifi.set_radio(want)
                self.wifi_radio_error = None
            except NetworkError as exc:
                self.wifi_radio_error = str(exc)
            GLib.idle_add(self.after_radio, want)

        threading.Thread(target=work, daemon=True).start()

    def after_radio(self, want: bool) -> bool:
        error = getattr(self, "wifi_radio_error", None)
        if error:
            self.net_status.set_text(error)
            self.wifi_tile.set_active(not want)
        else:
            self.net_status.set_text("Wi-Fi on." if want else "Wi-Fi off.")
        self.refresh_networks(scan=want)
        return False

    def on_bt_toggle(self, tile: Gtk.ToggleButton) -> None:
        if self.bluetooth is None:
            return
        want = tile.get_active()

        def work() -> None:
            try:
                message = self.bluetooth.set_power(want)
                error = None
            except NetworkError as exc:
                message, error = None, str(exc)
            GLib.idle_add(self.finish_bt, tile, message, error)

        threading.Thread(target=work, daemon=True).start()

    def finish_bt(self, tile, message, error) -> bool:
        if error:
            self.net_status.set_text(error)
            tile.set_active(not tile.get_active())
        else:
            self.net_status.set_text(message or "Bluetooth updated.")
        return False

    def on_night_light(self, tile: Gtk.ToggleButton) -> None:
        if tile.get_active():
            run("/usr/bin/wlsunset", "-T", "4500", "-t", "3500")
        else:
            run("/usr/bin/pkill", "-x", "wlsunset")

    # ---- sound and battery -------------------------------------------------
    def read_volume(self) -> float:
        try:
            out = subprocess.run(
                ["/usr/bin/wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
            return float(out.split()[1]) * 100 if out.split() else 60.0
        except (OSError, ValueError, IndexError):
            return 60.0

    def set_volume(self, scale: Gtk.Scale) -> None:
        level = int(scale.get_value())
        # pipewire is the only sound server in the image, so wpctl is the tool
        # that is actually there; pactl used to be called and never existed.
        run("/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{level}%")

    def battery_text(self) -> str:
        for supply in Path("/sys/class/power_supply").glob("BAT*"):
            try:
                charge = int((supply / "capacity").read_text().strip())
                state = (supply / "status").read_text().strip().lower()
            except (OSError, ValueError):
                continue
            suffix = " (charging)" if state == "charging" else ""
            return f"Battery {charge}%{suffix}"
        return "Battery: mains power"


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
