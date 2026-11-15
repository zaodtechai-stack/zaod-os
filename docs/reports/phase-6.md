## Zaod OS Phase 6 report: Fluent design system, visual audit and accessibility

- Date (UTC): 2026-11-16
- Host: Linux x86_64 (container), Python 3.11, PySide6 6.12.0 Qt 6.9, offscreen platform
- Verification style: every claim below is a real render or a real gate run on this host.
  Surfaces were captured at 1366x768 in both themes (48 PNGs). Items that need a bootable
  image (Plasma session, greeter, Firefox, hardware floor) are marked BLOCKED, because this
  repository still has no Phases 3-5 output to boot.

## Gates (all green)

| Gate | Command | Result |
| --- | --- | --- |
| Token consistency | `python3 tests/check_design_tokens.py` | 1653 checks, 0 failed, 60 contrast pairs, lowest ratio 3.08:1 |
| Design drift | `python3 tests/check_design_drift.py` | 38 files scanned, 0 findings |
| QML compiles | `python3 desktop/design/tools/check_qml.py` | 17 surfaces compiled, 0 failed |
| Visual capture | `python3 desktop/design/tools/capture_surfaces.py --lite` | 48 images, 0 failed |

`tests/check_design_drift.py` is negative-tested: a probe file with `color: "#ff0000"`,
`font.pixelSize: 18` and `radius: 7` produces three findings, so a green run means
something.

## 1. Visual audit

`docs/reports/phase-6-screenshots/` holds 18 surfaces x 2 themes at 1366x768, plus 12
lite-profile captures at 150% text. `manifest.json` records what produced each file.

| Surface | Kind | Light | Dark |
| --- | --- | --- | --- |
| desktop (wallpaper + taskbar) | QML | yes | yes |
| start menu | QML | yes | yes |
| quick settings | QML | yes | yes |
| notifications | QML | yes | yes |
| component kit (all Zaod components) | QML | yes | yes |
| Notes, Tasks, Calculator, Converter, Clock, Monitor, Editor, Viewer, Store, Studio, Control Center, OOBE | app | yes | yes |
| Firefox | app | BLOCKED | BLOCKED |
| Calendar, Files | app | MISSING | MISSING |

Audit findings that are about *absence*, not styling:

- **Calendar and Files do not exist.** The brief lists 15 surfaces; the repo ships 13 app
  packages. Two of the surfaces the design system is supposed to cover have no application
  to style, so they cannot be audited. They are listed here rather than quietly skipped.
- **Firefox cannot be rendered without an image.** `apps/firefox` is an upstream repack
  (`build.py` fetches the official ESR tarball at build time); there is no payload to run on
  this host. It has no Zaod chrome of its own by design: it uses the GTK theme, which is
  verified through the drift gate and token-derived CSS, not through a screenshot.
- **The SDDM greeter theme is excluded from `check_qml.py`.** It needs the greeter's QML
  module; the exclusion is printed by the tool rather than silent.

## 2. Defect list

These were found by auditing the sources and by rendering. The first four made large parts
of the design system *non-functional while every existing gate stayed green*, which is why
the enforcement gates in section 3 exist.

| # | Defect | Where | Severity |
| --- | --- | --- | --- |
| 1 | Generator emitted `readonly property color` lines *inside* the palette object literals, so `ZaodTheme.qml` did not compile. Every QML surface in the product was dead. | `desktop/design/tools/tokens_to_qml.py` | blocker |
| 2 | Emitted type names were `typeBodysm` / `typeBodystrong`; three components referenced `typeBodySm` / `typeBodyStrong`. | same | blocker |
| 3 | `ZaodButton` re-declared `hovered`, a final property of `Control`, so it did not compile. | `qml/ZaodButton.qml` | blocker |
| 4 | `scrim` was exposed as the raw opaque role, so the start menu, quick settings and notification centre painted a **solid black panel** over the desktop instead of dimming it. | `tokens_to_qml.py` | high |
| 5 | `ZaodMenu` attached `Keys` to a `Popup`; `Popup` is not an `Item`, so keyboard navigation was inert. | `qml/ZaodMenu.qml` | high |
| 6 | First-party apps carried their own palette: accent `#0b57d0` (token `#0067C0`), light border `#dde1e8` (~1.4:1), dark text `#ffffff` on a light accent fill. | `apps/lib/zaodapp.py` | high |
| 7 | UI border tokens failed 3:1 against the surfaces they are drawn on: 2.96:1 (light, `surfaceAlt`), 2.82:1 (dark, `surfaceAlt`), 2.36:1 (dark, `surfaceOverlay`). | `tokens.json` | high (a11y) |
| 8 | Taskbar items and quick-setting tiles were pointer-only: no `activeFocusOnTab`, no key handler, no accessible role. | `shell/Taskbar.qml`, `shell/QuickSettings.qml` | high (a11y) |
| 9 | Menu rows and the start-menu current item showed selection with a tint only, so keyboard focus was invisible to a user who cannot see the hue shift. | `qml/ZaodMenu.qml`, `shell/StartMenu.qml` | medium |
| 10 | Hardcoded sizes outside the token set: switch track 44/24/16, taskbar glyph 18, start-menu 560x600, button spinner 10, quick-settings caption 12. | components + shell | medium |
| 11 | Studio project icons used a literal palette hex, so generated projects ignored the theme. | `studio/zaodstudio/project.py` | medium |
| 12 | A component could be authored with `elevation4` even though the ladder stops at 3. | tokens | medium |

