#!/usr/bin/env python3
"""Zaod Clock: current time plus a stopwatch."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp


def format_elapsed(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"


def build_window():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

    window = zaodapp.base_window("Clock", 420, 320)
    time_label = QLabel("--:--:--")
    time_label.setObjectName("metric")
    window.content.addWidget(time_label)

    stopwatch_label = QLabel("00:00")
    stopwatch_label.setObjectName("hero")
    window.content.addWidget(stopwatch_label)

    tick = QTimer(window)
    started = {"at": None, "frozen": 0.0}

    def refresh() -> None:
        time_label.setText(time.strftime("%H:%M:%S"))
        if started["at"] is None:
            stopwatch_label.setText(format_elapsed(started["frozen"]))
        else:
            stopwatch_label.setText(format_elapsed(started["frozen"] + time.monotonic() - started["at"]))

    tick.timeout.connect(refresh)
    tick.start(200)
    refresh()

    def toggle() -> None:
        if started["at"] is None:
            started["at"] = time.monotonic()
        else:
            started["frozen"] += time.monotonic() - started["at"]
            started["at"] = None
        refresh()

    def reset() -> None:
        started["at"] = None
        started["frozen"] = 0.0
        refresh()

    row = QHBoxLayout()
    start_button = QPushButton("Start / Stop")
    start_button.clicked.connect(toggle)
    reset_button = QPushButton("Reset")
    reset_button.clicked.connect(reset)
    row.addWidget(start_button)
    row.addWidget(reset_button)
    row.addStretch(1)
    window.content.addLayout(row)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
