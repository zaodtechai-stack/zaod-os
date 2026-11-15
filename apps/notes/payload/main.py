#!/usr/bin/env python3
"""Zaod Notes: a plain-text notepad stored in the app data directory."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp

APP_ID = "org.zaod.notes"


def notes_file():
    return zaodapp.data_dir(APP_ID) / "notes.txt"


def build_window():
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit

    window = zaodapp.base_window("Notes", 620, 460)
    editor = QTextEdit()
    editor.setPlaceholderText("Write something…")
    window.content.addWidget(editor)
    status = QLabel("")
    status.setObjectName("muted")
    window.content.addWidget(status)

    def load_text() -> str:
        path = notes_file()
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def save_text() -> None:
        notes_file().write_text(editor.toPlainText(), encoding="utf-8")
        status.setText(f"saved · {len(editor.toPlainText().split())} words")

    editor.setPlainText(load_text())

    buttons = QHBoxLayout()
    save = QPushButton("Save")
    save.setObjectName("primary")
    save.clicked.connect(save_text)
    reload_button = QPushButton("Reload")
    reload_button.clicked.connect(lambda: editor.setPlainText(load_text()))
    buttons.addWidget(save)
    buttons.addWidget(reload_button)
    buttons.addStretch(1)
    window.content.addLayout(buttons)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
