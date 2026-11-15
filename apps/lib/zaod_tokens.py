"""Zaod Fluent tokens for the PySide6 first-party applications.

GENERATED FILE - do not edit.
Source: desktop/design/tokens/tokens.json
Generator: desktop/design/tools/tokens_to_python.py

Colours, spacing, radii, type sizes and motion all come from the design
tokens, so an app can never drift from the Qt Quick surfaces.
"""

from __future__ import annotations

ROLES = ('background',
 'surface',
 'surfaceAlt',
 'surfaceRaised',
 'surfaceOverlay',
 'border',
 'borderStrong',
 'textPrimary',
 'textSecondary',
 'textTertiary',
 'textDisabled',
 'accent',
 'accentHover',
 'accentPressed',
 'accentSubtle',
 'onAccent',
 'danger',
 'onDanger',
 'success',
 'warning',
 'focusRing',
 'shadow',
 'scrim')

ALIASES = {'window': 'background',
 'text': 'textPrimary',
 'muted': 'textSecondary',
 'overlay': 'surfaceOverlay'}

THEMES = {'light': {'background': '#F6F7F9',
           'surface': '#FFFFFF',
           'surfaceAlt': '#EEF1F5',
           'surfaceRaised': '#FFFFFF',
           'surfaceOverlay': '#FFFFFF',
           'border': '#818A98',
           'borderStrong': '#5F6875',
           'textPrimary': '#101418',
           'textSecondary': '#4A5260',
           'textTertiary': '#5F6875',
           'textDisabled': '#8A93A0',
           'accent': '#0067C0',
           'accentHover': '#005BA8',
           'accentPressed': '#004F91',
           'accentSubtle': '#E6F0FB',
           'onAccent': '#FFFFFF',
           'danger': '#B3261E',
           'onDanger': '#FFFFFF',
           'success': '#1B6B3A',
           'warning': '#7A5900',
           'focusRing': '#0067C0',
           'shadow': '#0B1B2B',
           'scrim': '#0B1B2B'},
 'dark': {'background': '#14161A',
          'surface': '#1B1E23',
          'surfaceAlt': '#23272E',
          'surfaceRaised': '#282D35',
          'surfaceOverlay': '#2E343D',
          'border': '#737F90',
          'borderStrong': '#8A93A0',
          'textPrimary': '#F2F4F7',
          'textSecondary': '#B4BCC8',
          'textTertiary': '#9CA6B3',
          'textDisabled': '#6C7684',
          'accent': '#4CC2FF',
          'accentHover': '#6BCEFF',
          'accentPressed': '#8AD8FF',
          'accentSubtle': '#16303F',
          'onAccent': '#101418',
          'danger': '#FFB4AB',
          'onDanger': '#3B0906',
          'success': '#7DDC9B',
          'warning': '#F5C451',
          'focusRing': '#4CC2FF',
          'shadow': '#000000',
          'scrim': '#000000'}}

SPACING = {'0': 0,
 '1': 4,
 '2': 8,
 '3': 12,
 '4': 16,
 '5': 20,
 '6': 24,
 '7': 28,
 '8': 32,
 '10': 40,
 '12': 48,
 '16': 64,
 '20': 80,
 '24': 96}

RADII = {'none': 0, 'sm': 4, 'md': 8, 'lg': 12, 'xl': 16, 'xxl': 24, 'pill': 999}

BORDERS = {'hairline': 1, 'thick': 2}

MOTION = {'fast': 120,
 'base': 160,
 'slow': 250,
 'easing': 'cubic-bezier(0.2, 0, 0, 1)',
 'easingQml': 'Easing.OutCubic'}

ELEVATION = {'0': {'blur': 0, 'y': 0, 'opacity': 0.0},
 '1': {'blur': 4, 'y': 1, 'opacity': 0.08},
 '2': {'blur': 12, 'y': 2, 'opacity': 0.12},
 '3': {'blur': 24, 'y': 6, 'opacity': 0.16},
 '4': {'blur': 40, 'y': 12, 'opacity': 0.2}}

TYPE_SCALE = {'typeCaption': {'size': 11, 'lineHeight': 16, 'weight': 400, 'tracking': 0.2},
 'typeBodySm': {'size': 12, 'lineHeight': 16, 'weight': 400, 'tracking': 0.1},
 'typeBody': {'size': 14, 'lineHeight': 20, 'weight': 400, 'tracking': 0.0},
 'typeBodyStrong': {'size': 14, 'lineHeight': 20, 'weight': 600, 'tracking': 0.0},
 'typeSubtitle': {'size': 16, 'lineHeight': 24, 'weight': 600, 'tracking': 0.0},
 'typeTitle': {'size': 20, 'lineHeight': 28, 'weight': 600, 'tracking': -0.1},
 'typeTitleLg': {'size': 24, 'lineHeight': 32, 'weight': 600, 'tracking': -0.2},
 'typeDisplay': {'size': 32, 'lineHeight': 40, 'weight': 600, 'tracking': -0.4}}

FOCUS = {'ringWidth': 2, 'ringOffset': 2, 'minTargetSize': 32, 'minPointerTarget': 28}

OPACITY = {'glass': 0.92, 'scrim': 0.48, 'hover': 0.08, 'pressed': 0.12, 'disabled': 0.45, 'hint': 0.6}

LITE = {'elevationCap': 1,
 'allowBlur': False,
 'allowGlass': False,
 'allowAnimation': False,
 'allowPreviews': False,
 'allowThumbnails': False,
 'wallpaperTier': 'flat',
 'note': 'Lite profile for 1366x768 / 2 GB / 2 cores: no blur, no glass, no animation, shadows '
         'capped at level 1, flat wallpaper tier. Text scale is never capped.'}

FONT_FAMILIES = {'text': 'Inter', 'display': 'Inter', 'mono': 'JetBrains Mono', 'fallback': 'Noto Sans'}

SCALE_RANGE = {'min': 100, 'max': 150, 'step': 25, 'reflowAt': 125}


def role_map(theme: str = 'light') -> dict[str, str]:
    """Colour roles plus the short aliases app code uses."""
    colours = dict(THEMES[theme])
    for alias, role in ALIASES.items():
        colours[alias] = colours[role]
    return colours
