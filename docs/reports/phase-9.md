## Zaod OS Phase 9 report: Studio, templates and deterministic project builds

- Date (UTC): 2026-11-15
- Host: Linux x86_64, Python 3.11.15, PySide6 6.12.0, cmake 3.25.1, gcc 12.2.0, gVisor build sandbox
- Verification style: unit tests, offscreen Qt rendering and real package installs. Phase 9's
  first acceptance item needs a QEMU image, which this repository still does not contain
  (Phases 3-6 are absent), so that item is reported as blocked rather than claimed.

## What shipped

| Deliverable | Path | Notes |
| --- | --- | --- |
| Studio library | `studio/zaodstudio/` | project model, manifest generation, deterministic builds, dev keys |
| Templates (5) | `studio/zaodstudio/templates.py` | Python-Qt, Python CLI, C/CMake, shell, web wrapper |
| Studio CLI | `studio/zaodstudio/cli.py` | `new`, `build`, `verify`, `run`, `templates` |
| Studio window | `apps/studio/payload/main.py` | tree, syntax-highlighted editor, find bar, console, New/Open/Save/Build/Run/Verify |
| Studio package | `apps/studio/build.py` | ships the window plus the bundled `zaodstudio` library |
| Developer guide | `docs/dev/studio.md` | project format, template rules, build steps, troubleshooting |
| Make targets | `Makefile` | `studio`, `studio-test`, studio suite added to `test` |

## Tests and lint

```
$ make test
Ran 97 tests ... OK      (package manager)
Ran 43 tests ... OK      (applications)
Ran 16 tests ... OK      (Studio, templates and projects)
$ ruff check .           All checks passed!
$ shellcheck scripts/*.sh tests/*.sh apps/*/build.sh   no findings
```

The Studio suite covers: all five templates scaffold and build, manifest defaults per template
(runtimes, network permission, terminal flag), no timestamp in the manifest, invalid app id and
unknown template errors, non-empty destination guard, reproducibility, compiled template shipping
the binary instead of its C source, broken manifest producing no package, missing entry producing
a precise error, a signed build verified through the keyring, project load/save round trip, and
developer keys created once with mode `0600`.

## Template builds (byte-reproducible)

Every template was scaffolded and built twice; both builds produced the same archive hash.

| Template | App id | Package | SHA-256 (first 16) | Reproducible |
| --- | --- | --- | --- | --- |
| `python-qt` | `org.zaodstudio.pythonqt` | 1245 bytes | `74202446c4d97f5a` | yes |
| `python-cli` | `org.zaodstudio.pythoncli` | 1195 bytes | `9986c5b486a7ffe4` | yes |
| `c-cmake` | `org.zaodstudio.ccmake` | 3118 bytes | `4f6c8f699e84d5db` | yes |
| `shell` | `org.zaodstudio.shell` | 999 bytes | `33f9c471252a079b` | yes |
| `web-wrapper` | `org.zaodstudio.webwrapper` | 1266 bytes | `0728ff4bb0297471` | yes |

The reproducibility comes from the package format: fixed tar member order, fixed mtime and
ownership, normalised JSON, and a manifest with no build timestamp. `c-cmake` also builds with
`-ffile-prefix-map` so paths and dates do not leak into the binary.

## End-to-end runs

Scaffold, sign with the developer key, install into a development root, run:

```
$ zaod-studio new shell /tmp/shdemo --id org.zaodstudio.shdemo --name "Shell Demo"
$ zaod-studio build /tmp/shdemo --sign --out /tmp/shdemo.zaod
$ zaod install /tmp/shdemo.zaod          -> installed Shell Demo 0.1.0
$ zaod run --no-sandbox org.zaodstudio.shdemo "Zaod OS"
Hello, Zaod OS!

$ zaod-studio new c-cmake /tmp/cdemo --id org.zaodstudio.cdemo --name "C Demo"
$ zaod-studio build /tmp/cdemo --sign --out /tmp/cdemo.zaod
$ zaod install /tmp/cdemo.zaod           -> installed C Demo 0.1.0
$ zaod run --no-sandbox org.zaodstudio.cdemo
Hello from C Demo

$ zaod-studio new python-cli /tmp/clidemo --id org.zaodstudio.clidemo --name "CLI Demo"
$ zaod run --no-sandbox org.zaodstudio.clidemo Zaod
Hello, Zaod!
```

