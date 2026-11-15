#!/usr/bin/env python3
"""Zaod Calculator: integer and decimal arithmetic with a safe expression parser."""

from __future__ import annotations

import ast
import operator
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp

OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
}


def safe_eval(expression: str) -> str:
    """Evaluate basic arithmetic without ever calling eval()."""
    tree = ast.parse(expression.replace("x", "*").replace("÷", "/"), mode="eval")

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPERATORS:
            return OPERATORS[type(node.op)](walk(node.operand))
        raise ValueError("unsupported expression")

    value = walk(tree)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return f"{value:.10g}"


def build_window():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QPushButton

    window = zaodapp.base_window("Calculator", 360, 420)
    display = QLineEdit()
    display.setPlaceholderText("0")
    display.setAlignment(Qt.AlignmentFlag.AlignRight)
    display.setObjectName("calcDisplay")
    window.content.addWidget(display)

    grid = QGridLayout()
    grid.setSpacing(8)
    keys = [
        ("7", "8", "9", "/"),
        ("4", "5", "6", "*"),
        ("1", "2", "3", "-"),
        ("0", ".", "=", "+"),
    ]
    for row, line in enumerate(keys):
        for column, label in enumerate(line):
            button = QPushButton(label)
            button.setMinimumHeight(46)

            def collect(_checked=False, label=label):
                if label == "=":
                    try:
                        display.setText(safe_eval(display.text() or "0"))
                    except (ValueError, SyntaxError, ZeroDivisionError):
                        display.setText("error")
                    return
                display.setText(display.text() + label)

            button.clicked.connect(collect)
            grid.addWidget(button, row, column)
    window.content.addLayout(grid)

    clear = QPushButton("Clear")
    clear.clicked.connect(display.clear)
    window.content.addWidget(clear)
    hint = QLabel("Type an expression or use the keypad.")
    hint.setObjectName("muted")
    window.content.addWidget(hint)
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
