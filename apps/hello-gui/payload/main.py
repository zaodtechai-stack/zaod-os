#!/usr/bin/env python3
"""Zaod Hello: the smallest reference app for the .zaod format (MIT licensed)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp


def build_window():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    window = zaodapp.base_window("Hello", 460, 240)
    message = QLabel("Hello from Zaod OS")
    message.setStyleSheet("font-size: 26px; font-weight: 600;")
    message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.content.addWidget(message)
    detail = QLabel("This window is running from a signed .zaod package.")
    detail.setObjectName("muted")
    detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.content.addWidget(detail)
    window.content.addStretch(1)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
