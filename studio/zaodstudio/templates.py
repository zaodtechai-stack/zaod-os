"""The five project templates Studio can scaffold.

Each template is plain data: the files it writes, the project defaults it needs,
and the build steps that turn its source into ``payload/`` content. Nothing here
imports Qt, so templates can be created and built headlessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Template:
    name: str
    label: str
    language: str
    summary: str
    entry: str
    files: dict
    defaults: dict = field(default_factory=dict)
    steps: tuple = ()
    artifacts: dict = field(default_factory=dict)
    terminal: bool = False
    tools: tuple = ()

    def render(self, app_id: str, name: str) -> dict[str, str]:
        return {
            path: content.replace("{{APP_ID}}", app_id).replace("{{APP_NAME}}", name)
            for path, content in self.files.items()
        }


PYTHON_QT_MAIN = '''#!/usr/bin/env python3
"""{{APP_NAME}} - a Zaod application."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget


def build_window() -> QMainWindow:
    window = QMainWindow()
    window.setWindowTitle("{{APP_NAME}}")
    window.resize(560, 360)
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addWidget(QLabel("{{APP_NAME}} is running."))
    layout.addStretch(1)
    window.setCentralWidget(central)
    return window


def main() -> int:
    app = QApplication(sys.argv)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
'''

PYTHON_CLI_MAIN = '''#!/usr/bin/env python3
"""{{APP_NAME}} - a Zaod command line tool."""

from __future__ import annotations

import argparse
import sys


def greet(who: str) -> str:
    return f"Hello, {who}!"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="{{APP_ID}}", description="{{APP_NAME}}")
    parser.add_argument("who", nargs="?", default="world")
    arguments = parser.parse_args(argv)
    print(greet(arguments.who))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

C_MAIN = '''#include <stdio.h>

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;
    printf("Hello from {{APP_NAME}}\\n");
    return 0;
}
'''

C_CMAKE = '''cmake_minimum_required(VERSION 3.16)
project({{APP_ID}} C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_executable({{APP_ID}} src/main.c)
# Builds are reproducible: no timestamps, no absolute paths in the binary.
add_compile_options(-ffile-prefix-map=${CMAKE_SOURCE_DIR}=.)
'''

SHELL_MAIN = '''#!/bin/bash
# {{APP_NAME}} - a shell application packaged as .zaod.
set -euo pipefail

name=${1:-world}
printf 'Hello, %s!\\n' "$name"
'''

WEB_WRAPPER_MAIN = '''#!/usr/bin/env python3
"""{{APP_NAME}} - a web wrapper application."""

from __future__ import annotations

import sys

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

HOME = "https://example.com"


def build_window() -> QMainWindow:
    window = QMainWindow()
    window.setWindowTitle("{{APP_NAME}}")
    window.resize(1024, 700)
    view = QWebEngineView()
    view.setUrl(QUrl(HOME))
    window.setCentralWidget(view)
    return window


def main() -> int:
    app = QApplication(sys.argv)
    window = build_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
'''

TEMPLATES = {
    "python-qt": Template(
        name="python-qt",
        label="Python + Qt desktop app",
        language="python",
        summary="PySide6 window with the Zaod Fluent layout; needs the PySide6 runtime.",
        entry="payload/main.py",
        files={"payload/main.py": PYTHON_QT_MAIN},
        defaults={
            "runtimes": ["org.zaod.runtime.pyside6"],
            "permissions": {"network": False, "filesystem": [], "devices": ["dri"]},
        },
    ),
    "python-cli": Template(
        name="python-cli",
        label="Python command line tool",
        language="python",
        summary="Standard library only; runs in the sandbox without extra runtimes.",
        entry="payload/main.py",
        files={"payload/main.py": PYTHON_CLI_MAIN},
        defaults={"runtimes": [], "permissions": {"network": False, "filesystem": [], "devices": []}},
        terminal=True,
    ),
    "c-cmake": Template(
        name="c-cmake",
        label="C with CMake",
        language="c",
        summary="Compiled C program; Studio runs cmake and copies the binary into the payload.",
        entry="payload/bin/app",
        files={"src/main.c": C_MAIN, "CMakeLists.txt": C_CMAKE},
        steps=(
            ("cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"),
            ("cmake", "--build", "build"),
        ),
        artifacts={"build/{{APP_ID}}": "payload/bin/app"},
        defaults={"runtimes": [], "permissions": {"network": False, "filesystem": [], "devices": []}},
        terminal=True,
        tools=("cmake", "cc"),
    ),
    "shell": Template(
        name="shell",
        label="Shell script",
        language="shell",
        summary="A bash program; useful for glue tools and quick system utilities.",
        entry="payload/main.sh",
        files={"payload/main.sh": SHELL_MAIN},
        defaults={"runtimes": [], "permissions": {"network": False, "filesystem": [], "devices": []}},
        terminal=True,
        tools=("bash",),
    ),
    "web-wrapper": Template(
        name="web-wrapper",
        label="Web wrapper",
        language="python",
        summary="Wraps a site in a desktop window; needs the PySide6 runtime with QtWebEngine.",
        entry="payload/main.py",
        files={"payload/main.py": WEB_WRAPPER_MAIN},
        defaults={
            "runtimes": ["org.zaod.runtime.pyside6"],
            "permissions": {"network": True, "filesystem": [], "devices": ["dri"]},
        },
    ),
}


def template_names() -> list[str]:
    return list(TEMPLATES)
