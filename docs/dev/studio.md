# Zaod Studio developer guide

Studio is the optional application for building `.zaod` programs. It scaffolds a project
from one of five templates, edits the sources, builds and signs a package, and verifies
the result. The same work is available headlessly through the `zaod-studio` command line,
which is what the automated tests use.

Studio is **not installed by default** and is **not** part of the regular store index:
`make studio` writes `build/out/optional/studio-0.9.0.zaod`, while `repo/build-store.sh`
only publishes `build/out/apps/*.zaod`.

## Project layout

A project is a directory containing `zaod.project.json`:

```json
{
  "format": 1,
  "id": "org.example.myapp",
  "name": "My App",
  "version": "0.1.0",
  "template": "python-qt",
  "entry": "payload/main.py",
  "summary": "What the app does",
  "categories": ["Utility"],
  "license": {"spdx": "MIT", "name": "MIT License"},
  "author": {"name": "You"},
  "permissions": {"network": false, "filesystem": [], "devices": ["dri"]},
  "runtimes": ["org.zaod.runtime.pyside6"]
}
```

`MANIFEST.json` is **generated** from that file on every build, so the two can never
disagree. Editing the manifest by hand is pointless: it is rewritten and normalised before
signing. No `built_at` value is written by Studio, because a timestamp would make builds
irreproducible.

Rules the project file must satisfy:

| Field | Rule |
| --- | --- |
| `format` | must be `1` |
| `id` | reverse-DNS, lowercase, at least two labels: `org.example.myapp` |
| `name`, `version` (semver), `template` | required |
| `template` | one of `python-qt`, `python-cli`, `c-cmake`, `shell`, `web-wrapper` |

## Templates

| Template | Language | Entry | Notes |
| --- | --- | --- | --- |
| `python-qt` | Python + PySide6 | `payload/main.py` | Fluent window; needs `org.zaod.runtime.pyside6` |
| `python-cli` | Python (stdlib) | `payload/main.py` | No runtimes, terminal entry |
| `c-cmake` | C + CMake | `payload/bin/app` | Studio runs `cmake`, copies the binary in, drops sources |
| `shell` | bash | `payload/main.sh` | Terminal entry, no runtimes |
| `web-wrapper` | Python + QtWebEngine | `payload/main.py` | Network permission on by default |

## Command line

```bash
export PYTHONPATH=/usr/lib/zaod-studio     # on a real system; in this repo use studio/
python3 -m zaodstudio.cli templates
python3 -m zaodstudio.cli new python-cli ~/src/hello --id org.example.hello --name "Hello"
python3 -m zaodstudio.cli build ~/src/hello --sign --out build/hello.zaod
python3 -m zaodstudio.cli verify build/hello.zaod
python3 -m zaodstudio.cli run build/hello.zaod --id org.example.hello --root ~/.zaod/devroot
```

`--sign` uses the developer key at `~/.zaod/data/org.zaod.studio/keys/developer.key`
(created on first use, mode `0600`). Trust it once with
`zaod key trust ~/.zaod/data/org.zaod.studio/keys/developer.pub` to install your own
builds without `--allow-unsigned`.

## What a build does

1. Loads and validates `zaod.project.json`.
2. Copies the project into a temporary work tree (`.git`, `build/`, `__pycache__` skipped).
3. Runs the template's build steps there (`c-cmake` runs CMake twice).
4. Assembles the package from `MANIFEST.json`, `icon.svg`, screenshots and `payload/` only,
   so C sources and build scripts never ship.
5. Validates the manifest, entry point and permissions through `zaodlib.pack.build_package`.
   A bad project fails with a precise message and **no** archive is left behind.
6. Signs with the developer key when one is given, then reports the SHA-256.

Builds are byte-reproducible: two builds of the same sources produce the same archive hash.

## Studio window

The window has a project tree, an editor with syntax highlighting for Python, C, CMake and
shell, a find bar with a match count, a build console and status line, and New / Open /
Save / Build / Run / Verify actions. It renders offscreen in CI:

```bash
make smoke            # writes build/out/screens/studio.png among the others
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `invalid app id` | Ids are reverse-DNS and lowercase; use `org.example.app` |
| `build step failed (2)` | CMake or the compiler rejected the sources; the console has the exact line |
| `entry point … is missing from the build` | The template's build steps did not produce the entry file |
| `signing key … is not trusted` | `zaod key trust` the developer public key, or install with `--allow-unsigned` |
| `bwrap: loopback: Failed RTM_NEWADDR` | The host blocks network namespaces; use `zaod run --no-sandbox` for local debugging |
