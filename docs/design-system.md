# Zaod Fluent design system

Zaod Fluent is the single visual language for the shell, the core applications,
the installer and the login screen. Everything is derived from one file:
`desktop/design/tokens/tokens.json`. Generated artefacts are committed so the
repository builds without running the generators, and CI fails when a generated
file drifts from the tokens.

## Layout

| Path | Contents |
| --- | --- |
| `tokens/tokens.json` | Every colour, space, radius, duration, type step, elevation and the accessibility rules |
| `tools/tokens_to_qml.py` | Generates `qml/ZaodTheme.qml` (singleton) |
| `tools/tokens_to_css.py` | Generates GTK 3 and GTK 4 stylesheets |
| `tools/make_wallpapers.py` | Generates the three original wallpapers in light and dark |
| `tools/scan_assets.py` | Repo-wide vendor asset and licence scan |
| `qml/` | Component kit: button, card, switch, menu, toolbar, window frame |
| `shell/` | Shell surfaces: taskbar, Start menu, quick settings, notifications |
| `gtk/` | Generated GTK 3 and GTK 4 themes |
| `icons/` | Original SVG glyphs, 24 px grid, drawn for this project |
| `wallpapers/` | Generated wallpaper SVGs |
| `LICENSE.md` | Asset licence and the provenance statement |

## Rules the validator enforces

`python3 tests/check_design_tokens.py --verbose` is the gate. It computes real
WCAG 2.1 contrast rather than trusting a comment:

1. **4 px grid.** Every spacing value is a multiple of 4.
2. **Radii** come from the fixed set `0, 4, 8, 12, 16, 24, 999` px and sit on the grid.
3. **Motion** is between 120 and 250 ms with a cubic-bezier easing.
4. **Typography** uses only Inter, JetBrains Mono and Noto Sans, each with an
   open licence declared in `tokens.json` and `LICENSE.md`. The type scale is
   monotonically distinguishable.
5. **Theme parity**: light and dark declare exactly the same colour roles.
6. **Contrast**: every pair in `accessibility.pairs` meets 4.5:1 for text and
   3:1 for borders and focus rings, in both themes. There are 42 pairs.
7. **Freshness**: generated QML, CSS and wallpapers must match the tokens.
8. **No vendor assets**: the scan rejects Microsoft/Windows strings and
   requires every asset directory to carry a licence document.

Current status: 352 checks, 42 contrast pairs, lowest ratio 3.13:1 (the light
theme border against the background), all text pairs at or above 4.5:1.

## Colour roles

| Role | Purpose |
| --- | --- |
| `background`, `surface`, `surfaceAlt`, `surfaceRaised`, `surfaceOverlay` | Elevation ladder, back to front |
| `border`, `borderStrong` | Hairlines and emphasised dividers |
| `textPrimary`, `textSecondary`, `textTertiary`, `textDisabled` | Text hierarchy |
| `accent`, `accentHover`, `accentPressed`, `accentSubtle`, `onAccent` | The selectable accent system; blue is the default |
| `danger`, `onDanger`, `success`, `warning` | Semantic states |
| `focusRing` | Keyboard focus, always visible `activeFocus` |
| `shadow`, `scrim` | Elevation shadow and modal scrim |

## Using the tokens in QML

```qml
import "../qml"

Rectangle {
    color: ZaodTheme.surface
    radius: ZaodTheme.radiusLg
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    Text {
        color: ZaodTheme.textPrimary
        font.family: ZaodTheme.fontFamily
        font.pixelSize: ZaodTheme.typeBody.size
    }
}
```

Components must never hardcode a colour: `tests/test_design_tools.py` fails if a
`#rrggbb` literal appears in a hand-written component. `ZaodTheme.mode` switches
between `"light"` and `"dark"` at runtime and the palette re-resolves.

## Keyboard and accessibility rules

* Every interactive component sets `activeFocusOnTab: true`, exposes
  `Accessible.role`, `Accessible.name` and, where relevant, `Accessible.checked`.
* The focus ring is drawn outside the element with the tokens
  `focusRingWidth` (2 px) and `focusRingOffset` (2 px), so focus never shifts layout.
* Minimum pointer target is 32 px (`minTargetSize`), and text never drops below
  11 px.
* State is never communicated by colour alone: toggles change position and
  shape as well as colour.
* Tab order follows reading order; menus and the Start menu support arrow keys,
  Enter to activate and Escape to dismiss.

## Adding a screen

1. Pick tokens, do not invent values. If a value is genuinely missing, add it to
   `tokens.json` and re-run the generators.
2. Build the screen from the component kit (`ZaodButton`, `ZaodCard`,
   `ZaodSwitch`, `ZaodToolbar`, `ZaodWindow`).
3. Run `python3 tests/check_design_tokens.py --verbose` and
   `python3 -m pytest tests -q`.
4. Add the screen to the Phase 6 screenshot set listed in
   `docs/reports/phase-6.md` so the visual review covers it.

## Wallpapers

Three deterministic designs are generated: `zaod-aurora`, `zaod-lattice` and
`zaod-horizon`, each in light and dark at 2560x1440. They are pure SVG geometry
derived from the palette and the 4 px grid, so they are reproducible and carry
no third-party material.
