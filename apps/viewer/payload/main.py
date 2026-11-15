#!/usr/bin/env python3
"""Zaod Image Viewer: open, fit and zoom local images."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp  # noqa: E402


def build_window():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton

    window = zaodapp.base_window("Image Viewer", 720, 520)
    canvas = QLabel("Open a picture to start")
    canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
    canvas.setMinimumHeight(320)
    window.content.addWidget(canvas)

    state = {"path": None, "zoom": 1.0}

    def render() -> None:
        if not state["path"]:
            return
        pixmap = QPixmap(state["path"])
        if pixmap.isNull():
            canvas.setText("cannot read that image")
            return
        scaled = pixmap.scaled(
            int(canvas.width() * state["zoom"]),
            int(canvas.height() * state["zoom"]),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas.setPixmap(scaled)

    def open_file() -> None:
        path, _filter = QFileDialog.getOpenFileName(
            window, "Open image", os.environ.get("HOME", ""), "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if path:
            state["path"] = path
            state["zoom"] = 1.0
            window.setWindowTitle(f"Image Viewer — {os.path.basename(path)}")
            render()

    row = QHBoxLayout()
    open_button = QPushButton("Open…")
    open_button.setObjectName("primary")
    open_button.clicked.connect(open_file)

    def zoom(factor: float) -> None:
        state["zoom"] = max(0.2, min(4.0, state["zoom"] * factor))
        render()

    zoom_in = QPushButton("Zoom in")
    zoom_in.clicked.connect(lambda: zoom(1.25))
    zoom_out = QPushButton("Zoom out")
    zoom_out.clicked.connect(lambda: zoom(0.8))
    for widget in (open_button, zoom_in, zoom_out):
        row.addWidget(widget)
    row.addStretch(1)
    window.content.addLayout(row)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
