#!/usr/bin/env python3
"""Zaod OS first-boot setup: three short steps, offline, no account."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp
from backend import ACCENTS, APPEARANCES, Setup, SetupError

STEPS = ("Welcome", "Appearance", "Privacy", "Ready")


def build_window():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QRadioButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )

    setup = Setup()
    window = zaodapp.base_window("Welcome to Zaod OS", 720, 520)
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    progress = QLabel(" · ".join(STEPS))
    progress.setObjectName("muted")
    window.content.addWidget(progress)

    stack = QStackedWidget()
    window.content.addWidget(stack, 1)

    def page(title: str, body: str, extra: QWidget | None = None) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("title")
        layout.addWidget(heading)
        text = QLabel(body)
        text.setWordWrap(True)
        text.setObjectName("muted")
        layout.addWidget(text)
        if extra is not None:
            layout.addWidget(extra)
        layout.addStretch(1)
        return holder

    welcome = page(
        "Welcome to Zaod OS",
        "This setup takes about a minute. It works entirely offline: no account, no sign-in, "
        "and nothing leaves this computer unless you switch it on later.",
    )

    appearance_holder = QWidget()
    appearance_layout = QVBoxLayout(appearance_holder)
    appearance_layout.setContentsMargins(0, 0, 0, 0)
    theme_row = QHBoxLayout()
    theme_row.addWidget(QLabel("Theme"))
    theme = QComboBox()
    theme.addItems([name.title() for name in APPEARANCES])
    theme_row.addWidget(theme, 1)
    accent_row = QHBoxLayout()
    accent_row.addWidget(QLabel("Accent"))
    accent = QComboBox()
    accent.addItems([name.title() for name in ACCENTS])
    accent_row.addWidget(accent, 1)
    appearance_layout.addLayout(theme_row)
    appearance_layout.addLayout(accent_row)
    preview = QFrame()
    preview.setFixedHeight(70)
    preview.setStyleSheet("QFrame { background: #eef2ff; border-radius: 10px; }")
    appearance_layout.addWidget(preview)
    appearance = page(
        "Choose how it looks",
        "You can change both of these in Control Center whenever you like.",
        appearance_holder,
    )

    privacy_holder = QWidget()
    privacy_layout = QVBoxLayout(privacy_holder)
    privacy_layout.setContentsMargins(0, 0, 0, 0)
    privacy_layout.addWidget(QLabel("Updates"))
    update_modes = QVBoxLayout()
    radios = {}
    for key, label in (
        ("security-only", "Install security updates automatically"),
        ("automatic", "Install all updates automatically"),
        ("manual", "Let me choose when to update"),
    ):
        radio = QRadioButton(label)
        radios[key] = radio
        update_modes.addWidget(radio)
    radios[setup.state["updates"] if setup.state["updates"] in radios else "security-only"].setChecked(True)
    privacy_layout.addLayout(update_modes)
    telemetry = QCheckBox("Send anonymous crash and usage diagnostics (off by default)")
    telemetry.setChecked(bool(setup.state["telemetry"]))
    location = QCheckBox("Allow apps to use my approximate location (off by default)")
    location.setChecked(bool(setup.state["location"]))
    privacy_layout.addWidget(telemetry)
    privacy_layout.addWidget(location)
    privacy = page(
        "Privacy and updates",
        "Nothing is collected unless you tick a box here. Both switches stay visible in "
        "Control Center under Privacy, so you can change your mind at any time.",
        privacy_holder,
    )

    ready_text = QLabel("")
    ready_text.setWordWrap(True)
    ready = page("You are ready", "Setup will apply these choices now.", ready_text)

    for widget in (welcome, appearance, privacy, ready):
        stack.addWidget(widget)

    status = QLabel("")
    status.setObjectName("muted")

    buttons = QHBoxLayout()
    back = QPushButton("Back")
    forward = QPushButton("Continue")
    forward.setObjectName("primary")
    buttons.addWidget(back)
    buttons.addStretch(1)
    buttons.addWidget(status, 2)
    buttons.addWidget(forward)
    window.content.addLayout(buttons)

    def current() -> int:
        return stack.currentIndex()

    def sync() -> None:
        index = current()
        back.setEnabled(index > 0)
        forward.setText("Start using Zaod OS" if index == len(STEPS) - 1 else "Continue")
        if index == len(STEPS) - 1:
            try:
                setup.set("appearance", APPEARANCES[theme.currentIndex()])
                setup.set("accent", ACCENTS[accent.currentIndex()])
                chosen = next((key for key, radio in radios.items() if radio.isChecked()), None)
                if chosen:
                    setup.set("updates", chosen)
                setup.set("telemetry", telemetry.isChecked())
                setup.set("location", location.isChecked())
                ready_text.setText(setup.summary())
                status.setText("")
            except SetupError as error:
                status.setText(str(error))
        progress.setText(" · ".join(
            f"[{name}]" if position <= index else name for position, name in enumerate(STEPS)
        ))

    def go_forward() -> None:
        if current() == len(STEPS) - 1:
            try:
                setup.finish()
            except SetupError as error:
                status.setText(str(error))
                return
            status.setText("setup complete")
            window.close()
            return
        stack.setCurrentIndex(current() + 1)
        sync()

    def go_back() -> None:
        stack.setCurrentIndex(max(0, current() - 1))
        sync()

    forward.clicked.connect(go_forward)
    back.clicked.connect(go_back)
    sync()
    window.primary = forward
    return window


def main() -> int:
    if Setup().completed and "--force" not in sys.argv:
        print("setup is already complete (use --force to run it again)")
        return 0
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
