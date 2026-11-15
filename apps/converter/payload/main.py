#!/usr/bin/env python3
"""Zaod Converter: unit conversion with exact factors."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import zaodapp

LENGTH = {"Metre": 1.0, "Kilometre": 1000.0, "Centimetre": 0.01, "Inch": 0.0254, "Foot": 0.3048, "Mile": 1609.344}
MASS = {"Kilogram": 1.0, "Gram": 0.001, "Pound": 0.45359237, "Ounce": 0.028349523125}
TEMPERATURE = {"Celsius": None, "Fahrenheit": None, "Kelvin": None}
CATEGORIES = {"Length": LENGTH, "Mass": MASS, "Temperature": TEMPERATURE}


def convert(category: str, value: float, source: str, target: str) -> float:
    if category == "Temperature":
        celsius = {"Celsius": value, "Fahrenheit": (value - 32) * 5 / 9, "Kelvin": value - 273.15}[source]
        return {"Celsius": celsius, "Fahrenheit": celsius * 9 / 5 + 32, "Kelvin": celsius + 273.15}[target]
    factors = CATEGORIES[category]
    return value * factors[source] / factors[target]


def build_window():
    from PySide6.QtWidgets import (
        QComboBox,
        QDoubleSpinBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    window = zaodapp.base_window("Converter", 460, 420)
    category_box = QComboBox()
    category_box.addItems(list(CATEGORIES))
    window.content.addWidget(category_box)

    source_box = QComboBox()
    target_box = QComboBox()
    for box in (source_box, target_box):
        box.addItems(list(LENGTH))
    window.content.addWidget(source_box)
    window.content.addWidget(target_box)

    amount = QDoubleSpinBox()
    amount.setRange(-1_000_000, 1_000_000)
    amount.setValue(1.0)
    amount.setDecimals(4)
    window.content.addWidget(amount)

    result = QLabel("1")
    result.setStyleSheet("font-size: 30px; font-weight: 600;")
    window.content.addWidget(result)

    def refill_units() -> None:
        units = list(CATEGORIES[category_box.currentText()])
        for box in (source_box, target_box):
            box.blockSignals(True)
            box.clear()
            box.addItems(units)
            box.blockSignals(False)
        target_box.setCurrentIndex(min(1, len(units) - 1))
        recompute()

    def recompute() -> None:
        try:
            value = convert(category_box.currentText(), amount.value(), source_box.currentText(), target_box.currentText())
        except (KeyError, ZeroDivisionError):
            result.setText("error")
            return
        result.setText(f"{value:,.4f}".rstrip("0").rstrip("."))

    category_box.currentTextChanged.connect(lambda _text: refill_units())
    for box in (source_box, target_box):
        box.currentTextChanged.connect(lambda _text: recompute())
    amount.valueChanged.connect(lambda _value: recompute())

    swap = QPushButton("Swap units")
    swap.clicked.connect(lambda: (
        source_box.setCurrentText(target_box.currentText()),
        target_box.setCurrentText(source_box.currentText()),
    ))
    window.content.addWidget(swap)
    window.content.addLayout(QVBoxLayout())
    recompute()
    return window


def main() -> int:
    return zaodapp.run(build_window)


if __name__ == "__main__":
    sys.exit(main())
