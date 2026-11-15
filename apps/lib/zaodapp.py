"""Shared helpers for Zaod first-party applications (MIT licensed, original).

Every first-party app bundles this file so it works offline as a self-contained
``.zaod`` package. The helpers keep the Fluent design tokens in one place:
4 px spacing grid, 8 px radii, the Zaod blue accent and the light/dark palettes.
"""

from __future__ import annotations

import os
import sys

ACCENT = "#0b57d0"
ACCENT_DARK = "#a8c7fa"

LIGHT = {
    "window": "#f7f8fa",
    "surface": "#ffffff",
    "text": "#14171f",
    "muted": "#5b6270",
    "border": "#dde1e8",
    "accent": ACCENT,
}

DARK = {
    "window": "#14171f",
    "surface": "#1e222c",
    "text": "#f2f5fa",
    "muted": "#a6adbb",
    "border": "#333947",
    "accent": ACCENT_DARK,
}


def is_dark() -> bool:
    """Follow the desktop theme; ``ZAOD_THEME=dark|light`` overrides it."""
    override = os.environ.get("ZAOD_THEME", "").strip().lower()
    if override in ("dark", "light"):
        return override == "dark"
    return os.environ.get("ZAOD_COLOR_SCHEME", "").lower().endswith("dark")


def palette() -> dict[str, str]:
    return DARK if is_dark() else LIGHT


def stylesheet() -> str:
    colours = palette()
    return f"""
    QWidget {{ background: {colours['window']}; color: {colours['text']};
               font-family: Inter, "Noto Sans", sans-serif; font-size: 14px; }}
    QLabel#title {{ font-size: 22px; font-weight: 600; }}
    QLabel#muted {{ color: {colours['muted']}; }}
    QPushButton {{ background: {colours['surface']}; color: {colours['text']};
                   border: 1px solid {colours['border']}; border-radius: 8px; padding: 8px 14px; }}
    QPushButton:hover {{ border-color: {colours['accent']}; }}
    QPushButton#primary {{ background: {colours['accent']}; color: #ffffff; border: none; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox {{
        background: {colours['surface']}; border: 1px solid {colours['border']};
        border-radius: 8px; padding: 6px; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus {{
        border-color: {colours['accent']}; }}
    QCheckBox {{ spacing: 8px; }}
    """


def make_app(argv: list[str] | None = None):
    """Create the QApplication with the Zaod palette applied."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("Zaod")
    app.setStyleSheet(stylesheet())
    return app


def base_window(title: str, width: int = 520, height: int = 380, *, margins: int = 20):
    """A window with a 4 px grid layout and the app title already in place."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    window = QWidget()
    window.setWindowTitle(title)
    window.resize(width, height)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(12)
    heading = QLabel(title)
    heading.setObjectName("title")
    heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(heading)
    window.heading = heading
    window.content = layout
    return window


def run(window_builder, argv: list[str] | None = None) -> int:
    """Run an app: build the window, show it, enter the Qt event loop."""
    app = make_app(argv)
    window = window_builder()
    window.show()
    return app.exec()


def data_dir(app_id: str):
    """Writable per-app data directory (the sandbox maps it to ``/data``)."""
    from pathlib import Path

    base = os.environ.get("HOME", str(Path.home()))
    path = Path(base) / ".zaod" / "data" / app_id
    if (Path(base) / ".local").exists() or Path(base).name == "data":
        path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path
