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

import zaod_tokens as tokens

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


def _mix(foreground: str, background: str, amount: float) -> str:
    """Blend two #rrggbb colours: ``amount`` of foreground over background."""
    f = [int(foreground[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(background[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(fv * amount + bv * (1 - amount)):02X}" for fv, bv in zip(f, b))


def stylesheet() -> str:
    """The app stylesheet, built only from design tokens.

    Three kinds of edge, because one border colour cannot do all three jobs:

    * panels and cards are separated by *elevation* (a slightly lighter surface)
      and a barely-there hairline, never by a bright outline;
    * input controls (fields, combo boxes, check boxes) keep the full-contrast
      ``border`` token, which is what WCAG 1.4.11 asks the *control boundary* for;
    * keyboard focus is a ring, drawn only for Tab focus (buttons are given
      ``Qt.TabFocus`` so a mouse click never paints a cyan box).
    """
    c = palette()
    dark = is_dark()
    radius = tokens.RADII["md"]
    radius_lg = tokens.RADII["lg"]
    radius_sm = tokens.RADII["sm"]
    hairline = tokens.BORDERS["hairline"]
    ring = tokens.FOCUS["ringWidth"]
    target = tokens.FOCUS["minTargetSize"]
    body = font_px("typeBody")
    caption = font_px("typeCaption")
    heading = min(font_px("typeTitleLg"), font_px("typeDisplay"))
    hero = font_px("typeTitleLg")
    subtitle = font_px("typeSubtitle")
    metric = font_px("typeDisplay")

    # Derived tones: a hairline that sits quietly on every surface, and a hover
    # step between surface and surfaceAlt.
    edge = _mix(c["textPrimary"], c["surface"], 0.10 if dark else 0.14)
    edge_soft = _mix(c["textPrimary"], c["background"], 0.06 if dark else 0.09)
    hover = _mix(c["textPrimary"], c["surface"], 0.06 if dark else 0.05)
    pressed = _mix(c["textPrimary"], c["surface"], 0.10 if dark else 0.09)
    card = c["surfaceAlt"]
    field = c["surface"]
    font = f'{tokens.FONT_FAMILIES["text"]}, "{tokens.FONT_FAMILIES["fallback"]}"'

    return f"""
    * {{ outline: none; }}
    QWidget {{
        color: {c['textPrimary']};
        font-family: {font};
        font-size: {body}px;
    }}
    QWidget#zaodWindow, QDialog {{ background: {c['background']}; }}
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
    QAbstractScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}

    QLabel#title {{
        font-size: {heading}px;
        font-weight: 600;
        color: {c['textPrimary']};
        padding-bottom: {tokens.SPACING['1']}px;
    }}
    QLabel#subtitle {{ font-size: {subtitle}px; color: {c['textSecondary']}; }}
    QLabel#muted {{ color: {c['textSecondary']}; }}
    QLabel#hero {{ font-size: {hero}px; font-weight: 600; color: {c['textPrimary']}; }}
    QLabel#metric {{ font-size: {metric}px; font-weight: 600; color: {c['textPrimary']}; }}
    QLabel#caption {{ font-size: {caption}px; color: {c['textTertiary']}; }}
    QLabel#danger {{ color: {c['danger']}; }}
    QLabel#success {{ color: {c['success']}; }}
    QLabel#sectionTitle {{
        font-size: {caption}px; font-weight: 600; color: {c['textTertiary']};
        letter-spacing: 1px; padding-top: {tokens.SPACING['2']}px;
    }}
    QLineEdit#calcDisplay {{
        font-size: {hero}px; padding: 8px 12px; qproperty-alignment: AlignRight;
    }}

    /* ---- surfaces: elevation, not outlines ------------------------------- */
    QFrame#card, QFrame#preview {{
        background: {card};
        border: {hairline}px solid {edge_soft};
        border-radius: {radius_lg}px;
    }}
    QFrame#panel {{
        background: {c['surface']};
        border: {hairline}px solid {edge_soft};
        border-radius: {radius_lg}px;
    }}
    QFrame#sidebar {{
        background: {c['surface']};
        border: none;
        border-right: {hairline}px solid {edge_soft};
    }}
    QFrame#divider {{ background: {edge_soft}; max-height: {hairline}px; min-height: {hairline}px; border: none; }}
    QFrame#row {{
        background: transparent; border: none;
        border-bottom: {hairline}px solid {edge_soft};
    }}

    /* ---- buttons ---------------------------------------------------------- */
    QPushButton, QToolButton {{
        background: {c['surfaceAlt']};
        color: {c['textPrimary']};
        border: {hairline}px solid {edge};
        border-radius: {radius}px;
        padding: 6px 14px;
        min-height: {target - 4}px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {hover}; border-color: {_mix(c['textPrimary'], c['surface'], 0.18)}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {pressed}; }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {c['textDisabled']}; background: transparent; border-color: {edge_soft};
    }}
    QPushButton:checked {{ background: {c['accentSubtle']}; border-color: {c['accent']}; }}
    QPushButton:focus {{ border: {ring}px solid {c['focusRing']}; }}
    QPushButton#primary {{
        background: {c['accent']}; color: {c['onAccent']};
        border: {hairline}px solid {c['accent']}; font-weight: 600;
    }}
    QPushButton#primary:hover {{ background: {c['accentHover']}; border-color: {c['accentHover']}; }}
    QPushButton#primary:pressed {{ background: {c['accentPressed']}; border-color: {c['accentPressed']}; }}
    QPushButton#primary:disabled {{
        background: {edge}; color: {c['textDisabled']}; border-color: {edge};
    }}
    QPushButton#danger {{
        background: transparent; color: {c['danger']}; border: {hairline}px solid {c['danger']};
    }}
    QPushButton#danger:hover {{ background: {_mix(c['danger'], c['surface'], 0.14)}; }}
    QPushButton#flat {{ background: transparent; border: none; }}
    QPushButton#flat:hover {{ background: {hover}; }}

    /* a navigation entry in a sidebar */
    QPushButton#nav {{
        background: transparent; border: none; border-radius: {radius}px;
        text-align: left; padding: 8px 12px; color: {c['textSecondary']};
    }}
    QPushButton#nav:hover {{ background: {hover}; color: {c['textPrimary']}; }}
    QPushButton#nav:checked {{ background: {c['accentSubtle']}; color: {c['textPrimary']}; font-weight: 600; }}

    /* a filter chip */
    QPushButton#chip {{
        background: transparent; border: {hairline}px solid {edge};
        border-radius: 999px; padding: 4px 14px; min-height: 24px;
        color: {c['textSecondary']};
    }}
    QPushButton#chip:hover {{ background: {hover}; color: {c['textPrimary']}; }}
    QPushButton#chip:checked {{
        background: {c['accent']}; color: {c['onAccent']}; border-color: {c['accent']};
    }}

    /* a selectable card (store grid, wallpapers) */
    QPushButton#tile {{
        background: {card}; border: {hairline}px solid {edge_soft};
        border-radius: {radius_lg}px; text-align: left; padding: 0px;
    }}
    QPushButton#tile:hover {{ background: {hover}; border-color: {edge}; }}
    QPushButton#tile:checked {{ background: {c['accentSubtle']}; border: 2px solid {c['accent']}; }}

    /* ---- inputs: the control boundary keeps the strong border ------------ */
    QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox {{
        background: {field};
        color: {c['textPrimary']};
        border: {hairline}px solid {c['border']};
        border-radius: {radius}px;
        padding: 6px 10px;
        selection-background-color: {c['accent']};
        selection-color: {c['onAccent']};
    }}
    QTextBrowser, QPlainTextEdit, QTextEdit {{ border-color: {edge}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: {ring}px solid {c['focusRing']}; padding: 5px 9px;
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled {{ color: {c['textDisabled']}; border-color: {edge_soft}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {c['surfaceOverlay']}; border: {hairline}px solid {edge};
        selection-background-color: {c['accentSubtle']}; selection-color: {c['textPrimary']};
        outline: none; padding: 4px;
    }}

    QListWidget, QListView {{
        background: transparent; border: none; outline: none;
    }}
    QListWidget::item {{ padding: 8px 10px; border-radius: {radius_sm}px; margin: 1px 0; }}
    QListWidget::item:selected {{ background: {c['accentSubtle']}; color: {c['textPrimary']}; }}
    QListWidget::item:hover:!selected {{ background: {hover}; }}

    QHeaderView::section {{
        background: {c['surfaceAlt']}; color: {c['textSecondary']};
        border: none; border-bottom: {hairline}px solid {edge}; padding: 8px;
    }}
    QTableWidget, QTreeWidget, QTreeView, QTableView {{
        background: {c['surface']}; alternate-background-color: {c['surfaceAlt']};
        color: {c['textPrimary']}; border: {hairline}px solid {edge_soft};
        border-radius: {radius}px; gridline-color: {edge_soft};
    }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {_mix(c['textPrimary'], c['background'], 0.22)}; border-radius: 3px; min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: {_mix(c['textPrimary'], c['background'], 0.36)}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QCheckBox, QRadioButton {{ spacing: 8px; min-height: {target - 6}px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px; height: 16px;
        border: {hairline}px solid {c['border']}; background: {c['surface']};
    }}
    QCheckBox::indicator {{ border-radius: {radius_sm}px; }}
    QRadioButton::indicator {{ border-radius: 9px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {c['accent']}; border-color: {c['accent']};
    }}
    QCheckBox::indicator:focus, QRadioButton::indicator:focus {{ border-color: {c['focusRing']}; }}

    QSlider::groove:horizontal {{ height: 4px; background: {edge}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {c['textPrimary']}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    }}

    QProgressBar {{
        background: {edge}; border: none; border-radius: 3px; max-height: 6px; text-align: center; color: transparent;
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}

    QTabWidget::pane {{ border: {hairline}px solid {edge_soft}; border-radius: {radius}px; }}
    QTabBar::tab {{
        background: transparent; color: {c['textSecondary']};
        padding: 6px 14px; margin-right: 4px; border-radius: {radius}px; min-height: {target - 8}px;
    }}
    QTabBar::tab:selected {{ background: {c['accentSubtle']}; color: {c['textPrimary']}; }}

    QToolTip {{
        background: {c['surfaceOverlay']}; color: {c['textPrimary']};
        border: {hairline}px solid {edge}; border-radius: {radius}px; padding: 6px;
    }}
    QMenu {{
        background: {c['surfaceOverlay']}; color: {c['textPrimary']};
        border: {hairline}px solid {edge}; border-radius: {radius}px; padding: 4px;
    }}
    QMenu::item {{ padding: 6px 14px; border-radius: {radius_sm}px; }}
    QMenu::item:selected {{ background: {c['accentSubtle']}; }}
    QMenu::separator {{ height: {hairline}px; background: {edge_soft}; margin: 4px 8px; }}
    QStatusBar {{ color: {c['textSecondary']}; }}
    QSplitter::handle {{ background: {edge_soft}; }}
    QGroupBox {{
        border: {hairline}px solid {edge_soft}; border-radius: {radius_lg}px;
        margin-top: 12px; padding: 12px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 8px; }}
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


def window_icon(app_id: str):
    """The app's own icon, or the Zaod mark - never the toolkit's default.

    Without this every PySide6 window carries Qt's generic icon (the Python
    logo), which is what shows up in the bar and the window switcher.
    """
    from pathlib import Path as _Path

    from PySide6.QtGui import QIcon

    icon = QIcon.fromTheme(app_id)
    if not icon.isNull():
        return icon
    for size in ("128x128", "64x64", "48x48", "scalable"):
        for suffix in ("png", "svg"):
            path = _Path(f"/usr/share/icons/hicolor/{size}/apps/{app_id}.{suffix}")
            if path.exists():
                return QIcon(str(path))
    for fallback in ("/usr/share/zaod/artwork/logo.png", "/usr/share/zaod/logo.png"):
        if _Path(fallback).exists():
            return QIcon(fallback)
    return QIcon()


def app_id_from_argv(argv: list[str] | None = None) -> str:
    """org.zaod.<name> for a payload running from /opt/zaod/apps/<name>/."""
    given = os.environ.get("ZAOD_APP_ID", "")
    if given:
        return given
    argv = argv if argv is not None else sys.argv
    for part in argv:
        text = str(part)
        if "/apps/" in text:
            name = text.split("/apps/", 1)[1].split("/", 1)[0]
            if name:
                return f"org.zaod.{name}"
    return "org.zaod"


def base_window(title: str, width: int = 520, height: int = 380, *, margins: int | None = None):
    """A window with a 4 px grid layout and the app title already in place."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    step = tokens.SPACING["5"]
    if margins is None:
        margins = step
    window = QWidget()
    window.setObjectName("zaodWindow")
    window.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    window.setWindowTitle(title)
    window.setWindowIcon(window_icon(app_id_from_argv()))
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
    app.setWindowIcon(window_icon(app_id_from_argv(argv)))
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
