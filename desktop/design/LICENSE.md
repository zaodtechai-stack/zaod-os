# Zaod design assets licence

## Design tokens, generated themes, shell QML and wallpapers

Copyright 2026 the Zaod OS project.

- `tokens.json`, the generated QML singleton, the generated GTK stylesheets, the
  shell QML components and the generated wallpaper SVGs are released under
  **CC-BY-4.0** (https://creativecommons.org/licenses/by/4.0/). You may reuse
  and adapt them with attribution to "Zaod OS".
- The code in `tools/` is released under the same licence as the rest of the
  Zaod OS build system.

## Fonts

The design system references these typefaces. They are not bundled here; the
rootfs installs the Debian packages named below, which carry the licence files
into `/usr/share/doc/<package>/copyright` and into
`/usr/share/zaod/licenses`.

| Family | Role | Debian package | Licence |
| --- | --- | --- | --- |
| Inter | Text and display | `fonts-inter` | SIL Open Font License 1.1 (OFL-1.1) |
| JetBrains Mono | Monospace | `fonts-jetbrains-mono` | SIL Open Font License 1.1 (OFL-1.1) |
| Noto Sans | Fallback coverage | `fonts-noto-core` | SIL Open Font License 1.1 (OFL-1.1) |

## Icon and cursor themes

The shell uses the `breeze-icon-theme` Debian package (LGPL-3.0-or-later) and
the `Zaod` cursor theme generated from the design tokens. The original SVG
glyphs shipped in `icons/` are CC-BY-4.0 like the rest of the visual language.

## Provenance statement

No asset in this directory is copied from, derived from, or named after a
Microsoft or Windows product. "Zaod Fluent" is the name of this project's own
design system. Windows 11 is referenced in the PRD only as a layout inspiration
for the centred taskbar and Start menu behaviour; no Microsoft artwork, font,
sound, icon, logo or trademark is used anywhere in the tree. The automated scan
in `tests/check_design_tokens.py` enforces that statement.
