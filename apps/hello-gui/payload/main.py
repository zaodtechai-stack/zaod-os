#!/usr/bin/env python3
"""Zaod Hello: the smallest reference app for the .zaod format.

MIT licensed, original to the Zaod OS project.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


def main() -> int:
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Hello")
    window.resize(420, 220)
    layout = QVBoxLayout(window)
    title = QLabel("Hello from Zaod OS")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet("font-size: 22px; font-weight: 600;")
    subtitle = QLabel("This window is running from a signed .zaod package.")
    subtitle.setAlignment(Qt.AlignCenter)
    layout.addWidget(title)
    layout.addWidget(subtitle)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
