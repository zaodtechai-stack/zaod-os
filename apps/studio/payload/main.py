#!/usr/bin/env python3
"""Zaod Studio: scaffold, edit, build, verify and run `.zaod` projects."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import ClassVar

HERE = Path(__file__).resolve().parent
for candidate in (HERE, HERE / "lib", HERE.parents[2] / "studio" if len(HERE.parents) > 2 else HERE):
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import zaodapp
from zaodstudio import (
    TEMPLATES,
    Project,
    ProjectError,
    build_project,
    developer_keys,
    scaffold,
)
from zaodstudio.project import key_id_of, run_package

TERMINAL_SUFFIXES = (".sh",)


def build_window(project_root: Path | None = None):
    from PySide6.QtCore import QRegularExpression, Qt
    from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
    from PySide6.QtWidgets import (
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTextEdit,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    class Highlighter(QSyntaxHighlighter):
        """Small syntax highlighter for the languages Studio templates ship."""

        KEYWORDS: ClassVar[list[str]] = ["and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif", "else", "except", "False", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "None", "nonlocal", "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield", "int", "char", "void", "const", "static", "struct", "printf", "include", "define", "cmake_minimum_required", "project", "add_executable", "set", "function", "local", "if", "then", "fi", "for", "do", "done", "echo"]

        def __init__(self, document):
            super().__init__(document)
            self.rules = []
            # Highlight roles come from the token palette, so the editor is
            # legible in both themes instead of only on a white background.
            colours = zaodapp.palette()
            keyword = QTextCharFormat()
            keyword.setForeground(QColor(colours["accent"]))
            keyword.setFontWeight(QFont.Weight.DemiBold)
            for word in self.KEYWORDS:
                self.rules.append((QRegularExpression(rf"\b{word}\b"), keyword))
            string = QTextCharFormat()
            string.setForeground(QColor(colours["success"]))
            self.rules.append((QRegularExpression(r'"[^"\n]*"'), string))
            self.rules.append((QRegularExpression(r"'[^'\n]*'"), string))
            comment = QTextCharFormat()
            comment.setForeground(QColor(colours["textTertiary"]))
            comment.setFontItalic(True)
            self.rules.append((QRegularExpression(r"#[^\n]*"), comment))
            number = QTextCharFormat()
            number.setForeground(QColor(colours["warning"]))
            self.rules.append((QRegularExpression(r"\b[0-9]+\b"), number))

        def highlightBlock(self, text: str) -> None:
            for pattern, style in self.rules:
                matcher = pattern.globalMatch(text)
                while matcher.hasNext():
                    match = matcher.next()
                    self.setFormat(match.capturedStart(), match.capturedLength(), style)

    class NewProjectDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("New project")
            layout = QFormLayout(self)
            self.template = QComboBox()
            for name, template in TEMPLATES.items():
                self.template.addItem(f"{template.label}  ({name})", name)
            self.app_id = QLineEdit("org.example.myapp")
            self.name = QLineEdit("My App")
            self.folder = QLineEdit()
            browse = QPushButton("Choose…")
            browse.clicked.connect(self.pick_folder)
            folder_row = QWidget()
            folder_layout = QHBoxLayout(folder_row)
            folder_layout.setContentsMargins(0, 0, 0, 0)
            folder_layout.addWidget(self.folder, 1)
            folder_layout.addWidget(browse)
            layout.addRow("Template", self.template)
            layout.addRow("App id", self.app_id)
            layout.addRow("Name", self.name)
            layout.addRow("Folder", folder_row)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addRow(buttons)

        def pick_folder(self) -> None:
            chosen = QFileDialog.getExistingDirectory(self, "Choose a folder")
            if chosen:
                self.folder.setText(chosen)

    window = zaodapp.base_window("Zaod Studio", 1080, 700)
    state = {"project": None, "file": None, "path": None}

    toolbar = QHBoxLayout()
    for label, slot in (
        ("New", "new"),
        ("Open", "open"),
        ("Save", "save"),
        ("Build", "build"),
        ("Run", "run"),
        ("Verify", "verify"),
    ):
        button = QPushButton(label)
        if slot == "build":
            button.setObjectName("primary")
        button.setProperty("action", slot)
        toolbar.addWidget(button)
    toolbar.addStretch(1)
    key_label = QLabel("")
    key_label.setObjectName("muted")
    toolbar.addWidget(key_label)
    window.content.addLayout(toolbar)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    window.content.addWidget(splitter, 1)

    tree = QTreeWidget()
    tree.setHeaderLabels(["Project", ""])
    tree.setMinimumWidth(230)
    splitter.addWidget(tree)

    editor_panel = QWidget()
    editor_layout = QVBoxLayout(editor_panel)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    find_row = QHBoxLayout()
    find = QLineEdit()
    find.setPlaceholderText("Find in file")
    matches = QLabel("")
    matches.setObjectName("muted")
    find_row.addWidget(find, 1)
    find_row.addWidget(matches)
    editor_layout.addLayout(find_row)
    editor = QPlainTextEdit()
    editor.setFont(QFont("JetBrains Mono", 11))
    editor_layout.addWidget(editor, 1)
    splitter.addWidget(editor_panel)

    console_title = QLabel("Build output")
    console_title.setObjectName("muted")
    window.content.addWidget(console_title)
    console = QTextEdit()
    console.setReadOnly(True)
    console.setMaximumHeight(190)
    console.setFont(QFont("JetBrains Mono", 10))
    window.content.addWidget(console)

    status = QLabel("Create a project or open an existing one.")
    status.setObjectName("muted")
    window.content.addWidget(status)

    highlighter = Highlighter(editor.document())
    window.highlighter = highlighter

    def log(lines) -> None:
        if isinstance(lines, str):
            lines = [lines]
        console.append("\n".join(str(line) for line in lines))

    def refresh_tree() -> None:
        tree.clear()
        if not state["project"]:
            return
        for path in state["project"].source_files():
            relative = path.relative_to(state["project"].root)
            item = QTreeWidgetItem([relative.name, relative.parent.as_posix() if str(relative.parent) != "." else ""])
            item.setData(0, Qt.ItemDataRole.UserRole, str(relative))
            tree.addTopLevelItem(item)

    def load_project(root: Path) -> None:
        try:
            project = Project.load(root)
        except ProjectError as error:
            status.setText(str(error))
            return
        state["project"] = project
        state["file"] = None
        refresh_tree()
        first = next((p for p in project.source_files() if p.suffix == ".py"), None)
        if first:
            open_file(first.relative_to(project.root).as_posix())
        window.setWindowTitle(f"Zaod Studio — {project.name} {project.version}")
        try:
            private_key, _public = developer_keys()
            key_label.setText(f"dev key {key_id_of(private_key)}")
        except Exception:  # noqa: BLE001 - the key is optional until the first build
            key_label.setText("no developer key")
        status.setText(f"{project.id} · {project.template.name} · {len(project.source_files())} files")

    def open_file(relative: str) -> None:
        project = state["project"]
        if not project:
            return
        try:
            content = project.read_source(relative)
        except ProjectError as error:
            status.setText(str(error))
            return
        state["file"] = relative
        state["path"] = project.root / relative
        editor.setPlainText(content)
        editor.setReadOnly(False)
        status.setText(relative)

    def save_file() -> bool:
        project = state["project"]
        if not project or not state["file"]:
            return False
        project.write_source(state["file"], editor.toPlainText())
        status.setText(f"saved {state['file']}")
        return True

    def action_new() -> None:
        dialog = NewProjectDialog(window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dialog.folder.text().strip()
        if not folder:
            status.setText("choose a folder for the new project")
            return
        try:
            project = scaffold(
                dialog.template.currentData(),
                Path(folder),
                dialog.app_id.text().strip(),
                dialog.name.text().strip() or None,
            )
        except ProjectError as error:
            status.setText(str(error))
            return
        log(f"created {project.id} from {project.template.name}")
        load_project(project.root)

    def action_open() -> None:
        folder = QFileDialog.getExistingDirectory(window, "Open a Studio project")
        if folder:
            load_project(Path(folder))

    def action_build() -> None:
        project = state["project"]
        if not project:
            status.setText("open a project first")
            return
        if not save_file():
            log("nothing to save")
        private_key, _public = developer_keys()
        status.setText("building…")
        try:
            result = build_project(project.root, private_key=private_key, level=10)
        except ProjectError as error:
            log([f"error: {error}"])
            status.setText(f"build failed: {error}")
            return
        log(result.log)
        status.setText(f"built {result.package.name} ({result.size} bytes) sha256 {result.sha256[:16]}")

    def action_run() -> None:
        project = state["project"]
        if not project:
            return
        action_build()
        package = project.root / "build" / "out" / f"{project.id}-{project.version}.zaod"
        if not package.is_file():
            return
        dev_root = Path(os.environ.get("HOME", "~")).expanduser() / ".zaod" / "devroot"
        try:
            completed = run_package(package, project.id, dev_root)
        except ProjectError as error:
            log(f"error: {error}")
            status.setText("run failed")
            return
        log(completed.stdout.strip().splitlines() or ["(no output)"])
        if completed.stderr.strip():
            log(completed.stderr.strip().splitlines())
        status.setText(f"exit code {completed.returncode}")

    def action_verify() -> None:
        project = state["project"]
        if not project:
            return
        package = project.root / "build" / "out" / f"{project.id}-{project.version}.zaod"
        if not package.is_file():
            status.setText("build the project before verifying it")
            return
        try:
            from zaodlib import install
            from zaodlib import paths as zaod_paths

            verified = install.verify_package(zaod_paths.Paths(), package, allow_unsigned=True)
        except Exception as error:  # noqa: BLE001 - surface every verification problem
            log(f"verify failed: {error}")
            status.setText("verification failed")
            return
        log(f"ok {verified.manifest.id} {verified.manifest.version} · {len(verified.checksums)} files")
        if verified.signed:
            log(f"signed by {verified.key_id}")
        status.setText("package verified")

    def find_next() -> None:
        needle = find.text()
        if not needle:
            matches.setText("")
            return
        document_text = editor.toPlainText()
        count = document_text.count(needle)
        matches.setText(f"{count} match{'es' if count != 1 else ''}")
        if not editor.find(needle):
            cursor = editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            editor.find(needle)

    for button in window.findChildren(QPushButton):
        action = button.property("action")
        if action:
            button.clicked.connect(
                {
                    "new": action_new,
                    "open": action_open,
                    "save": save_file,
                    "build": action_build,
                    "run": action_run,
                    "verify": action_verify,
                }[action]
            )
    tree.itemActivated.connect(lambda item, _column: open_file(item.data(0, Qt.ItemDataRole.UserRole)))
    tree.itemClicked.connect(lambda item, _column: open_file(item.data(0, Qt.ItemDataRole.UserRole)))
    find.returnPressed.connect(find_next)

    if project_root:
        load_project(Path(project_root))
    return window


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    return zaodapp.run(lambda: build_window(root))


if __name__ == "__main__":
    sys.exit(main())