## 3. Fixes, expressed only as token values or component changes

No new font, no new dependency, no colour outside `tokens.json`.

Token additions (all consumed by generated QML, CSS and Python):

| Block | Values | Why |
| --- | --- | --- |
| `layout` | taskbar 44/40 (lite), item count 8, start menu 560x600, quick settings 380, notifications 400, menu 256, window chrome 40, min window 480x320, icon sizes 20/24/28/64, grid cell 96 | replaces every hardcoded shell dimension |
| `opacity` | glass 0.92, scrim 0.48, hover 0.08, pressed 0.12, disabled 0.45, hint 0.6 | state styling without literal alphas |
| `focus` | ring 2, offset 2, min target 32, min pointer target 28 | the brief's 28 px floor, with slack |
| `typography.scaleRange` | 100-150, step 25, reflow at 125 | text scale contract, single source |
| `lite` | elevation cap 1, blur/glass/animation/previews/thumbnails all false, flat wallpaper tier | the 2 GB profile, switchable not implied |
| `elevationUsage` | max component level 3, per-level meaning | makes "no shadow above 3" enforceable |
| `motion` | fast 120, base 160, slow 250, `cubic-bezier(0.2, 0, 0, 1)` | one duration scale |

Colour changes, both themes kept in parity:

- `light.border` `#848D9A` -> `#818A98` (now 3.08-3.49:1 against every light surface).
- `dark.border` `#626C7B` -> `#737F90` (now 3.09-4.46:1 against every dark surface).

Generator changes: palettes are emitted as plain object literals; `scrim` is emitted
composited with `opacityScrim` and the raw role is kept as `scrimBase`; type names map
correctly; a new `tokens_to_python.py` emits `apps/lib/zaod_tokens.py` so the 13 Python
surfaces have no palette of their own.

Component changes: `ZaodButton` (variants Primary/Secondary/Quiet/Destructive, token
borders, token spinner), `ZaodSwitch` (token track/knob/margins), `ZaodCard` (token
elevation, capped by `elevationCap`), `ZaodMenu` (keys on the content item, ring on the
current row), `ZaodToolbar`, `ZaodTheme` (lite profile, `scaled()`, `duration()`),
`Taskbar` (focusable items + ring), `QuickSettings` (focusable tiles + ring),
`StartMenu` (ring on the current tile), `NotificationCenter`.

Enforcement added, so none of the above can regress:

- `tests/check_design_drift.py`: no hex literal, no numeric `font.pixelSize`, no numeric
  radius/spacing/margin in QML; no hex and no inline `font-size` in app code; `elevation4`
  refused; every file with a `MouseArea` must declare keyboard focus, and every file that
  takes focus must draw the `focusRingWidth` token.
- `desktop/design/tools/check_qml.py`: loads every surface with the real engine.
- `tests/check_design_tokens.py`: now also checks the `layout` grid, the lite switches,
  the elevation cap, the text-scale range, the target sizes, the flat wallpaper tier and
  the generated Python module.

## 4. Lite mode: what drops, collapses or defers

The profile is a set of token switches, not a separate theme. `ZaodTheme.lite` is set by the
session; apps never set it themselves.

| Surface | Full profile | Lite profile at 1366x768 / 2 GB |
| --- | --- | --- |
| Wallpaper | full gradient artwork | `flat` tier: single fill plus two shapes, no gradient, no metadata |
| Window blur / acrylic | backdrop blur, glass at 0.92 | **dropped**: opaque `surface` |
| Scrim | blurred backdrop dim | dim only (0.48), no blur pass |
| Shadows | levels 0-3, layered | **capped at 1**: level 2 and 3 surfaces get the border and a 4 px opaque underlay instead of a shadow |
| Start menu | 560x600 with pinned grid and recents | same geometry, **recents dropped**, 4 columns |
| Quick settings | 380 wide, all tiles | same, **brightness/volume sliders deferred into one row** |
| Notifications | 400 wide with group headers | same width, **group headers collapse to a count**, one card per app |
| File thumbnails, image and PDF previews | rendered previews | **dropped**: icon plus filename; previews return when the app is focused |
| Motion | 120-250 ms | `duration()` returns **0**; state changes are instant |
| Hit targets, contrast, focus rings, text scale | unchanged | **unchanged**: lite never reduces legibility |

