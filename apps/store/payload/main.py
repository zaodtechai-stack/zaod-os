#!/usr/bin/env python3
"""Zaod Store: one place for the apps on this system.

Three catalogues meet here:

* the apps the image installs, read from /usr/share/applications;
* the optional set (YouTube, WhatsApp, Instagram, Facebook, TikTok, X and Zaod
  Studio), shipped in /usr/share/zaod/optional and added per person on request -
  nobody is forced to have a social app in their launcher;
* a signed repository, browsed through ``zaodlib`` when one is configured.

Every card is a button, so a click anywhere on it opens the details pane with the
one action that applies: Add, Open, Install, Update or Remove.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "lib"))

import zaodapp
from backend import StoreBackend, StoreError

APPLICATIONS = Path("/usr/share/applications")
OPTIONAL_ROOT = Path("/usr/share/zaod/optional")
USER_APPLICATIONS = Path(os.environ.get("HOME", "/root")) / ".local/share/applications"
USER_ICONS = Path(os.environ.get("HOME", "/root")) / ".local/share/icons/hicolor/scalable/apps"
USER_APPS = Path(os.environ.get("HOME", "/root")) / ".local/share/zaod/apps"


def parse_entry(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return fields
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())
    return fields


def installed_entries() -> dict[str, dict[str, str]]:
    """Launcher entries that are on this system, by app id."""
    entries: dict[str, dict[str, str]] = {}
    for directory in (APPLICATIONS, USER_APPLICATIONS):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.desktop")):
            fields = parse_entry(path)
            app_id = fields.get("X-Zaod-AppId")
            if app_id:
                entries[app_id] = fields
    return entries


def card_from_entry(app_id: str, fields: dict[str, str]) -> dict:
    web = fields.get("X-Zaod-WebApp", "")
    return {
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


def optional_apps(installed: dict[str, dict[str, str]]) -> list[dict]:
    """The optional set, flagged with whether this person has already added it."""
    items: list[dict] = []
    manifest = OPTIONAL_ROOT / "webapps/webapps.json"
    if manifest.is_file():
        try:
            for app in json.loads(manifest.read_text())["apps"]:
                item = {
                    "id": app["id"],
                    "name": app["name"],
                    "summary": app.get("summary", ""),
                    "icon": app.get("icon", app["id"]),
                    "kind": "web",
                    "url": app.get("url", ""),
                    "categories": app.get("category", "Web"),
                    "state": "installed" if app["id"] in installed else "optional",
                    "version": "",
                    "license": "",
                    "repository": "optional",
                    "size": 0,
                    "description": app.get("summary", ""),
                }
                items.append(item)
        except (OSError, ValueError, KeyError):
            pass
    apps_dir = OPTIONAL_ROOT / "apps"
    if apps_dir.is_dir():
        for manifest_path in sorted(apps_dir.glob("*/MANIFEST.json")):
            try:
                data = json.loads(manifest_path.read_text())
            except (OSError, ValueError):
                continue
            app_id = data.get("id") or manifest_path.parent.name
            items.append(
                {
                    "id": app_id,
                    "name": data.get("name", app_id),
                    "summary": data.get("summary", ""),
                    "icon": data.get("id", app_id),
                    "kind": "app",
                    "url": "",
                    "categories": ",".join(data.get("categories", [])),
                    "state": "installed" if app_id in installed else "optional",
                    "version": data.get("version", ""),
                    "license": "",
                    "repository": "optional",
                    "size": 0,
                    "description": data.get("summary", ""),
                }
            )
    return items


def remember_in_hub(app_id: str, installed: bool) -> None:
    """Tell the local backend what this person installed.

    The launch entries on disk stay the source of truth, so nothing in the store's
    own flow waits on this: no hub, no session or a refused call only means the
    per-user record could not be kept.
    """
    try:
        from zaodhub import HubError, HubUnavailable, signed_in_hub
    except ImportError:
        return
    try:
        hub = signed_in_hub()
        if hub.token:
            hub.mark_installed(app_id, installed)
    except (HubUnavailable, HubError):
        return


def add_optional(item: dict) -> str:
    """Add an optional app for this person, into their own XDG directories."""
    USER_APPLICATIONS.mkdir(parents=True, exist_ok=True)
    USER_ICONS.mkdir(parents=True, exist_ok=True)
    app_id = item["id"]
    if item["kind"] == "web":
        manifest = OPTIONAL_ROOT / "webapps/webapps.json"
        apps = {a["id"]: a for a in json.loads(manifest.read_text())["apps"]}
        app = apps.get(app_id)
        if not app:
            raise StoreError(f"{app_id} is not in the optional set")
        icon_src = OPTIONAL_ROOT / "webapps/icons" / f"{app_id}.svg"
        if icon_src.is_file():
            shutil.copy2(icon_src, USER_ICONS / icon_src.name)
        (USER_APPLICATIONS / f"{app_id}.desktop").write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={app['name']}\nComment={app.get('summary', '')}\n"
            f"Exec=/usr/local/bin/zaod-webapp {app['url']}\n"
            f"Icon={app['icon']}\nTerminal=false\n"
            f"Categories=Network;{app.get('category', 'Utility')};\n"
            "StartupNotify=true\n"
            f"X-Zaod-AppId={app_id}\nX-Zaod-WebApp={app['url']}\n"
        )
        return f"{app['name']} added to your launcher"

    source = OPTIONAL_ROOT / "apps" / app_id
    if not source.is_dir():
        # The directory is named after the app, the id carries the vendor prefix
        # (apps/studio vs org.zaod.studio), so the manifest decides.
        for candidate in sorted((OPTIONAL_ROOT / "apps").glob("*/MANIFEST.json")):
            try:
                if json.loads(candidate.read_text()).get("id") == app_id:
                    source = candidate.parent
                    break
            except (OSError, ValueError):
                continue
    if not source.is_dir():
        raise StoreError(f"{app_id} is not in the optional set")
    target = USER_APPS / app_id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    entry = target / f"{app_id}.desktop"
    if not entry.is_file():
        entry.write_text(
            "[Desktop Entry]\nType=Application\n"
            f"Name={item['name']}\nComment={item.get('summary', '')}\n"
            f"Exec=/usr/local/bin/zaod-run {app_id} /usr/bin/python3 {target}/payload/main.py\n"
            f"Icon={item['icon']}\nTerminal=false\nCategories=Utility;\n"
            f"X-Zaod-AppId={app_id}\n"
        )
    shutil.copy2(entry, USER_APPLICATIONS / f"{app_id}.desktop")
    icon = target / "icon.svg"
    if icon.is_file():
        shutil.copy2(icon, USER_ICONS / f"{app_id}.svg")
    return f"{item['name']} added to your launcher"


def remove_optional(item: dict) -> str:
    app_id = item["id"]
    for path in (
        USER_APPLICATIONS / f"{app_id}.desktop",
        USER_ICONS / f"{app_id}.svg",
    ):
        if path.exists():
            path.unlink()
    tree = USER_APPS / app_id
    if tree.exists():
        shutil.rmtree(tree)
    return f"{item['name']} removed"


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

    window = zaodapp.base_window("Store", 1080, 720)
    c = zaodapp.palette()

    header = QHBoxLayout()
    subtitle = QLabel("Apps, web apps and Studio")
    subtitle.setObjectName("subtitle")
    header.addWidget(subtitle, 1)
    search = QLineEdit()
    search.setPlaceholderText("Search apps")
    search.setMinimumWidth(240)
    search.setClearButtonEnabled(True)
    header.addWidget(search)
    sync_button = QPushButton("Sync")
    header.addWidget(sync_button)
    account_button = QPushButton("Account")
    account_button.setObjectName("accountButton")
    account_button.setToolTip("Sign in to back up this computer and get your apps back")
    account_button.setCursor(Qt.CursorShape.PointingHandCursor)
    header.addWidget(account_button)
    window.content.addLayout(header)

    chips_row = QHBoxLayout()
    chips_row.setSpacing(8)
    chips: dict[str, QPushButton] = {}
    for key in ("All", "Installed", "Optional", "Web", "Social", "Video"):
        chip = QPushButton(key)
        chip.setCheckable(True)
        chip.setObjectName("chip")
        chip.setAutoExclusive(True)
        chip.setChecked(key == "All")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chips[key] = chip
        chips_row.addWidget(chip)
    chips_row.addStretch(1)
    window.content.addLayout(chips_row)

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
    detail_icon.setFixedSize(QSize(72, 72))
    detail_icon.setScaledContents(True)
    detail_name = QLabel("Pick an app")
    detail_name.setObjectName("hero")
    detail_name.setWordWrap(True)
    detail_meta = QLabel(" ")
    detail_meta.setObjectName("muted")
    detail_meta.setWordWrap(True)
    detail_text = QTextBrowser()
    detail_text.setOpenExternalLinks(False)
    detail_text.setMinimumHeight(150)
    detail_layout.addWidget(detail_icon)
    detail_layout.addWidget(detail_name)
    detail_layout.addWidget(detail_meta)
    detail_layout.addWidget(detail_text, 1)
    primary = QPushButton("Open")
    primary.setObjectName("primary")
    secondary = QPushButton("Remove")
    detail_layout.addWidget(primary)
    detail_layout.addWidget(secondary)
    detail_panel.setFixedWidth(330)
    body.addWidget(detail_panel)

    status = QLabel(notice or " ")
    status.setObjectName("danger" if notice else "muted")
    status.setWordWrap(True)
    window.content.addWidget(status)

    state: dict[str, object] = {"items": [], "selected": None, "filter": "All", "buttons": {}}

    def open_account() -> None:
        try:
            import zaodaccount
        except ImportError as error:  # the shared module is not on this system
            report(f"The account window is unavailable: {error}", error=True)
            return
        dialog = zaodaccount.build_dialog(window)
        dialog.exec()
        refresh()

    account_button.clicked.connect(open_account)
    window.account_button = account_button  # test hook

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
        installed = installed_entries()
        items = [card_from_entry(app_id, fields) for app_id, fields in sorted(installed.items())]
        known = {item["id"] for item in items}
        items.extend(optional_apps(installed))
        known |= {item["id"] for item in items}
        try:
            remote = backend.catalogue(search.text())
        except StoreError:
            remote = []
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
        if chip == "Installed":
            return item["state"] == "installed"
        if chip == "Optional":
            return item["state"] == "optional" or item.get("repository") == "optional"
        if chip == "Web":
            return item.get("kind") == "web"
        return chip.lower() in str(item.get("categories", "")).lower()

    def clear_grid() -> None:
        while grid.count():
            child = grid.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        state["buttons"] = {}

    def select(item: dict | None) -> None:
        state["selected"] = item
        for app_id, button in state["buttons"].items():
            button.setChecked(bool(item) and app_id == item["id"])
        if not item:
            detail_icon.clear()
            detail_name.setText("Pick an app")
            detail_meta.setText(" ")
            detail_text.setHtml("")
            primary.setEnabled(False)
            secondary.setEnabled(False)
            primary.setText("Open")
            return
        detail_icon.setPixmap(icon_for(item.get("icon", "")).pixmap(QSize(72, 72)))
        detail_name.setText(item["name"])
        bits = []
        if item.get("version"):
            bits.append(f"Version {item['version']}")
        if item.get("kind") == "web":
            bits.append("Web app")
        state_text = {
            "installed": "Added" if item.get("repository") == "optional" else "Installed",
            "optional": "Optional · not added",
            "new": "Available",
            "update": "Update available",
        }.get(item["state"], item["state"])
        bits.append(state_text)
        if item.get("repository") and item["repository"] != "optional":
            bits.append(f"Repository {item['repository']}")
        detail_meta.setText(" · ".join(bits))
        summary = item.get("description") or item.get("summary") or ""
        extra = ""
        if item.get("url"):
            extra = f"<p><b>Opens</b> {item['url']}</p>"
        detail_text.setHtml(f"<p>{summary}</p>{extra}")

        if item["state"] == "optional":
            primary.setText("Add to launcher")
            primary.setEnabled(True)
            secondary.setEnabled(False)
            secondary.setText("Remove")
        elif item["state"] == "installed":
            primary.setText("Open")
            primary.setEnabled(True)
            secondary.setText("Remove")
            secondary.setEnabled(item.get("repository") == "optional")
        else:
            primary.setText("Update" if item["state"] == "update" else "Install")
            primary.setEnabled(True)
            secondary.setText("Remove")
            secondary.setEnabled(item["state"] == "update")

    def card(item: dict) -> QPushButton:
        button = QPushButton()
        button.setCheckable(True)
        button.setObjectName("card")
        button.setAutoExclusive(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(QSize(316, 92))
        button.setStyleSheet(
            "QPushButton { text-align: left; padding: 0px; }"
            f"QPushButton:checked {{ border: 2px solid {c['accent']}; }}"
        )
        layout = QHBoxLayout(button)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        badge = QLabel()
        badge.setFixedSize(QSize(44, 44))
        badge.setScaledContents(True)
        badge.setPixmap(icon_for(item.get("icon", "")).pixmap(QSize(44, 44)))
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        column = QVBoxLayout()
        column.setSpacing(2)
        column.setContentsMargins(0, 0, 0, 0)
        title = QLabel(item["name"])
        title.setStyleSheet(f"font-weight: 600; color: {c['textPrimary']};")
        summary = QLabel(item.get("summary") or "")
        summary.setObjectName("muted")
        summary.setWordWrap(False)
        summary.setFixedHeight(18)
        summary.setText(summary.fontMetrics().elidedText(
            item.get("summary") or "", Qt.TextElideMode.ElideRight, 210))
        column.addWidget(title)
        column.addWidget(summary)
        if item["state"] == "optional":
            tag = QLabel("Optional")
            tag.setObjectName("caption")
            column.addWidget(tag)
        elif item.get("kind") == "web":
            tag = QLabel("Web app")
            tag.setObjectName("caption")
            column.addWidget(tag)
        layout.addLayout(column, 1)
        button.clicked.connect(lambda _checked=False, data=item: select(data))
        state["buttons"][item["id"]] = button
        return button

    def refresh() -> None:
        items = catalogue()
        state["items"] = items
        chip = str(state["filter"])
        query = search.text()
        visible = [item for item in items if in_chip(item, chip) and matches(item, query)]
        previous = state["selected"]["id"] if state["selected"] else None
        clear_grid()
        columns = 3
        for index, item in enumerate(visible):
            grid.addWidget(
                card(item), index // columns, index % columns,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
        rows = (len(visible) + columns - 1) // columns
        for column in range(columns):
            grid.setColumnStretch(column, 0)
        grid.setColumnStretch(columns, 1)   # the slack sits to the right, not between cards
        grid.setRowStretch(rows, 1)
        if not visible:
            report("Nothing matches that search.")
            select(None)
            return
        chosen = next((item for item in visible if item["id"] == previous), visible[0])
        select(chosen)
        added = sum(1 for item in items if item["state"] == "optional")
        report(f"{len(visible)} shown · {added} optional apps you can add")

    def act_primary() -> None:
        item = state["selected"]
        if not item:
            return
        try:
            if item["state"] == "optional":
                message = add_optional(item)
                remember_in_hub(item["id"], True)
                report(message)
                refresh()
                return
            if item["state"] == "installed":
                from gi.repository import Gio

                info = Gio.DesktopAppInfo.new(f"{item['id']}.desktop")
                if info is None:
                    report(f"no launcher entry for {item['name']}", error=True)
                    return
                info.launch([], None)
                report(f"Starting {item['name']}")
                return
            if item["state"] == "update":
                backend.update(item["id"])
            else:
                backend.install(item["id"])
        except StoreError as error:
            report(str(error), error=True)
            return
        refresh()

    def act_remove() -> None:
        item = state["selected"]
        if not item:
            return
        try:
            if item.get("repository") == "optional":
                message = remove_optional(item)
                remember_in_hub(item["id"], False)
                report(message)
                refresh()
                return
            backend.remove(item["id"])
        except StoreError as error:
            report(str(error), error=True)
            return
        refresh()

    def sync() -> None:
        report("syncing signed store indexes…")
        try:
            backend.sync()
        except StoreError as error:
            report(f"offline: showing what is on this system ({error})", error=True)
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
    primary.clicked.connect(act_primary)
    secondary.clicked.connect(act_remove)
    sync_button.clicked.connect(sync)

    refresh()
    window.refresh_list = refresh
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
