# Zaod OS

Zaod OS is a lightweight x86_64 Linux desktop built from a single repository.
`PRD.md` is the source of truth and the phase plan; each finished phase has a
report under `docs/reports/`.

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Foundation, toolchain, feasibility | done, `docs/reports/phase-1.md` |
| 2 | Kernel 6.18 LTS with the Zaod config | done, `docs/reports/phase-2.md` |
| 7 | `.zaod` format and package manager | done, `docs/reports/phase-7.md` |
| 8 | Applications, Store and Control Center | done, `docs/reports/phase-8.md` |
| 9 | Studio, templates and project builds | done, `docs/reports/phase-9.md` |

## Repository layout

```
kernel/     kernel config, build script
scripts/    host setup, fetch and build helpers
zaod/       package manager: zaodlib, CLI, spec, tests
apps/       Zaod application sources and their build recipes
repo/       store hosting output
tests/      repository-wide test and proof scripts
docs/       reports, ADRs, versions
```

## Applications

Eleven first-party apps plus Firefox ESR build as signed `.zaod` packages:

```bash
make apps ZAOD_KEY=store.key     # build and sign every app
make firefox ZAOD_KEY=store.key  # repackage Firefox ESR with the Google policy
make smoke                       # start every window offscreen, save screenshots
make apps-test                   # 43 application tests
```

Apps live under `apps/`, share the Fluent helpers in `apps/lib/zaodapp.py`, and use only the
Python standard library plus PySide6. Firefox is repackaged from the official Mozilla tarball with
a pinned SHA-256; the builder proves that the only added file is `distribution/policies.json`.

`repo/build-store.sh store.key` publishes a signed store index over every built package.

## Studio (optional)

`make studio` packages Zaod Studio, the editor for building `.zaod` apps from five templates
(Python+Qt, Python CLI, C/CMake, shell, web wrapper). It writes `build/out/optional/`, so the
regular store index never ships it. The developer guide is `docs/dev/studio.md`.

```bash
PYTHONPATH=studio python3 -m zaodstudio.cli templates
PYTHONPATH=studio python3 -m zaodstudio.cli new python-cli ~/src/demo --id org.example.demo
PYTHONPATH=studio python3 -m zaodstudio.cli build ~/src/demo --sign --out build/demo.zaod
```

## Package manager

`zaod` installs, verifies and runs `.zaod` packages. It is pure Python 3 with no
third-party modules, so it runs on an image that has no distro package manager.

```bash
make zaod-test          # 97 unit tests
make zaod-lint          # Ruff + ShellCheck
make sandbox-proof      # bubblewrap isolation proof
make hello              # build the reference app package

./zaod/bin/zaod key generate --out store.key --trust
./zaod/bin/zaod pack apps/hello-gui -o build/out/apps/zaod-hello-1.0.0.zaod --key store.key
./zaod/bin/zaod verify build/out/apps/zaod-hello-1.0.0.zaod
./zaod/bin/zaod repo build build/out/apps --name core --key store.key
./zaod/bin/zaod repo add core file://$PWD/build/out/apps --key store.pub
./zaod/bin/zaod repo sync
./zaod/bin/zaod search hello
./zaod/bin/zaod install org.zaod.hello
./zaod/bin/zaod run org.zaod.hello
./zaod/bin/zaod remove org.zaod.hello
```

Set `ZAOD_ROOT` to any directory to exercise the whole manager unprivileged;
that is how the test suite and the demo runs work.

Specifications: `zaod/spec/format-v1.md`, `zaod/spec/permissions.md`,
`zaod/spec/store.md`, `zaod/spec/manifest.schema.json`,
`zaod/spec/store-index.schema.json`.
