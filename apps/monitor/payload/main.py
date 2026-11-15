#!/usr/bin/env python3
"""Zaod System Monitor: reads /proc to show memory, load and uptime."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp


def read_memory(sample: str | None = None) -> tuple[int, int, int]:
    """Return (used, total, percent) in bytes from /proc/meminfo layout."""
    if sample is None:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            sample = handle.read()
    values = {}
    for line in sample.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        number = rest.strip().split()
        if number:
            values[key] = int(number[0]) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    used = max(total - available, 0)
    percent = int(used * 100 / total) if total else 0
    return used, total, percent


def read_load(sample: str | None = None) -> tuple[float, float, float]:
    if sample is None:
        with open("/proc/loadavg", encoding="utf-8") as handle:
            sample = handle.read()
    parts = sample.split()
    return tuple(float(item) for item in parts[:3])  # type: ignore[return-value]


def read_uptime(sample: str | None = None) -> str:
    if sample is None:
        with open("/proc/uptime", encoding="utf-8") as handle:
            sample = handle.read()
    seconds = int(float(sample.split()[0]))
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"


def build_window():
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QProgressBar

    window = zaodapp.base_window("System Monitor", 480, 360)
    memory_bar = QProgressBar()
    memory_bar.setRange(0, 100)
    window.content.addWidget(memory_bar)
    memory_label = QLabel("reading…")
    load_label = QLabel("")
    uptime_label = QLabel("")
    for label in (memory_label, load_label, uptime_label):
        window.content.addWidget(label)
    window.content.addStretch(1)

    def refresh() -> None:
        try:
            used, total, percent = read_memory()
            load = read_load()
            uptime = read_uptime()
        except OSError:
            memory_label.setText("system statistics are not available")
            return
        memory_bar.setValue(percent)
        memory_label.setText(f"{used / (1024 ** 3):.2f} GB of {total / (1024 ** 3):.2f} GB used")
        load_label.setText(f"load 1m {load[0]:.2f} · 5m {load[1]:.2f} · 15m {load[2]:.2f}")
        uptime_label.setText(f"uptime {uptime}")

    timer = QTimer(window)
    timer.timeout.connect(refresh)
    timer.start(1000)
    refresh()
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
