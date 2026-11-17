#!/usr/bin/env python3
"""Zaod Control Center: one window for the settings that matter."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))

import zaodapp
from backend import ControlCenter, SettingError


def build_window(center: ControlCenter | None = None):
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QPushButton,
        QSlider,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    settings = center or ControlCenter()
    window = zaodapp.base_window("Control Center", 860, 560)
    split = QHBoxLayout()
    window.content.addLayout(split)

    navigation = QListWidget()
    navigation.setFixedWidth(190)
    stack = QStackedWidget()
    split.addWidget(navigation)
    split.addWidget(stack, 1)

    status = QLabel("")
    status.setObjectName("muted")
    status.setWordWrap(True)
    window.content.addWidget(status)

    def report(message: str, error: bool = False) -> None:
        status.setText(message)
        status.setObjectName("danger" if error else "muted")
        status.style().unpolish(status)
        status.style().polish(status)

    builders = []

    for page in settings.pages:
        navigation.addItem(page.title)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        summary = QLabel(page.summary)
        summary.setObjectName("muted")
        layout.addWidget(summary)

        for control in page.controls:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 6, 0, 6)
            heading = QLabel(control.label)
            heading.setStyleSheet("font-weight: 600;")
            row_layout.addWidget(heading)
            note = QLabel(control.description)
            note.setObjectName("muted")
            note.setWordWrap(True)
            row_layout.addWidget(note)

            def current(page_key=page.key, control_key=control.key, widget=None) -> None:
                pass

            if control.kind in ("toggle", "choice"):
                widget = QComboBox() if control.kind == "choice" else None
                if control.kind == "choice":
                    for value, label in control.choices:
                        widget.addItem(label, value)
                else:
                    toggle = QCheckBox("Enabled")
                    widget = toggle
                row_layout.addWidget(widget)

                def load(page_key=page.key, control_key=control.key, widget=widget, kind=control.kind) -> None:
                    try:
                        value = settings.get(page_key, control_key)
                    except SettingError as error:
                        report(str(error), error=True)
                        return
                    if kind == "choice":
                        index = widget.findData(value)
                        if index >= 0:
                            widget.setCurrentIndex(index)
                    else:
                        widget.setChecked(str(value).lower() in ("true", "on", "1", "yes"))

                def store(value, page_key=page.key, control_key=control.key, kind=control.kind, label=control.label) -> None:
                    if kind == "toggle":
                        on_value, off_value = "true", "false"
                        for raw, translated in settings.control(page_key, control_key).value_map.items():
                            if translated == "on":
                                on_value = raw
                            if translated == "off":
                                off_value = raw
                        payload = on_value if value else off_value
                    else:
                        payload = value
                    try:
                        settings.set(page_key, control_key, payload)
                    except SettingError as error:
                        report(str(error), error=True)
                        return
                    report(f"{label} updated")

                if control.kind == "choice":
                    widget.currentIndexChanged.connect(
                        lambda _index, widget=widget: store(widget.currentData())
                    )
                else:
                    widget.toggled.connect(store)
                load()
                builders.append(load)

            elif control.kind == "slider":
                row_layout.addLayout(QHBoxLayout())
                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(0, 100)
                value_label = QLabel("%")
                slider.valueChanged.connect(lambda value, label=value_label: label.setText(f"{value}%"))
                holder = QHBoxLayout()
                holder.addWidget(slider, 1)
                holder.addWidget(value_label)
                row_layout.addLayout(holder)

                def load_slider(page_key=page.key, control_key=control.key, slider=slider) -> None:
                    try:
                        slider.setValue(int(settings.get(page_key, control_key)))
                    except (SettingError, ValueError) as error:
                        report(str(error), error=True)

                def apply_slider(value, page_key=page.key, control_key=control.key, label=control.label) -> None:
                    try:
                        settings.set(page_key, control_key, str(value))
                    except SettingError as error:
                        report(str(error), error=True)
                        return
                    report(f"{label} set to {value}%")

                slider.sliderReleased.connect(lambda slider=slider: apply_slider(slider.value()))
                load_slider()
                builders.append(load_slider)

            elif control.kind == "action":
                button = QPushButton(control.label)
                button.setObjectName("primary")

                def run(page_key=page.key, control_key=control.key, label=control.label) -> None:
                    report(f"running {label.lower()}…")
                    try:
                        settings.set(page_key, control_key, "")
                    except SettingError as error:
                        report(str(error), error=True)
                        return
                    report(f"{label} finished")

                button.clicked.connect(run)
                row_layout.addWidget(button)

            else:  # info
                value_label = QLabel("…")
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                refresh = QPushButton("Refresh")
                value_holder = QHBoxLayout()
                value_holder.addWidget(value_label, 1)
                value_holder.addWidget(refresh)
                row_layout.addLayout(value_holder)

                def load_info(page_key=page.key, control_key=control.key, label=value_label) -> None:
                    try:
                        label.setText(settings.get(page_key, control_key) or "not set")
                    except SettingError as error:
                        label.setText(str(error))

                refresh.clicked.connect(load_info)
                load_info()
                builders.append(load_info)

            layout.addWidget(row)

        layout.addStretch(1)
        stack.addWidget(panel)


    # ---- wallpapers ---------------------------------------------------------
    # A gallery, not a file dialog: the nine built-in wallpapers are the choice,
    # each shown as its own thumbnail, and the pick is remembered for next time.
    navigation.addItem("Wallpapers")
    wall_panel = QWidget()
    wall_layout = QVBoxLayout(wall_panel)
    wall_layout.setSpacing(12)
    wall_note = QLabel("Pick a wallpaper. It stays after a restart.")
    wall_note.setObjectName("muted")
    wall_layout.addWidget(wall_note)

    thumbs_host = QWidget()
    thumbs_grid = QGridLayout(thumbs_host)
    thumbs_grid.setSpacing(12)
    thumbs_grid.setContentsMargins(0, 0, 0, 0)

    choice_file = Path(os.environ.get("HOME", str(Path.home()))) / ".config" / "zaod" / "wallpaper"
    try:
        current_wallpaper = choice_file.read_text().strip()
    except OSError:
        current_wallpaper = ""

    buttons: list[QPushButton] = []

    def apply_wallpaper(slug: str, button: QPushButton) -> None:
        image = f"/usr/share/wallpapers/zaod/collection/{slug}"
        if not Path(image).is_file():
            report(f"missing wallpaper {slug}", error=True)
            return
        try:
            choice_file.parent.mkdir(parents=True, exist_ok=True)
            choice_file.write_text(image + "\n")
        except OSError as error:
            report(f"could not save the choice: {error}", error=True)
            return
        for other in buttons:
            other.setChecked(other is button)
        subprocess.run(["pkill", "-x", "swaybg"], check=False, capture_output=True)
        if os.environ.get("WAYLAND_DISPLAY"):
            subprocess.Popen(
                ["swaybg", "-i", image, "-m", "fill"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        report(f"wallpaper: {slug.removesuffix('.jpg').replace('zaod-', '').replace('-', ' ').title()}")

    thumbs = sorted(Path("/usr/share/wallpapers/zaod/collection/thumbs").glob("*.jpg"))
    for index, thumb in enumerate(thumbs):
        slug = thumb.name
        button = QPushButton()
        button.setCheckable(True)
        button.setChecked(current_wallpaper.endswith(slug))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(QSize(236, 140))
        button.setToolTip(slug.removesuffix(".jpg").replace("zaod-", "").replace("-", " ").title())
        pixmap = QPixmap(str(thumb))
        if not pixmap.isNull():
            button.setIcon(
                QIcon(
                    pixmap.scaled(
                        QSize(228, 124),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            )
            button.setIconSize(QSize(228, 124))
        button.clicked.connect(lambda _checked=False, slug=slug, button=button: apply_wallpaper(slug, button))
        buttons.append(button)
        thumbs_grid.addWidget(button, index // 3, index % 3)

    wall_layout.addWidget(thumbs_host)
    wall_layout.addStretch(1)
    stack.addWidget(wall_panel)

    navigation.currentRowChanged.connect(stack.setCurrentIndex)
    navigation.setCurrentRow(0)
    window.reload = lambda: [builder() for builder in builders]
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
