"""Unit tests for first-party app logic (no display required)."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

APPS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APPS / "lib"))


def load(slug: str, name: str):
    entry = APPS / slug / "payload" / "main.py"
    spec = importlib.util.spec_from_file_location(name, entry)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


calculator = load("calculator", "app_calculator")
clock = load("clock", "app_clock")
converter = load("converter", "app_converter")
editor = load("editor", "app_editor")
monitor = load("monitor", "app_monitor")
tasks = load("tasks", "app_tasks")
notes = load("notes", "app_notes")


class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(calculator.safe_eval("2+3*4"), "14")
        self.assertEqual(calculator.safe_eval("(2+3)*4"), "20")
        self.assertEqual(calculator.safe_eval("10/4"), "2.5")

    def test_alternate_operators(self):
        self.assertEqual(calculator.safe_eval("6÷2"), "3")
        self.assertEqual(calculator.safe_eval("3x3"), "9")

    def test_rejects_names_and_calls(self):
        for expression in ("__import__('os').system('true')", "open('/etc/passwd')", "abc"):
            with self.assertRaises(ValueError):
                calculator.safe_eval(expression)

    def test_division_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            calculator.safe_eval("1/0")


class ConverterTests(unittest.TestCase):
    def test_length(self):
        self.assertAlmostEqual(converter.convert("Length", 1, "Kilometre", "Metre"), 1000.0)
        self.assertAlmostEqual(converter.convert("Length", 1, "Inch", "Centimetre"), 2.54)

    def test_mass(self):
        self.assertAlmostEqual(converter.convert("Mass", 1, "Pound", "Kilogram"), 0.45359237)

    def test_temperature(self):
        self.assertAlmostEqual(converter.convert("Temperature", 0, "Celsius", "Fahrenheit"), 32.0)
        self.assertAlmostEqual(converter.convert("Temperature", 100, "Celsius", "Kelvin"), 373.15)


class MonitorTests(unittest.TestCase):
    MEMINFO = "MemTotal:        2048000 kB\nMemFree:          500000 kB\nMemAvailable:    1024000 kB\n"

    def test_memory_maths(self):
        used, total, percent = monitor.read_memory(self.MEMINFO)
        self.assertEqual(total, 2048000 * 1024)
        self.assertEqual(used, 1024000 * 1024)
        self.assertEqual(percent, 50)

    def test_load_parsing(self):
        self.assertEqual(monitor.read_load("0.52 0.31 0.20 1/230 4242\n"), (0.52, 0.31, 0.2))

    def test_uptime_formatting(self):
        self.assertEqual(monitor.read_uptime("3725.44 9000.00\n"), "1h 2m")


class SmallHelperTests(unittest.TestCase):
    def test_elapsed_formatting(self):
        self.assertEqual(clock.format_elapsed(0), "00:00")
        self.assertEqual(clock.format_elapsed(65), "01:05")

    def test_word_count(self):
        self.assertEqual(editor.word_count("one two  three\n"), 3)
        self.assertEqual(editor.word_count(""), 0)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.previous = os.environ.get("HOME")
        os.environ["HOME"] = self.home

    def tearDown(self):
        if self.previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self.previous

    def test_tasks_roundtrip(self):
        self.assertEqual(tasks.load_tasks(), [])
        tasks.save_tasks([{"title": "write tests", "done": True}])
        self.assertEqual(tasks.load_tasks(), [{"title": "write tests", "done": True}])

    def test_tasks_survive_broken_json(self):
        tasks.tasks_file().write_text("{not json", encoding="utf-8")
        self.assertEqual(tasks.load_tasks(), [])

    def test_notes_path_is_per_app(self):
        path = notes.notes_file()
        self.assertIn("org.zaod.notes", str(path))
        self.assertTrue(path.parent.is_dir())


class WindowSmokeTests(unittest.TestCase):
    """Construct every app window offscreen when Qt is available."""

    def test_every_app_builds_a_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:  # pragma: no cover - only when Qt is missing
            self.skipTest("PySide6 is not installed")
        app = QApplication.instance() or QApplication([])
        for slug in ("calculator", "clock", "converter", "editor", "hello-gui", "monitor", "notes", "tasks", "viewer"):
            module = load(slug, f"window_{slug.replace('-', '_')}")
            window = module.build_window()
            self.assertGreaterEqual(window.width(), 200, slug)
            self.assertIsNotNone(window.windowTitle(), slug)
            window.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
