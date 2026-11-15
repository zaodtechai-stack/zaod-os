"""Shared helpers for Zaod first-party applications (MIT licensed, original).

Every first-party app bundles this file so it works offline as a self-contained
``.zaod`` package. Colours, spacing, radii, type sizes and motion come from
``zaod_tokens``, which is generated from ``desktop/design/tokens/tokens.json``,
so a widget app and a QML surface can never show a different accent or a border
that misses the 3:1 UI contrast floor.

Text scale, lite mode and the theme all come from the environment the session
sets, never from a per-app preference:

* ``ZAOD_THEME=light|dark``        force a theme (otherwise ``ZAOD_COLOR_SCHEME``)
* ``ZAOD_TEXT_SCALE=100..150``     text scale percentage
* ``ZAOD_LITE=1``                  lite profile: no shadows, no motion, no previews
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import zaod_tokens as tokens  # noqa: E402  (local, generated, bundled with every app)

SCALE_RANGE = tokens.SCALE_RANGE


def is_dark() -> bool:
    """Follow the desktop theme; ``ZAOD_THEME=dark|light`` overrides it."""
    override = os.environ.get("ZAOD_THEME", "").strip().lower()
    if override in ("dark", "light"):
        return override == "dark"
    return os.environ.get("ZAOD_COLOR_SCHEME", "").lower().endswith("dark")


def text_scale() -> float:
    """Text scale between 1.0 and 1.5, clamped to the declared range."""
    raw = os.environ.get("ZAOD_TEXT_SCALE", "").strip().rstrip("%")
    try:
        value = float(raw) / 100 if raw else 1.0
    except ValueError:
        value = 1.0
    low = SCALE_RANGE["min"] / 100
    high = SCALE_RANGE["max"] / 100
    return max(low, min(high, value))


def is_lite() -> bool:
    """Lite profile: 1366x768, 2 GB RAM, no GPU assumption."""
    return os.environ.get("ZAOD_LITE", "").strip() in ("1", "true", "yes")


def font_px(step: str) -> int:
    """A type-scale step in device pixels at the current text scale."""
    return round(tokens.TYPE_SCALE[step]["size"] * text_scale())


def palette() -> dict[str, str]:
    """The active colour roles, with the short aliases app code uses."""
    return tokens.role_map("dark" if is_dark() else "light")


# The short names stay available for code that imported them directly.
LIGHT = tokens.role_map("light")
DARK = tokens.role_map("dark")


def accent() -> str:
    return palette()["accent"]


def stylesheet() -> str:
    """The app stylesheet, built only from design tokens."""
    c = palette()
    radius = tokens.RADII["md"]
    radius_lg = tokens.RADII["lg"]
    hairline = tokens.BORDERS["hairline"]
    ring = tokens.FOCUS["ringWidth"]
    pad_y = tokens.SPACING["2"]
    pad_x = tokens.SPACING["3"]
    gap = tokens.SPACING["3"]
    target = tokens.FOCUS["minTargetSize"]
    mono = tokens.FONT_FAMILIES["mono"]
    body = font_px("typeBody")
    caption = font_px("typeCaption")
    # The title role is 20 px; a window heading steps up one notch and never
    # exceeds the display step, so 150% text still fits a 1366 px window.
    heading = min(font_px("typeTitleLg"), font_px("typeDisplay"))
    hero = font_px("typeTitleLg")
    subtitle = font_px("typeSubtitle")
    metric = font_px("typeDisplay")

    return f"""
    QWidget {{
        background: {c['background']};
        color: {c['textPrimary']};
        font-family: {tokens.FONT_FAMILIES['text']}, "{tokens.FONT_FAMILIES['fallback']}";
        font-size: {body}px;
    }}
    QLabel {{ background: transparent; }}
    QLabel#title {{
        font-size: {heading}px;
        font-weight: {tokens.TYPE_SCALE['typeTitleLg']['weight']};
        color: {c['textPrimary']};
        padding-bottom: {tokens.SPACING['1']}px;
    }}
    QLabel#subtitle {{ font-size: {subtitle}px; color: {c['textSecondary']}; }}
    QLabel#muted {{ color: {c['textSecondary']}; }}
    QLabel#hero {{
        font-size: {hero}px;
        font-weight: {tokens.TYPE_SCALE['typeTitleLg']['weight']};
        color: {c['textPrimary']};
    }}
    QLabel#metric {{
        font-size: {metric}px;
        font-weight: {tokens.TYPE_SCALE['typeDisplay']['weight']};
        color: {c['textPrimary']};
    }}
    QLineEdit#calcDisplay {{
        font-size: {hero}px;
        padding: {pad_y}px {pad_x}px;
        qproperty-alignment: AlignRight;
    }}
    QFrame#preview {{
        background: {c['accentSubtle']};
        border: {hairline}px solid {c['accent']};
        border-radius: {radius_lg}px;
    }}

    QLabel#caption {{ font-size: {caption}px; color: {c['textTertiary']}; }}
    QLabel#danger {{ color: {c['danger']}; }}
    QLabel#success {{ color: {c['success']}; }}

    QPushButton, QToolButton {{
        background: {c['surface']};
        color: {c['textPrimary']};
        border: {hairline}px solid {c['border']};
        border-radius: {radius}px;
        padding: {pad_y}px {pad_x}px;
        min-height: {target}px;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {c['surfaceAlt']};
        border-color: {c['borderStrong']};
    }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['accentSubtle']}; }}
    QPushButton:focus, QToolButton:focus {{
        border: {ring}px solid {c['focusRing']};
        outline: none;
    }}
    QPushButton:disabled, QToolButton:disabled {{ color: {c['textDisabled']}; }}
    QPushButton#primary {{
        background: {c['accent']};
        color: {c['onAccent']};
        border: {ring}px solid {c['accent']};
        font-weight: {tokens.TYPE_SCALE['typeBodyStrong']['weight']};
    }}
    QPushButton#primary:hover {{ background: {c['accentHover']}; border-color: {c['accentHover']}; }}
    QPushButton#primary:pressed {{ background: {c['accentPressed']}; border-color: {c['accentPressed']}; }}
    QPushButton#primary:focus {{ border: {ring}px solid {c['focusRing']}; }}
    QPushButton#danger {{ background: {c['danger']}; color: {c['onDanger']}; border-color: {c['danger']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QComboBox, QSpinBox {{
        background: {c['surface']};
        color: {c['textPrimary']};
        border: {hairline}px solid {c['border']};
        border-radius: {radius}px;
        padding: {pad_y}px;
        selection-background-color: {c['accent']};
        selection-color: {c['onAccent']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus,
    QComboBox:focus, QSpinBox:focus {{
        border: {ring}px solid {c['focusRing']};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled {{ color: {c['textDisabled']}; }}

    QListWidget::item {{ padding: {tokens.SPACING['2']}px; border-radius: {tokens.RADII['sm']}px; }}
    QListWidget::item:selected {{ background: {c['accentSubtle']}; color: {c['textPrimary']}; }}
    QListWidget::item:hover {{ background: {c['surfaceAlt']}; }}

    QHeaderView::section {{
        background: {c['surfaceAlt']};
        color: {c['textSecondary']};
        border: none;
        border-bottom: {hairline}px solid {c['border']};
        padding: {tokens.SPACING['2']}px;
    }}
    QScrollBar:vertical, QScrollBar:horizontal {{ background: transparent; width: {tokens.SPACING['3']}px; }}
    QScrollBar::handle {{ background: {c['border']}; border-radius: {tokens.RADII['sm']}px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

    QCheckBox, QRadioButton {{ spacing: {tokens.SPACING['2']}px; min-height: {target}px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: {tokens.SPACING['4']}px; height: {tokens.SPACING['4']}px;
        border: {ring}px solid {c['borderStrong']};
        background: {c['surface']};
    }}
    QCheckBox::indicator {{ border-radius: {tokens.RADII['sm']}px; }}
    QRadioButton::indicator {{ border-radius: {tokens.RADII['sm'] + tokens.SPACING['2']}px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {c['accent']}; border-color: {c['accent']};
    }}
    QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {c['focusRing']}; }}

    QProgressBar {{
        background: {c['surfaceAlt']}; border: {hairline}px solid {c['border']};
        border-radius: {radius}px; height: {tokens.SPACING['2']}px; text-align: center;
        color: {c['textPrimary']};
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: {radius}px; }}

    QTabWidget::pane {{ border: {hairline}px solid {c['border']}; border-radius: {radius}px; }}
    QTabBar::tab {{
        background: transparent; color: {c['textSecondary']};
        padding: {pad_y}px {pad_x}px; margin-right: {tokens.SPACING['1']}px;
        border-radius: {radius}px; min-height: {target}px;
    }}
    QTabBar::tab:selected {{ background: {c['accentSubtle']}; color: {c['textPrimary']}; }}
    QTabBar::tab:focus {{ border: {ring}px solid {c['focusRing']}; }}

    QToolTip {{
        background: {c['surfaceOverlay']}; color: {c['textPrimary']};
        border: {hairline}px solid {c['border']}; border-radius: {radius}px;
        padding: {tokens.SPACING['2']}px;
    }}
    QMenu {{
        background: {c['surfaceOverlay']}; color: {c['textPrimary']};
        border: {hairline}px solid {c['border']}; border-radius: {radius}px;
        padding: {tokens.SPACING['1']}px;
    }}
    QMenu::item {{ padding: {pad_y}px {pad_x}px; border-radius: {tokens.RADII['sm']}px; }}
    QMenu::item:selected {{ background: {c['accentSubtle']}; }}
    QMenu::separator {{
        height: {hairline}px; background: {c['border']};
        margin: {tokens.SPACING['1']}px {tokens.SPACING['2']}px;
    }}
    QStatusBar {{ color: {c['textSecondary']}; }}
    QSplitter::handle {{ background: {c['border']}; }}
    QGroupBox {{
        border: {hairline}px solid {c['border']}; border-radius: {radius_lg}px;
        margin-top: {gap}px; padding: {gap}px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: {gap}px; padding: 0 {pad_y}px; }}
    QFrame#card {{
        background: {c['surface']}; border: {hairline}px solid {c['border']};
        border-radius: {radius_lg}px;
    }}
    QFrame#divider {{ background: {c['border']}; max-height: {hairline}px; }}
    QTableWidget, QTreeWidget, QTreeView, QTableView {{
        background: {c['surface']}; alternate-background-color: {c['surfaceAlt']};
        color: {c['textPrimary']}; border: {hairline}px solid {c['border']};
        border-radius: {radius}px; gridline-color: {c['border']};
    }}
    """


def make_app(argv: list[str] | None = None):
    """Create the QApplication with the Zaod palette applied."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("Zaod")
    # Fusion + the token stylesheet gives the same rendering in light and dark
    # and does not depend on the host widget style being installed.
    app.setStyle("Fusion")
    app.setStyleSheet(stylesheet())
    return app


def base_window(title: str, width: int = 520, height: int = 380, *, margins: int | None = None):
    """A window with a 4 px grid layout and the app title already in place."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    step = tokens.SPACING["5"]
    if margins is None:
        margins = step
    window = QWidget()
    window.setWindowTitle(title)
    window.resize(width, height)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(step - tokens.SPACING["2"])
    heading = QLabel(title)
    heading.setObjectName("title")
    heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
    heading.setWordWrap(True)
    layout.addWidget(heading)
    window.heading = heading
    window.content = layout
    return window


def run(window_builder, argv: list[str] | None = None) -> int:
    """Run an app: build the window, show it, enter the Qt event loop."""
    app = make_app(argv)
    window = window_builder()
    window.show()
    return app.exec()


def data_dir(app_id: str):
    """Writable per-app data directory (the sandbox maps it to ``/data``)."""
    from pathlib import Path

    base = os.environ.get("HOME", str(Path.home()))
    path = Path(base) / ".zaod" / "data" / app_id
    if (Path(base) / ".local").exists() or Path(base).name == "data":
        path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path
