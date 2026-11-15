#!/usr/bin/env python3
"""Zaod Text Editor: a small plain-text editor."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp


def word_count(text: str) -> int:
    return len(text.split())


def build_window():
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QPlainTextEdit,
        QPushButton,
    )

    window = zaodapp.base_window("Text Editor", 760, 560)
    editor = QPlainTextEdit()
    editor.setFont(QFont("JetBrains Mono", 11))
    window.content.addWidget(editor)
    status = QLabel("0 words")
    status.setObjectName("muted")
    window.content.addWidget(status)

    state = {"path": None}

    def refresh_status() -> None:
        name = os.path.basename(state["path"]) if state["path"] else "Untitled"
        status.setText(f"{name} · {word_count(editor.toPlainText())} words")

    editor.textChanged.connect(refresh_status)

    def open_file() -> None:
        path, _filter = QFileDialog.getOpenFileName(window, "Open", os.environ.get("HOME", ""), "Text (*.txt *.md *.log *.*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                editor.setPlainText(handle.read())
        except OSError:
            status.setText("cannot read that file")
            return
        state["path"] = path
        refresh_status()

    def save_file() -> None:
        if not state["path"]:
            state["path"], _filter = QFileDialog.getSaveFileName(window, "Save as", "untitled.txt", "Text (*.txt)")
        if not state["path"]:
            return
        try:
            with open(state["path"], "w", encoding="utf-8") as handle:
                handle.write(editor.toPlainText())
        except OSError:
            status.setText("cannot write that file")
            return
        refresh_status()

    row = QHBoxLayout()
    open_button = QPushButton("Open…")
    open_button.clicked.connect(open_file)
    save_button = QPushButton("Save")
    save_button.setObjectName("primary")
    save_button.clicked.connect(save_file)
    row.addWidget(open_button)
    row.addWidget(save_button)
    row.addStretch(1)
    window.content.addLayout(row)
    refresh_status()
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
