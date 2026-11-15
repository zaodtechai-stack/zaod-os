#!/usr/bin/env python3
"""Zaod Tasks: a checklist saved as JSON in the app data directory."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp  # noqa: E402

APP_ID = "org.zaod.tasks"


def tasks_file():
    return zaodapp.data_dir(APP_ID) / "tasks.json"


def load_tasks():
    path = tasks_file()
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []


def save_tasks(tasks) -> None:
    tasks_file().write_text(json.dumps(tasks, indent=2), encoding="utf-8")


def build_window():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton

    window = zaodapp.base_window("Tasks", 520, 460)
    entry = QLineEdit()
    entry.setPlaceholderText("What needs doing?")
    window.content.addWidget(entry)
    listing = QListWidget()
    window.content.addWidget(listing)
    status = QLabel("")
    status.setObjectName("muted")
    window.content.addWidget(status)

    tasks = load_tasks()

    def render() -> None:
        listing.clear()
        for index, task in enumerate(tasks):
            item = QListWidgetItem(task["title"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if task.get("done") else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, index)
            listing.addItem(item)
        done = sum(1 for task in tasks if task.get("done"))
        status.setText(f"{done} of {len(tasks)} done")

    def add_task() -> None:
        title = entry.text().strip()
        if not title:
            return
        tasks.append({"title": title, "done": False})
        entry.clear()
        save_tasks(tasks)
        render()

    def toggle(item) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None or index >= len(tasks):
            return
        tasks[index]["done"] = item.checkState() == Qt.CheckState.Checked
        save_tasks(tasks)
        render()

    def remove_selected() -> None:
        row = listing.currentRow()
        if 0 <= row < len(tasks):
            tasks.pop(row)
            save_tasks(tasks)
            render()

    entry.returnPressed.connect(add_task)
    listing.itemChanged.connect(toggle)
    render()

    row = QHBoxLayout()
    add = QPushButton("Add")
    add.setObjectName("primary")
    add.clicked.connect(add_task)
    remove = QPushButton("Remove selected")
    remove.clicked.connect(remove_selected)
    row.addWidget(add)
    row.addWidget(remove)
    row.addStretch(1)
    window.content.addLayout(row)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