## 5. Icon and wallpaper proposal

The 9 existing icons could not cover 13 apps plus navigation. The set is now generated from
`tokens.json` so it can never drift:

- **39 navigation glyphs** (back, forward, up, home, search, settings, power, network,
  volume, battery, wifi, bluetooth, brightness, night-light, notifications, apps, files,
  folder, download, upload, edit, trash, copy, share, refresh, play, pause, next, previous,
  plus, minus, close, minimise, maximise, restore, check, warning, info, user) in `onSurface`
  and `onAccent` tones: 78 files.
- **15 application tiles** (the 13 shipped apps plus Calendar and Files, which the design
  system is ready for) in light and dark tones: 30 files.
- One `ZaodIcon.qml` resolves by name with a glyph fallback, so a missing icon degrades to
  text instead of an empty box.

Wallpapers: 3 original designs (`aurora`, `lattice`, `horizon`) x 2 themes x 2 tiers
(full, `flat`) = 12 files. The flat tier is the lite wallpaper and is also what the
greeter uses.

## 6. Accessibility pass

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Body text >= 4.5:1 | `textPrimary` / `textSecondary` / `textTertiary` pairs checked against every surface they are drawn on | 60 contrast pairs, worst 3.08:1 (a border, not text); text pairs all >= 4.5:1 |
| Borders and focus rings >= 3:1 | retuned `border` tokens; `focusRing` checked against `surface`, `surfaceAlt`, `surfaceOverlay`, `background` | 3.08-4.46:1 after the fix; three pairs failed before it |
| Focus visible without relying on colour | the ring is an **added 2 px border with a 2 px offset**, so focus changes the shape of the control, not only its hue; every custom control that took `MouseArea` now declares `activeFocusOnTab` plus Space/Return | `check_design_drift.py` fails a file with a pointer area and no keyboard focus |
| Minimum 28 px hit targets | `focus.minTargetSize` 32, `minPointerTarget` 28; menu rows assert `max(minTargetSize, ...)` | token gate asserts both >= 28 |
| Text scale 100-150% without clipping | every `pixelSize` goes through `scaled()`; `reflowAt` 125 declared; lite-mode capture at 150% | 12 captures at `-lite150-`, inspected at 1366x768 |

Remaining a11y gap, stated plainly: text scale is exercised through `scaled()` and captured
at 150%, but there is no automated clipping detector. A per-widget `QFontMetrics`
assertion is the next step and needs the Qt widget layer, not QML.

## 7. Motion and elevation rules (short enough to enforce)

Elevation, per `tokens.json`:

1. **0**: in-flow surfaces. Toolbars, list rows, inline forms, the taskbar.
2. **1**: cards and grouped containers that belong to the page.
3. **2**: surfaces that float: quick settings, notification centre, start menu, menus, tooltips.
4. **3**: modal dialogs and the focused window frame.
5. **4**: reserved, not available to components. `check_design_drift.py` refuses it.

Motion:

- Only three durations: `fast` 120 ms (state, hover, press), `base` 160 ms (open/close of a
  menu or panel, elevation change), `slow` 250 ms (full-surface transition such as entering
  the start menu). Nothing else is allowed.
- One easing: `cubic-bezier(0.2, 0, 0, 1)`.
- Animate opacity and transform only. Never animate layout, size of text, or colour of text.
- In the lite profile `duration()` returns 0, so every animation is instant; nothing needs a
  separate code path.

## Known gaps

- Calendar and Files have no application package; their icons and tokens exist.
- Firefox needs a downloaded ESR tarball and a running image to photograph.
- Plasma session, SDDM greeter and hardware-floor behaviour stay BLOCKED until Phases 3-5
  produce a bootable rootfs and ISO.
- The Store renders only with `ZAOD_LIB` pointing at the in-tree `zaod/` library; on a real
  system it uses `/usr/lib/zaod`, which is why the capture helper sets it.

## Files

- Design sources: `desktop/design/tokens/tokens.json`, `qml/`, `shell/`, `gtk/`, `icons/`,
  `wallpapers/`, `tools/` (generators, `check_qml.py`, `capture_surfaces.py`, `_render_app.py`)
- Generated: `ZaodTheme.qml`, `zaod.css`, `apps/lib/zaod_tokens.py`, 117 icon SVGs, 12 wallpapers
- Gates: `tests/check_design_tokens.py`, `tests/check_design_drift.py`,
  `desktop/design/tools/check_qml.py`
- Evidence: `docs/reports/phase-6-screenshots/` (48 PNGs + `manifest.json`)
