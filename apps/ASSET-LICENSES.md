# Application asset licences

Every file here declares where the artwork in `apps/*` comes from. The asset scan
(`desktop/design/tools/scan_assets.py`) walks up from each asset until it finds a document
like this one, so the declaration below covers all application directories.

## Original Zaod artwork

- `apps/{calculator,clock,control-center,converter,editor,hello-gui,monitor,notes,oobe,store,studio,tasks,viewer}/icon.svg`
  are original Zaod OS artwork, generated from `desktop/design/tokens/tokens.json` by
  `desktop/design/tools/make_icons.py` (the fifteen application tiles). They contain no
  third-party mark, glyph or trademark, and are covered by the repository licence.

## Third-party artwork

- `apps/firefox/icon.svg` is the Mozilla Firefox logo, reproduced for identification of the
  packaged application. Firefox is distributed here under the Mozilla Public License 2.0
  and the Mozilla Trademark Policy. The icon is not modified, and the application itself is
  an unmodified repack of the official Mozilla ESR tarball; see `apps/firefox/MANIFEST.json`
  and `docs/licenses.md`.

## Rules for adding an icon

1. Draw it from tokens (24 px navigation grid, 64 px application tile) with
   `make_icons.py` where possible.
2. Never copy artwork belonging to another operating system vendor. The asset scan
   fails the build on those terms, and this document must stay clear of them too.
3. If an icon belongs to a third-party project, add it to the second section above with the
   licence name, so the scan stays green for the right reason.
