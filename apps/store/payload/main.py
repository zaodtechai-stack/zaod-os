#!/usr/bin/env python3
"""Zaod Store: one place for the apps on this system.

Two catalogues meet here:

* what the machine already has - the first-party apps and the built-in web apps
  (YouTube, WhatsApp, Instagram, Facebook, TikTok, X), read from
  /usr/share/applications so the store agrees with the launcher;
* what a signed repository offers - browsed through ``zaodlib`` when an index is
  configured.

Layout: a searchable card grid on the left, the selected app's details and its
one action on the right. The grid is the point - a list of names was unreadable
and looked nothing like the rest of the desktop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))

import zaodapp
from backend import StoreBackend, StoreError

APPLICATIONS = "/usr/share/applications"
WEB_MANIFEST = Path("/usr/share/zaod/webapps.json")


def local_apps() -> list[dict]:
    """Every launcher entry this image ships, as a store card."""
    apps: list[dict] = []
    for entry in sorted(Path(APPLICATIONS).glob("*.desktop")):
        try:
            text = entry.read_text(errors="replace")
        except OSError:
            continue
        fields: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                fields.setdefault(key.strip(), value.strip())
        app_id = fields.get("X-Zaod-AppId")
        if not app_id:
            continue
        web = fields.get("X-Zaod-WebApp", "")
        apps.append(
            {
                "id": app_id,
                "name": fields.get("Name", app_id),
                "summary": fields.get("Comment", ""),
                "icon": fields.get("Icon", app_id),
                "kind": "web" if web else "app",
                "url": web,
                "categories": fields.get("Categories", ""),
                "state": "installed",
                "version": "",
                "license": "",
                "repository": "",
                "size": 0,
                "description": fields.get("Comment", ""),
            }
        )
    return apps


class UnavailableStore(StoreBackend):
    """Stands in for the backend when the Zaod system libraries are missing."""

    def __init__(self, reason: str):
        self.reason = reason

    def repositories(self):
        return []

    def cached(self):
        return {}

    def sync(self):
        return {}

    def catalogue(self, query, indexes=None):
        return []

    def permission_summary(self, item):
        return []

    def install(self, app_id: str) -> str:
        raise StoreError(self.reason)

    def remove(self, app_id: str) -> str:
        raise StoreError(self.reason)

    def update(self, app_id: str) -> str:
        raise StoreError(self.reason)

    def update_all(self) -> str:
        raise StoreError(self.reason)


def build_window(store: StoreBackend | None = None):
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )

    backend = store
    notice = ""
    if backend is None:
        try:
            backend = StoreBackend()
        except StoreError as error:
            backend = UnavailableStore(str(error))
            notice = str(error)

    window = zaodapp.base_window("Store", 1080, 700)
    c = zaodapp.palette()

    # ---- header -------------------------------------------------------------
    header = QHBoxLayout()
    subtitle = QLabel("Apps and web apps for Zaod OS")
    subtitle.setObjectName("subtitle")
    header.addWidget(subtitle, 1)

    search = QLineEdit()
    search.setPlaceholderText("Search apps")
    search.setMinimumWidth(260)
    search.setClearButtonEnabled(True)
    header.addWidget(search)

    sync_button = QPushButton("Sync")
    header.addWidget(sync_button)
    window.content.addLayout(header)

    chips_row = QHBoxLayout()
    chips_row.setSpacing(8)
    chips: dict[str, QPushButton] = {}
    for key in ("All", "Apps", "Web", "Video", "Social", "Chat"):
        chip = QPushButton(key)
        chip.setCheckable(True)
        chip.setChecked(key == "All")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chips[key] = chip
        chips_row.addWidget(chip)
    chips_row.addStretch(1)
    window.content.addLayout(chips_row)

    # ---- body ---------------------------------------------------------------
    body = QHBoxLayout()
    body.setSpacing(16)
    window.content.addLayout(body, 1)

    grid_host = QWidget()
    grid = QGridLayout(grid_host)
    grid.setSpacing(12)
    grid.setContentsMargins(0, 0, 0, 0)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(grid_host)
    body.addWidget(scroll, 1)

    detail_panel = QFrame()
    detail_panel.setObjectName("preview")
    detail_layout = QVBoxLayout(detail_panel)
    detail_layout.setContentsMargins(18, 18, 18, 18)
    detail_layout.setSpacing(10)

    detail_icon = QLabel()
    detail_icon.setFixedSize(QSize(64, 64))
    detail_icon.setScaledContents(True)
    detail_name = QLabel("")
    detail_name.setObjectName("hero")
    detail_name.setWordWrap(True)
    detail_meta = QLabel("")
    detail_meta.setObjectName("muted")
    detail_meta.setWordWrap(True)
    detail_text = QTextBrowser()
    detail_text.setOpenExternalLinks(False)
    detail_text.setMinimumHeight(160)

    detail_layout.addWidget(detail_icon)
    detail_layout.addWidget(detail_name)
    detail_layout.addWidget(detail_meta)
    detail_layout.addWidget(detail_text, 1)

    primary = QPushButton("Open")
    primary.setObjectName("primary")
    secondary = QPushButton("Remove")
    detail_layout.addWidget(primary)
    detail_layout.addWidget(secondary)
    detail_panel.setFixedWidth(320)
    body.addWidget(detail_panel)

    status = QLabel(notice or " ")
    status.setObjectName("danger" if notice else "muted")
    status.setWordWrap(True)
    window.content.addWidget(status)

    state: dict[str, object] = {"items": [], "selected": None, "filter": "All"}

    def report(message: str, error: bool = False) -> None:
        status.setText(message)
        status.setObjectName("danger" if error else "muted")
        status.style().unpolish(status)
        status.style().polish(status)

    def icon_for(name: str) -> QIcon:
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            icon = QIcon.fromTheme("application-x-executable")
        return icon

    def catalogue() -> list[dict]:
        items = local_apps()
        try:
            remote = backend.catalogue(search.text())
        except StoreError:
            remote = []
        known = {item["id"] for item in items}
        for item in remote:
            if item["id"] not in known:
                item["kind"] = "app"
                items.append(item)
        return items

    def matches(item: dict, query: str) -> bool:
        if not query:
            return True
        haystack = " ".join(
            str(item.get(key, "")) for key in ("name", "summary", "description", "categories")
        ).lower()
        return query.lower() in haystack

    def in_chip(item: dict, chip: str) -> bool:
        if chip == "All":
            return True
        if chip == "Apps":
            return item.get("kind") == "app"
        if chip == "Web":
            return item.get("kind") == "web"
        return chip.lower() in str(item.get("categories", "")).lower()

    def clear_grid() -> None:
        while grid.count():
            child = grid.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def select(item: dict | None) -> None:
        state["selected"] = item
        if not item:
            detail_icon.clear()
            detail_name.setText("")
            detail_meta.setText("")
            detail_text.setHtml("")
            primary.setEnabled(False)
            secondary.setEnabled(False)
            return
        detail_icon.setPixmap(icon_for(item.get("icon", "")).pixmap(QSize(64, 64)))
        detail_name.setText(item["name"])
        bits = []
        if item.get("version"):
            bits.append(f"Version {item['version']}")
        bits.append("Web app" if item.get("kind") == "web" else "Installed app")
        if item.get("repository"):
            bits.append(f"Repository {item['repository']}")
        if item.get("size"):
            bits.append(f"{item['size'] / 1024:.0f} KiB")
        detail_meta.setText(" · ".join(bits))
        body_text = item.get("description") or item.get("summary") or ""
        permissions = ""
        try:
            summary = backend.permission_summary(item) or []
            if summary:
                permissions = "<p><b>Permissions</b> " + ", ".join(summary) + "</p>"
        except StoreError:
            pass
        detail_text.setHtml(f"<p>{body_text}</p>{permissions}")

        if item.get("kind") == "web":
            primary.setText("Open")
            primary.setEnabled(True)
            secondary.setEnabled(False)
        elif item["state"] == "installed":
            primary.setText("Open")
            primary.setEnabled(True)
            secondary.setEnabled(item["id"].startswith("org.zaod.") is False)
        else:
            primary.setText("Update" if item["state"] == "update" else "Install")
            primary.setEnabled(True)
            secondary.setEnabled(item["state"] == "update")

    def card(item: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("preview")
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setMinimumHeight(132)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        badge = QLabel()
        badge.setFixedSize(QSize(48, 48))
        badge.setScaledContents(True)
        badge.setPixmap(icon_for(item.get("icon", "")).pixmap(QSize(48, 48)))
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setSpacing(2)
        title = QLabel(item["name"])
        title.setStyleSheet(f"font-weight: 600; color: {c['textPrimary']};")
        summary = QLabel(item.get("summary") or "")
        summary.setObjectName("muted")
        summary.setWordWrap(True)
        summary.setMaximumHeight(38)
        text_column.addWidget(title)
        text_column.addWidget(summary)
        if item.get("kind") == "web":
            tag = QLabel("Web app")
            tag.setObjectName("caption")
            text_column.addWidget(tag)
        layout.addLayout(text_column, 1)

        frame.mousePressEvent = lambda _event, data=item: select(data)
        return frame

    def refresh() -> None:
        items = catalogue()
        state["items"] = items
        chip = str(state["filter"])
        query = search.text()
        visible = [item for item in items if in_chip(item, chip) and matches(item, query)]
        clear_grid()
        for index, item in enumerate(visible):
            grid.addWidget(card(item), index // 3, index % 3)
        grid.setRowStretch(len(visible) // 3 + 1, 1)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        if visible:
            report(f"{len(visible)} apps · {sum(1 for i in items if i['state'] == 'update')} updates available")
            select(visible[0])
        else:
            report("Nothing matches that search.")
            select(None)

    def open_selected() -> None:
        item = state["selected"]
        if not item:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if item.get("kind") == "web":
            QDesktopServices.openUrl(QUrl(item["url"]))
            report(f"{item['name']} is opening in its own window")
            return
        if item["state"] == "installed":
            launcher = Path(APPLICATIONS) / f"{item['id']}.desktop"
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(launcher)))
            report(f"Starting {item['name']}")
            return
        act("update" if item["state"] == "update" else "install")

    def act(action: str) -> None:
        item = state["selected"]
        if not item:
            return
        report(f"{item['name']}: {action}…")
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
        refresh()

    def sync() -> None:
        report("syncing signed store indexes…")
        try:
            backend.sync()
        except StoreError as error:
            report(f"offline: showing what is installed ({error})", error=True)
            refresh()
            return
        refresh()
        report("store index verified and updated")

    for key, chip in chips.items():

        def pick(_checked=False, name=key):
            state["filter"] = name
            for other_key, other in chips.items():
                other.setChecked(other_key == name)
            refresh()

        chip.clicked.connect(pick)

    search.textChanged.connect(lambda _text: refresh())
    primary.clicked.connect(open_selected)
    secondary.clicked.connect(lambda: act("remove"))
    sync_button.clicked.connect(sync)

    refresh()
    window.refresh_list = refresh
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