`--no-sandbox` is used because this sandbox blocks network namespaces; bubblewrap fails with
`bwrap: loopback: Failed RTM_NEWADDR`, exactly as recorded in the Phase 7 report. Every other
step (build, sign, install, launch, output) is real.

## Studio package

```
$ make studio
built studio-0.9.0.zaod (11.9 KiB, org.zaod.studio 0.9.0)
$ zaod verify --allow-unsigned build/out/optional/studio-0.9.0.zaod
OK org.zaod.studio 0.9.0 (6 files)
  permissions: files: home, files: documents, device: dri
```

SHA-256 `43b4a9cdb3d0403ddbe309bcce037c5e5ae66bcbb90014235e1a513981bd5d98`. Studio writes to
`build/out/optional/`, and `repo/build-store.sh` only publishes `build/out/apps/*.zaod`, so the
store index never contains Studio. The window renders offscreen: `build/out/screens/studio.png`
(1080x700).

## Bug found and fixed while testing

`zaodlib.paths.Paths.os_version()` returned `VERSION_ID` from `/etc/os-release` unchecked. On a
plain Debian container that value is `12`, so `min_os` comparison crashed with
`version: expected MAJOR.MINOR.PATCH, got '12'` instead of reporting an incompatible host. The
reader now only accepts a semver `VERSION_ID` and otherwise falls back to the build default. This
bug was latent in Phases 7-8 because those tests always set `ZAOD_ROOT` to a root without
`/etc/os-release`.

## PRD acceptance checklist

| Acceptance item | State | Evidence |
| --- | --- | --- |
| Studio installs offline from a local repo inside QEMU | BLOCKED | No ISO or QEMU image exists in this repository; the package itself builds, verifies and installs into a development root |
| All five templates build, install and launch | PARTIAL | Build, verify and install pass for all five (16 tests); launch proven for Python CLI, shell and C; the two GUI templates render offscreen but need `org.zaod.runtime.pyside6` on a real system |
| Invalid manifest gives a precise error and produces no package | PASS | `test_broken_manifest_fails_without_a_package`, `test_missing_entry_fails_with_a_precise_error` |
| Studio is absent by default | PASS | Package goes to `build/out/optional/`; store index globs `build/out/apps` |
| Studio output passes Phase 7 validators | PASS | `zaod verify` plus manifest, entry and permission checks inside `build_package` |

## Deviations and decisions

- Studio bundles its own `zaodstudio` library into the package payload so it works offline; it
  uses the system `zaodlib` for packaging and verification.
- Only `MANIFEST.json`, `icon.svg`, screenshots and `payload/` are assembled into the archive, so
  C sources, CMake files and the project file never ship.
- `pyproject.toml` and `zaod.project.json` are different things on purpose: the former describes
  a Python project, the latter describes a `.zaod` application.
- The runtime package `org.zaod.runtime.pyside6` is still not built. It is declared by the two Qt
  templates and remains the first task of Phase 10 packaging work.

## Owner test steps

1. `make studio` and `zaod verify --allow-unsigned build/out/optional/studio-0.9.0.zaod`.
2. `make smoke` and open `build/out/screens/studio.png`.
3. `python3 -m zaodstudio.cli new python-cli ~/src/demo --id org.example.demo` (with
   `PYTHONPATH=studio`), then `build --sign` and `run --no-sandbox`.
4. In Studio: New, pick a template, Build, then Verify.

## Handover to Phase 10

- Installer, OOBE, signed update bundles, release ISO, hardware matrix and QA reports.
- Runtime packages (`org.zaod.runtime.pyside6`, and QtWebEngine support for the web wrapper).
- QEMU acceptance runs for the Studio and application items marked BLOCKED or PARTIAL here.
