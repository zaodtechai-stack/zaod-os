#!/usr/bin/env python3
"""Zaod Store: browse the signed index, install, update and remove apps."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))

import zaodapp
from backend import StoreBackend, StoreError


def build_window(store: StoreBackend | None = None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    backend = store or StoreBackend()
    window = zaodapp.base_window("Store", 900, 600)

    search = QLineEdit()
    search.setPlaceholderText("Search apps")
    window.content.addWidget(search)

    split = QHBoxLayout()
    window.content.addLayout(split, 1)

    listing = QListWidget()
    listing.setMinimumWidth(320)
    split.addWidget(listing, 1)

    detail_panel = QWidget()
    detail_layout = QVBoxLayout(detail_panel)
    detail = QTextBrowser()
    detail.setOpenExternalLinks(False)
    detail_layout.addWidget(detail, 1)
    buttons = QHBoxLayout()
    primary = QPushButton("Install")
    primary.setObjectName("primary")
    secondary = QPushButton("Remove")
    refresh = QPushButton("Sync")
    buttons.addWidget(primary)
    buttons.addWidget(secondary)
    buttons.addWidget(refresh)
    buttons.addStretch(1)
    detail_layout.addLayout(buttons)
    split.addWidget(detail_panel, 1)

    status = QLabel("")
    status.setObjectName("muted")
    status.setWordWrap(True)
    window.content.addWidget(status)

    state = {"items": [], "selected": None}

    def report(message: str, error: bool = False) -> None:
        status.setText(message)
        status.setObjectName("danger" if error else "muted")
        status.style().unpolish(status)
        status.style().polish(status)

    def describe(item: dict) -> str:
        permissions = ", ".join(backend.permission_summary(item))
        state_line = {
            "new": "Not installed",
            "update": f"Update available ({item['installed_version']} → {item['version']})",
            "installed": f"Installed {item['installed_version']}",
        }[item["state"]]
        return (
            f"<h2>{item['name']}</h2>"
            f"<p><b>Version</b> {item['version']} &nbsp; <b>Licence</b> {item['license'] or 'unknown'}<br>"
            f"<b>Repository</b> {item['repository']} &nbsp; <b>Size</b> {item['size'] / 1024:.1f} KiB</p>"
            f"<p>{item['description'] or item['summary']}</p>"
            f"<p><b>Permissions</b> {permissions}</p>"
            f"<p><i>{state_line}</i></p>"
        )

    def select(item) -> None:
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        state["selected"] = data
        if not data:
            detail.setHtml("<p>Select an app to see details.</p>")
            return
        detail.setHtml(describe(data))
        primary.setEnabled(data["state"] in ("new", "update"))
        primary.setText("Update" if data["state"] == "update" else "Install")
        secondary.setEnabled(data["state"] in ("update", "installed"))

    def refresh_list(indexes=None) -> None:
        query = search.text()
        try:
            items = backend.catalogue(query, indexes)
        except StoreError as error:
            report(str(error), error=True)
            return
        state["items"] = items
        listing.clear()
        for item in items:
            badge = {"new": "", "update": "  ↑ update", "installed": "  ✓"}[item["state"]]
            entry = QListWidgetItem(f"{item['name']} {item['version']}{badge}")
            entry.setData(Qt.ItemDataRole.UserRole, item)
            listing.addItem(entry)
        if not items:
            report("No apps match that search. Sync a repository or clear the query.")
        else:
            pending = sum(1 for item in items if item["state"] == "update")
            report(f"{len(items)} apps · {pending} updates available")
        select(listing.item(0))

    def act(action: str) -> None:
        item = state["selected"]
        if not item:
            return
        try:
            if action == "install":
                backend.install(item["id"])
            elif action == "remove":
                backend.remove(item["id"])
            elif action == "update":
                backend.update(item["id"])
        except StoreError as error:
            report(str(error), error=True)
            return
        report(f"{item['name']}: {action} finished")
        refresh_list()

    def sync() -> None:
        report("syncing signed store indexes…")
        try:
            indexes = backend.sync()
        except StoreError as error:
            cached = backend.cached()
            if cached:
                report(f"offline: showing the cached index ({error})", error=True)
                refresh_list(cached)
            else:
                report(str(error), error=True)
            return
        refresh_list(indexes)
        report("store index verified and updated")

    search.textChanged.connect(lambda _text: refresh_list())
    listing.currentItemChanged.connect(lambda current, _previous: select(current))
    primary.clicked.connect(
        lambda: act("update" if state["selected"] and state["selected"]["state"] == "update" else "install")
    )
    secondary.clicked.connect(lambda: act("remove"))
    refresh.clicked.connect(sync)

    refresh_list()
    window.refresh_list = refresh_list
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
