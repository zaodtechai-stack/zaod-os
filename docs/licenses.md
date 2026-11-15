# Licence register and source offers

Zaod OS ships free software, so the corresponding source must be available for as long
as the binaries are distributed.

| Component | Licence | Source we distribute |
| --- | --- | --- |
| Zaod OS build scripts, `zaod` package manager, first-party apps | MIT | this repository |
| Linux kernel | GPL-2.0-only | pinned tarball, fetched by `make fetch` and recorded in `docs/reports/phase-1.md` |
| Debian trixie base packages | per package (GPL, LGPL, MIT, BSD, ...) | `build/out/rootfs/` package list plus the Debian archive source |
| Plasma desktop and Qt | LGPL-2.1-or-later / GPL where applicable | source packages of the exact versions pinned in `docs/versions.md` |
| Firefox ESR | MPL-2.0 | the unmodified official tarball (sha256 recorded) plus `distribution/policies.json`, which is the only file we add |
| Python and PySide6 | PSF-2.0 / LGPL-3.0 | source packages of the pinned versions |

Rules we keep:

1. Every package's `MANIFEST.json` carries a `license` field; `zaod info` prints it.
2. We do not strip or alter upstream copyright notices.
3. Firefox is repackaged, not patched: the tarball hash is verified and the only change is
   the search policy file, which is documented in `docs/reports/phase-8.md`.
4. Any binary we distribute is accompanied by a written offer to provide its source, kept
   current in the release directory as `SOURCE-OFFER.txt`.

`SOURCE-OFFER.txt` is generated with the release and points at the exact tag plus the
archive locations for every third-party component listed above.
