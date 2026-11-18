#!/usr/bin/env python3
"""Zaod Control Center: Wi-Fi, Bluetooth, appearance, display, sound and system.

A sidebar of sections on the left and one page on the right. Every control does
something real:

* Wi-Fi scans through NetworkManager, lists the networks around you with their
  signal and security, asks for the password only when the network needs one and
  tells you plainly when it was wrong;
* Bluetooth powers the adapter, scans, pairs, connects and removes devices;
* the other pages change the theme, text size, wallpaper, volume, brightness,
  scale and night light through the same tools the session uses.

Anything slow (a scan, a connection attempt, a pairing) runs on a worker thread,
so the window never freezes while the radio works.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))

import zaodapp
from connectivity import BluetoothManager, NetworkError, WifiManager
from settings import (
    ACCENTS,
    SettingError,
    Settings,
    battery,
    brightness_available,
    get_brightness,
    get_volume,
    outputs,
    set_brightness,
    set_mute,
    set_night_light,
    set_scale,
    set_volume,
    system_facts,
)

WALLPAPERS = Path("/usr/share/wallpapers/zaod/collection")
SECTIONS = ("Wi-Fi", "Bluetooth", "Appearance", "Display", "Sound", "Power", "System")


def build_window(
    wifi: WifiManager | None = None,
    bluetooth: BluetoothManager | None = None,
    settings: Settings | None = None,
):
    from PySide6.QtCore import (
        QObject,
        QRunnable,
        QSize,
        Qt,
        QThreadPool,
        QTimer,
        Signal,
    )
    from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (
        QCheckBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QSlider,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    wifi = wifi or WifiManager()
    bluetooth = bluetooth or BluetoothManager()
    store = settings or Settings()
    pool = QThreadPool.globalInstance()
    c = zaodapp.palette()

    window = zaodapp.base_window("Settings", 980, 640, margins=0)
    window.heading.hide()

    # ---- helpers ----------------------------------------------------------------
    class Signals(QObject):
        done = Signal(object)
        failed = Signal(str)

    class Job(QRunnable):
        """Run ``fn`` off the GUI thread and hand the result back through signals."""

        def __init__(self, fn):
            super().__init__()
            self.fn = fn
            self.signals = Signals()

        def run(self):
            """Do the work, then report - unless the page is already gone.

            Switching pages deletes the widgets a job was going to report to, and
            emitting into a deleted signal source raised
            "RuntimeError: Signal source has been deleted" in the terminal. The
            answer is simply not needed any more, so it is dropped.
            """
            try:
                result = self.fn()
            except (NetworkError, SettingError) as error:
                self._emit(self.signals.failed, str(error))
            except Exception as error:  # noqa: BLE001 - shown to the person, never swallowed
                self._emit(self.signals.failed, f"{type(error).__name__}: {error}")
            else:
                self._emit(self.signals.done, result)

        @staticmethod
        def _emit(signal, payload) -> None:
            try:
                signal.emit(payload)
            except RuntimeError:
                pass  # the widget that would show it has been closed or replaced

    jobs: list[Job] = []

    def background(fn, on_done=None, on_fail=None):
        job = Job(fn)
        jobs.append(job)

        def finish(result):
            if job in jobs:
                jobs.remove(job)
            if on_done:
                on_done(result)

        def fail(message):
            if job in jobs:
                jobs.remove(job)
            if on_fail:
                on_fail(message)

        job.signals.done.connect(finish)
        job.signals.failed.connect(fail)
        pool.start(job)

    def label(text="", name=None, wrap=True):
        widget = QLabel(text)
        if name:
            widget.setObjectName(name)
        widget.setWordWrap(wrap)
        return widget

    def section_title(text):
        return label(text.upper(), "sectionTitle", wrap=False)

    def panel():
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        return frame, layout

    def switch_row(title, subtitle, checked=False):
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title))
        if subtitle:
            text.addWidget(label(subtitle, "muted"))
        row.addLayout(text, 1)
        box = QCheckBox("")
        box.setChecked(checked)
        row.addWidget(box)
        return row, box

    def tint(name, colour):
        pixmap = QIcon.fromTheme(name).pixmap(QSize(20, 20))
        if pixmap.isNull():
            return QIcon()
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(colour))
        painter.end()
        return QIcon(pixmap)

    def bars_icon(count, secured):
        pixmap = QPixmap(30, 22)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index in range(4):
            height = 5 + index * 4
            colour = QColor(c["accent"] if index < count else c["textDisabled"])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(2 + index * 6, 20 - height, 4, height, 1, 1)
        if secured:
            painter.setPen(QPen(QColor(c["textSecondary"]), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(25, 12, 5, 6, 1, 1)
            painter.drawArc(25, 8, 5, 6, 0, 180 * 16)
        painter.end()
        return QIcon(pixmap)

    # ---- shell ------------------------------------------------------------------
    shell = QHBoxLayout()
    shell.setContentsMargins(0, 0, 0, 0)
    shell.setSpacing(0)
    window.content.addLayout(shell, 1)

    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(220)
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(12, 16, 12, 12)
    side.setSpacing(2)
    title = label("Settings", "hero", wrap=False)
    side.addWidget(title)
    side.addSpacing(10)
    stack = QStackedWidget()
    nav_buttons: dict[str, QPushButton] = {}

    def show_section(name):
        stack.setCurrentIndex(SECTIONS.index(name))
        for key, button in nav_buttons.items():
            button.setChecked(key == name)
        on_show.get(name, lambda: None)()

    for name in SECTIONS:
        button = QPushButton(name)
        button.setObjectName("nav")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.clicked.connect(lambda _c=False, n=name: show_section(n))
        nav_buttons[name] = button
        side.addWidget(button)
    side.addStretch(1)

    page_host = QWidget()
    page_layout = QVBoxLayout(page_host)
    page_layout.setContentsMargins(28, 24, 28, 12)
    page_layout.setSpacing(12)
    page_layout.addWidget(stack, 1)
    status = label("", "muted")
    status.setMinimumHeight(20)
    page_layout.addWidget(status)
    shell.addWidget(sidebar)
    shell.addWidget(page_host, 1)

    def report(message, error=False):
        status.setText(message)
        status.setObjectName("danger" if error else "muted")
        status.style().unpolish(status)
        status.style().polish(status)

    def page(title_text, subtitle=""):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label(title_text, "title", wrap=False))
        if subtitle:
            layout.addWidget(label(subtitle, "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        inner = QVBoxLayout(body)
        inner.setContentsMargins(0, 0, 8, 0)
        inner.setSpacing(12)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        stack.addWidget(host)
        return inner

    on_show: dict[str, callable] = {}

    # ===================================================================== Wi-Fi
    wifi_body = page("Wi-Fi", "Connect to a network around you.")
    wifi_card, wifi_card_layout = panel()
    wifi_row, wifi_switch = switch_row("Wi-Fi", "Turn the wireless radio on or off")
    wifi_card_layout.addLayout(wifi_row)
    wifi_connected = label("", "muted")
    wifi_card_layout.addWidget(wifi_connected)
    wifi_body.addWidget(wifi_card)

    wifi_header = QHBoxLayout()
    wifi_header.addWidget(section_title("Networks nearby"), 1)
    wifi_scan = QPushButton("Scan")
    wifi_scan.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    wifi_header.addWidget(wifi_scan)
    wifi_body.addLayout(wifi_header)

    wifi_list_card, wifi_list_layout = panel()
    wifi_list_layout.setSpacing(2)
    wifi_body.addWidget(wifi_list_card)

    # the password prompt appears inline under the network that was picked
    prompt = QFrame()
    prompt.setObjectName("panel")
    prompt_layout = QVBoxLayout(prompt)
    prompt_layout.setContentsMargins(16, 14, 16, 14)
    prompt_layout.setSpacing(8)
    prompt_title = label("", "hero", wrap=False)
    prompt_hint = label("", "muted")
    password = QLineEdit()
    password.setEchoMode(QLineEdit.EchoMode.Password)
    password.setPlaceholderText("Network password")
    reveal = QCheckBox("Show password")
    prompt_buttons = QHBoxLayout()
    prompt_connect = QPushButton("Connect")
    prompt_connect.setObjectName("primary")
    prompt_cancel = QPushButton("Cancel")
    prompt_buttons.addStretch(1)
    prompt_buttons.addWidget(prompt_cancel)
    prompt_buttons.addWidget(prompt_connect)
    for widget in (prompt_title, prompt_hint, password, reveal):
        prompt_layout.addWidget(widget)
    prompt_layout.addLayout(prompt_buttons)
    prompt.hide()
    wifi_body.addWidget(prompt)
    wifi_body.addStretch(1)

    wifi_state = {"selected": None, "busy": False, "points": [], "saved": set()}

    def wifi_rows(points):
        while wifi_list_layout.count():
            item = wifi_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not points:
            wifi_list_layout.addWidget(label("No networks found. Press Scan to look again.", "muted"))
            return
        for point in points:
            row = QPushButton()
            row.setObjectName("nav")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            row.setMinimumHeight(44)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 0, 8, 0)
            icon = QLabel()
            icon.setPixmap(bars_icon(point.bars, point.secured).pixmap(QSize(30, 22)))
            icon.setFixedWidth(34)
            layout.addWidget(icon)
            name = QLabel(point.ssid)
            name.setStyleSheet(f"font-weight: {'600' if point.in_use else '400'}; color: {c['textPrimary']};")
            layout.addWidget(name, 1)
            detail = []
            if point.in_use:
                detail.append("Connected")
            elif point.ssid in wifi_state["saved"]:
                detail.append("Saved")
            detail.append(point.security if point.secured else "Open")
            tag = QLabel("  ·  ".join(detail))
            tag.setObjectName("caption")
            layout.addWidget(tag)
            row.clicked.connect(lambda _c=False, p=point: choose_network(p))
            wifi_list_layout.addWidget(row)

    def refresh_wifi(rescan=True):
        if wifi_state["busy"]:
            return
        wifi_state["busy"] = True
        wifi_scan.setEnabled(False)
        wifi_scan.setText("Scanning…")
        report("Looking for networks…")

        def work():
            enabled = wifi.radio_enabled()
            if not enabled:
                return {"enabled": False}
            if not wifi.has_adapter():
                return {"enabled": True, "adapter": False}
            points = wifi.scan(rescan=rescan)
            return {
                "enabled": True,
                "adapter": True,
                "points": points,
                "saved": wifi.saved_profiles(),
                "active": wifi.active(),
            }

        def done(result):
            wifi_state["busy"] = False
            wifi_scan.setEnabled(True)
            wifi_scan.setText("Scan")
            wifi_switch.blockSignals(True)
            wifi_switch.setChecked(result["enabled"])
            wifi_switch.blockSignals(False)
            if not result["enabled"]:
                wifi_rows([])
                wifi_connected.setText("Wi-Fi is off.")
                report("Wi-Fi is turned off.")
                return
            if not result.get("adapter", True):
                wifi_rows([])
                wifi_connected.setText("No Wi-Fi adapter was found on this computer.")
                report("No Wi-Fi adapter found.", error=True)
                return
            wifi_state["points"] = result["points"]
            wifi_state["saved"] = result["saved"]
            wifi_rows(result["points"])
            active = result["active"]
            wifi_connected.setText(
                f"Connected to {active[0]}" + (f"  ·  {active[1]}" if active[1] else "") if active else "Not connected"
            )
            report(f"{len(result['points'])} networks found")

        def fail(message):
            wifi_state["busy"] = False
            wifi_scan.setEnabled(True)
            wifi_scan.setText("Scan")
            report(message, error=True)

        background(work, done, fail)

    def choose_network(point):
        wifi_state["selected"] = point
        password.clear()
        reveal.setChecked(False)
        password.setEchoMode(QLineEdit.EchoMode.Password)
        if point.in_use:
            prompt_title.setText(point.ssid)
            prompt_hint.setText("You are connected to this network.")
            password.hide()
            reveal.hide()
            prompt_connect.setText("Disconnect")
        elif point.ssid in wifi_state["saved"]:
            prompt_title.setText(point.ssid)
            prompt_hint.setText("This network is saved. Connect, or forget it to enter a new password.")
            password.hide()
            reveal.hide()
            prompt_connect.setText("Connect")
        elif point.secured:
            prompt_title.setText(point.ssid)
            prompt_hint.setText(f"{point.security} network. Enter its password.")
            password.show()
            reveal.show()
            prompt_connect.setText("Connect")
        else:
            prompt_title.setText(point.ssid)
            prompt_hint.setText("Open network. Anyone nearby can see what you send over it.")
            password.hide()
            reveal.hide()
            prompt_connect.setText("Connect")
        prompt.show()
        if password.isVisible():
            password.setFocus()

    def submit_network():
        point = wifi_state["selected"]
        if point is None or wifi_state["busy"]:
            return
        secret = password.text() if password.isVisible() else None
        if password.isVisible() and len(secret) < 8:
            report("A Wi-Fi password is at least 8 characters.", error=True)
            return
        wifi_state["busy"] = True
        prompt_connect.setEnabled(False)

        if point.in_use:
            report(f"Disconnecting from {point.ssid}…")
            work = wifi.disconnect
        else:
            report(f"Connecting to {point.ssid}…")

            def work():
                return wifi.connect(point.ssid, secret)

        def done(message):
            wifi_state["busy"] = False
            prompt_connect.setEnabled(True)
            prompt.hide()
            password.clear()
            report(message)
            refresh_wifi(rescan=False)

        def fail(message):
            wifi_state["busy"] = False
            prompt_connect.setEnabled(True)
            password.clear()
            report(message, error=True)
            prompt_hint.setText(message)
            if password.isVisible():
                password.setFocus()

        background(work, done, fail)

    def forget_network():
        point = wifi_state["selected"]
        if point is None:
            return
        try:
            report(wifi.forget(point.ssid))
        except NetworkError as error:
            report(str(error), error=True)
            return
        prompt.hide()
        refresh_wifi(rescan=False)

    forget = QPushButton("Forget")
    forget.setObjectName("danger")
    prompt_buttons.insertWidget(0, forget)
    forget.clicked.connect(forget_network)
    prompt_connect.clicked.connect(submit_network)
    prompt_cancel.clicked.connect(prompt.hide)
    password.returnPressed.connect(submit_network)
    reveal.toggled.connect(
        lambda on: password.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
    )
    wifi_scan.clicked.connect(lambda: refresh_wifi(rescan=True))

    def toggle_wifi(on):
        try:
            wifi.set_radio(on)
        except NetworkError as error:
            report(str(error), error=True)
            wifi_switch.blockSignals(True)
            wifi_switch.setChecked(not on)
            wifi_switch.blockSignals(False)
            return
        report("Wi-Fi on" if on else "Wi-Fi off")
        prompt.hide()
        QTimer.singleShot(1800 if on else 0, lambda: refresh_wifi(rescan=True))

    wifi_switch.toggled.connect(toggle_wifi)
    on_show["Wi-Fi"] = lambda: refresh_wifi(rescan=True)

    # ================================================================= Bluetooth
    bt_body = page("Bluetooth", "Pair headphones, speakers, keyboards and more.")
    bt_card, bt_card_layout = panel()
    bt_row, bt_switch = switch_row("Bluetooth", "Turn the adapter on or off")
    bt_card_layout.addLayout(bt_row)
    bt_note = label("", "muted")
    bt_card_layout.addWidget(bt_note)
    bt_body.addWidget(bt_card)
    bt_header = QHBoxLayout()
    bt_header.addWidget(section_title("Devices"), 1)
    bt_scan = QPushButton("Scan")
    bt_scan.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    bt_header.addWidget(bt_scan)
    bt_body.addLayout(bt_header)
    bt_list_card, bt_list_layout = panel()
    bt_list_layout.setSpacing(2)
    bt_body.addWidget(bt_list_card)
    bt_body.addStretch(1)
    bt_state = {"busy": False}

    def bt_rows(devices):
        while bt_list_layout.count():
            item = bt_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
        if not devices:
            bt_list_layout.addWidget(label("No devices yet. Put one in pairing mode and press Scan.", "muted"))
            return
        for device in devices:
            row = QHBoxLayout()
            row.setSpacing(8)
            text = QVBoxLayout()
            text.setSpacing(0)
            name = QLabel(device.name)
            name.setStyleSheet(f"font-weight: 600; color: {c['textPrimary']};")
            text.addWidget(name)
            state_text = "Connected" if device.connected else ("Paired" if device.paired else "Not paired")
            kind = device.icon.replace("-", " ").title() if device.icon else "Device"
            sub = QLabel(f"{state_text}  ·  {kind}")
            sub.setObjectName("caption")
            text.addWidget(sub)
            row.addLayout(text, 1)
            if device.connected:
                action = QPushButton("Disconnect")
                action.clicked.connect(lambda _c=False, d=device: bt_do(d, "disconnect"))
            elif device.paired:
                action = QPushButton("Connect")
                action.setObjectName("primary")
                action.clicked.connect(lambda _c=False, d=device: bt_do(d, "connect"))
            else:
                action = QPushButton("Pair")
                action.setObjectName("primary")
                action.clicked.connect(lambda _c=False, d=device: bt_do(d, "pair"))
            row.addWidget(action)
            if device.paired:
                remove = QPushButton("Remove")
                remove.setObjectName("danger")
                remove.clicked.connect(lambda _c=False, d=device: bt_do(d, "remove"))
                row.addWidget(remove)
            holder = QWidget()
            holder.setLayout(row)
            holder.setMinimumHeight(48)
            bt_list_layout.addWidget(holder)

    def refresh_bt(scan=False):
        if bt_state["busy"]:
            return
        bt_state["busy"] = True
        bt_scan.setEnabled(False)
        bt_scan.setText("Scanning…" if scan else "Scan")
        report("Looking for Bluetooth devices…" if scan else "")

        def work():
            if not bluetooth.available():
                return {"available": False}
            powered = bluetooth.powered()
            devices = []
            if powered:
                devices = bluetooth.scan(seconds=8) if scan else bluetooth.devices()
            return {"available": True, "powered": powered, "devices": devices}

        def done(result):
            bt_state["busy"] = False
            bt_scan.setEnabled(True)
            bt_scan.setText("Scan")
            bt_switch.blockSignals(True)
            if not result["available"]:
                bt_switch.setChecked(False)
                bt_switch.setEnabled(False)
                bt_scan.setEnabled(False)
                bt_note.setText("No Bluetooth adapter was found on this computer.")
                bt_rows([])
            else:
                bt_switch.setEnabled(True)
                bt_switch.setChecked(result["powered"])
                bt_note.setText("" if result["powered"] else "Bluetooth is off.")
                bt_rows(result["devices"])
                if scan:
                    report(f"{len(result['devices'])} devices found")
            bt_switch.blockSignals(False)

        def fail(message):
            bt_state["busy"] = False
            bt_scan.setEnabled(True)
            bt_scan.setText("Scan")
            report(message, error=True)

        background(work, done, fail)

    def bt_do(device, action):
        if bt_state["busy"]:
            return
        bt_state["busy"] = True
        report({"pair": f"Pairing with {device.name}…", "connect": f"Connecting to {device.name}…"}.get(action, "Working…"))
        operation = {
            "pair": bluetooth.pair,
            "connect": bluetooth.connect,
            "disconnect": bluetooth.disconnect,
            "remove": bluetooth.remove,
        }[action]

        def done(message):
            bt_state["busy"] = False
            report(message)
            refresh_bt()

        def fail(message):
            bt_state["busy"] = False
            report(message, error=True)

        background(lambda: operation(device.address), done, fail)

    def toggle_bt(on):
        try:
            bluetooth.set_power(on)
        except NetworkError as error:
            report(str(error), error=True)
            bt_switch.blockSignals(True)
            bt_switch.setChecked(not on)
            bt_switch.blockSignals(False)
            return
        report("Bluetooth on" if on else "Bluetooth off")
        refresh_bt(scan=on)

    bt_switch.toggled.connect(toggle_bt)
    bt_scan.clicked.connect(lambda: refresh_bt(scan=True))
    on_show["Bluetooth"] = lambda: refresh_bt(scan=False)

    # =============================================================== Appearance
    look_body = page("Appearance", "Theme, accent colour, text size and wallpaper.")
    look_card, look_layout = panel()

    theme_row = QHBoxLayout()
    theme_row.addWidget(label("Theme"), 1)
    theme_buttons = {}
    for mode in ("light", "dark"):
        button = QPushButton(mode.title())
        button.setObjectName("chip")
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        theme_buttons[mode] = button
        theme_row.addWidget(button)
    look_layout.addLayout(theme_row)

    accent_row = QHBoxLayout()
    accent_row.addWidget(label("Accent colour"), 1)
    accent_buttons = {}
    for key, (bright, _deep) in ACCENTS.items():
        button = QPushButton("")
        button.setCheckable(True)
        button.setFixedSize(QSize(28, 28))
        button.setToolTip(key.title())
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setStyleSheet(
            f"QPushButton {{ background: {bright}; border: 2px solid transparent; border-radius: 14px; padding: 0; }}"
            f"QPushButton:checked {{ border: 2px solid {c['textPrimary']}; }}"
        )
        accent_buttons[key] = button
        accent_row.addWidget(button)
    look_layout.addLayout(accent_row)

    scale_row = QHBoxLayout()
    scale_row.addWidget(label("Text size"), 1)
    scale_label = label("100%", "muted", wrap=False)
    scale_slider = QSlider(Qt.Orientation.Horizontal)
    scale_slider.setRange(100, 150)
    scale_slider.setSingleStep(10)
    scale_slider.setFixedWidth(200)
    scale_row.addWidget(scale_slider)
    scale_row.addWidget(scale_label)
    look_layout.addLayout(scale_row)
    look_layout.addWidget(label("Theme, accent and text size apply to apps you open from now on.", "caption"))
    look_body.addWidget(look_card)

    look_body.addWidget(section_title("Wallpaper"))
    wall_card, wall_layout_ = panel()
    wall_grid = QGridLayout()
    wall_grid.setSpacing(10)
    wall_layout_.addLayout(wall_grid)
    look_body.addWidget(wall_card)
    look_body.addStretch(1)
    wall_buttons: list[QPushButton] = []

    def apply_wallpaper(slug, button):
        image = WALLPAPERS / slug
        if not image.is_file():
            report(f"{slug} is missing", error=True)
            return
        try:
            store.set("wallpaper", str(image))
        except SettingError as error:
            report(str(error), error=True)
            return
        for other in wall_buttons:
            other.setChecked(other is button)
        subprocess.run(["pkill", "-x", "swaybg"], check=False, capture_output=True)
        if os.environ.get("WAYLAND_DISPLAY"):
            subprocess.Popen(
                ["swaybg", "-i", str(image), "-m", "fill"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        report("Wallpaper changed")

    def build_wallpapers():
        chosen = store.get("wallpaper") or ""
        thumbs = sorted((WALLPAPERS / "thumbs").glob("*.jpg"))
        for index, thumb in enumerate(thumbs):
            button = QPushButton()
            button.setObjectName("tile")
            button.setCheckable(True)
            button.setChecked(chosen.endswith(thumb.name))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(QSize(176, 108))
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setToolTip(thumb.stem.replace("zaod-", "").replace("-", " ").title())
            pixmap = QPixmap(str(thumb))
            if not pixmap.isNull():
                button.setIcon(
                    QIcon(
                        pixmap.scaled(
                            QSize(168, 100),
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                )
                button.setIconSize(QSize(168, 100))
            button.clicked.connect(lambda _c=False, n=thumb.name, b=button: apply_wallpaper(n, b))
            wall_buttons.append(button)
            wall_grid.addWidget(button, index // 4, index % 4)

    build_wallpapers()

    def pick_theme(mode):
        store.set("theme", mode)
        for key, button in theme_buttons.items():
            button.setChecked(key == mode)
        report(f"{mode.title()} theme saved. New apps will use it.")

    def pick_accent(key):
        store.set("accent", key)
        for other, button in accent_buttons.items():
            button.setChecked(other == key)
        report(f"{key.title()} accent saved.")

    def pick_scale(value):
        value = round(value / 10) * 10
        scale_label.setText(f"{value}%")

    def save_scale():
        value = round(scale_slider.value() / 10) * 10
        store.set("text_scale", value)
        report(f"Text size {value}% saved. New apps will use it.")

    for mode, button in theme_buttons.items():
        button.clicked.connect(lambda _c=False, m=mode: pick_theme(m))
    for key, button in accent_buttons.items():
        button.clicked.connect(lambda _c=False, k=key: pick_accent(k))
    scale_slider.valueChanged.connect(pick_scale)
    scale_slider.sliderReleased.connect(save_scale)

    def load_look():
        data = store.load()
        for key, button in theme_buttons.items():
            button.setChecked(key == data["theme"])
        for key, button in accent_buttons.items():
            button.setChecked(key == data["accent"])
        scale_slider.setValue(int(data["text_scale"]))

    on_show["Appearance"] = load_look

    # ================================================================== Display
    display_body = page("Display", "Brightness, scale and night light.")
    display_card, display_layout = panel()
    bright_row = QHBoxLayout()
    bright_row.addWidget(label("Brightness"), 1)
    bright_slider = QSlider(Qt.Orientation.Horizontal)
    bright_slider.setRange(5, 100)
    bright_slider.setFixedWidth(240)
    bright_value = label("", "muted", wrap=False)
    bright_row.addWidget(bright_slider)
    bright_row.addWidget(bright_value)
    display_layout.addLayout(bright_row)
    bright_note = label("", "caption")
    display_layout.addWidget(bright_note)

    scale_choices = QHBoxLayout()
    scale_choices.addWidget(label("Display scale"), 1)
    display_scale_buttons = {}
    for value in (1.0, 1.25, 1.5, 2.0):
        button = QPushButton(f"{int(value * 100)}%")
        button.setObjectName("chip")
        button.setCheckable(True)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        display_scale_buttons[value] = button
        scale_choices.addWidget(button)
    display_layout.addLayout(scale_choices)
    night_row, night_switch = switch_row("Night light", "Warmer colours in the evening")
    display_layout.addLayout(night_row)
    display_body.addWidget(display_card)
    display_body.addStretch(1)

    def load_display():
        if brightness_available():
            try:
                level = get_brightness()
                bright_slider.blockSignals(True)
                bright_slider.setValue(level)
                bright_slider.blockSignals(False)
                bright_value.setText(f"{level}%")
                bright_slider.setEnabled(True)
                bright_note.setText("")
            except SettingError as error:
                bright_slider.setEnabled(False)
                bright_note.setText(str(error))
        else:
            bright_slider.setEnabled(False)
            bright_note.setText("This screen has no software brightness control.")
        try:
            current = outputs()
            scale = current[0]["scale"] if current else 1.0
        except SettingError:
            scale = None
        for value, button in display_scale_buttons.items():
            button.setEnabled(scale is not None)
            button.setChecked(scale is not None and abs(value - scale) < 0.01)
        night_switch.blockSignals(True)
        night_switch.setChecked(bool(store.get("night_light")))
        night_switch.blockSignals(False)

    def apply_brightness(value):
        bright_value.setText(f"{value}%")

    def commit_brightness():
        try:
            report(set_brightness(bright_slider.value()))
        except SettingError as error:
            report(str(error), error=True)

    def apply_display_scale(value):
        try:
            report(set_scale(value))
        except SettingError as error:
            report(str(error), error=True)
            return
        for key, button in display_scale_buttons.items():
            button.setChecked(key == value)

    def apply_night(on):
        try:
            report(set_night_light(on))
            store.set("night_light", on)
        except SettingError as error:
            report(str(error), error=True)
            night_switch.blockSignals(True)
            night_switch.setChecked(not on)
            night_switch.blockSignals(False)

    bright_slider.valueChanged.connect(apply_brightness)
    bright_slider.sliderReleased.connect(commit_brightness)
    for value, button in display_scale_buttons.items():
        button.clicked.connect(lambda _c=False, v=value: apply_display_scale(v))
    night_switch.toggled.connect(apply_night)
    on_show["Display"] = load_display

    # =================================================================== Sound
    sound_body = page("Sound", "Output volume.")
    sound_card, sound_layout = panel()
    vol_row = QHBoxLayout()
    vol_row.addWidget(label("Volume"), 1)
    vol_slider = QSlider(Qt.Orientation.Horizontal)
    vol_slider.setRange(0, 100)
    vol_slider.setFixedWidth(240)
    vol_value = label("", "muted", wrap=False)
    vol_row.addWidget(vol_slider)
    vol_row.addWidget(vol_value)
    sound_layout.addLayout(vol_row)
    mute_row, mute_switch = switch_row("Mute", "Silence the speakers")
    sound_layout.addLayout(mute_row)
    sound_note = label("", "caption")
    sound_layout.addWidget(sound_note)
    sound_body.addWidget(sound_card)
    sound_body.addStretch(1)

    def load_sound():
        try:
            level, muted = get_volume()
        except SettingError as error:
            vol_slider.setEnabled(False)
            mute_switch.setEnabled(False)
            sound_note.setText(f"No audio output yet: {error}")
            return
        sound_note.setText("")
        vol_slider.setEnabled(True)
        mute_switch.setEnabled(True)
        vol_slider.blockSignals(True)
        vol_slider.setValue(min(level, 100))
        vol_slider.blockSignals(False)
        vol_value.setText(f"{level}%")
        mute_switch.blockSignals(True)
        mute_switch.setChecked(muted)
        mute_switch.blockSignals(False)

    def commit_volume():
        try:
            report(set_volume(vol_slider.value()))
        except SettingError as error:
            report(str(error), error=True)

    vol_slider.valueChanged.connect(lambda v: vol_value.setText(f"{v}%"))
    vol_slider.sliderReleased.connect(commit_volume)

    def apply_mute(on):
        try:
            report(set_mute(on))
        except SettingError as error:
            report(str(error), error=True)

    mute_switch.toggled.connect(apply_mute)
    on_show["Sound"] = load_sound

    # =================================================================== Power
    power_body = page("Power", "Battery and performance.")
    power_card, power_layout = panel()
    battery_label = label("", "hero", wrap=False)
    battery_sub = label("", "muted")
    power_layout.addWidget(battery_label)
    power_layout.addWidget(battery_sub)
    power_body.addWidget(power_card)
    lite_card, lite_layout = panel()
    lite_row, lite_switch = switch_row(
        "Lite mode", "Fewer animations and background tasks, for computers with 2 GB of memory"
    )
    lite_layout.addLayout(lite_row)
    power_body.addWidget(lite_card)
    actions_card, actions_layout = panel()
    actions_layout.addWidget(section_title("Session"))
    actions = QHBoxLayout()
    for text, command in (
        ("Sleep", ["/usr/bin/systemctl", "suspend"]),
        ("Restart", ["/usr/bin/systemctl", "reboot"]),
        ("Shut down", ["/usr/bin/systemctl", "poweroff"]),
    ):
        button = QPushButton(text)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.clicked.connect(lambda _c=False, cmd=command: subprocess.Popen(cmd, start_new_session=True))
        actions.addWidget(button)
    actions.addStretch(1)
    actions_layout.addLayout(actions)
    power_body.addWidget(actions_card)
    power_body.addStretch(1)

    def load_power():
        reading = battery()
        if reading is None:
            battery_label.setText("Plugged in")
            battery_sub.setText("This computer has no battery.")
        else:
            percent, state = reading
            battery_label.setText(f"{percent}%")
            battery_sub.setText(state)
        lite_switch.blockSignals(True)
        lite_switch.setChecked(bool(store.get("lite_mode")))
        lite_switch.blockSignals(False)

    def apply_lite(on):
        try:
            store.set("lite_mode", on)
        except SettingError as error:
            report(str(error), error=True)
            return
        report("Lite mode on. Takes effect for apps you open next." if on else "Lite mode off.")

    lite_switch.toggled.connect(apply_lite)
    on_show["Power"] = load_power

    # =================================================================== System
    system_body = page("System", "About this computer.")
    system_card, system_layout = panel()
    system_rows: dict[str, QLabel] = {}
    for key, text in (
        ("os", "System"),
        ("kernel", "Kernel"),
        ("cpu", "Processor"),
        ("memory", "Memory"),
        ("disk", "Storage"),
        ("host", "Computer name"),
    ):
        row = QHBoxLayout()
        row.addWidget(label(text, "muted"), 0)
        value = label("")
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        system_rows[key] = value
        row.addWidget(value, 1)
        system_layout.addLayout(row)
    system_body.addWidget(system_card)
    system_body.addStretch(1)

    def load_system():
        facts = system_facts()
        for key, widget in system_rows.items():
            widget.setText(facts.get(key, "Unknown"))

    on_show["System"] = load_system

    show_section("Wi-Fi")
    window.show_section = show_section
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
