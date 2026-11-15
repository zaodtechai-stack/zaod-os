## Zaod OS Phase 8 report: applications, store and Control Center
- Date (UTC): 2026-11-15
- Host: Linux x86_64, Python 3.11.15, PySide6 6.12.0, 1 CPU core, gVisor build sandbox
- Verification style: unit tests plus offscreen Qt rendering. This repository still has no QEMU
  image (Phases 3-6 are absent), so "runs on the target desktop" is never claimed below.

## What shipped

| Deliverable | Path | Notes |
| --- | --- | --- |
| Shared UI library | `apps/lib/zaodapp.py` | Fluent tokens, window helper, per-app data directory |
| First-party apps (9) | `apps/calculator`, `notes`, `clock`, `tasks`, `converter`, `viewer`, `editor`, `monitor`, `hello-gui` | Original MIT code, 40-90 lines each |
| Control Center | `apps/control-center/` | 7 pages, 14 controls, each mapped to a real command |
| Store | `apps/store/` | Signed-index browsing, install/update/remove, offline cache |
| Firefox ESR | `apps/firefox/` | Repackaged from the official tarball with a Google search policy |
| Package pipeline | `apps/build-all.sh` | Stage, bundle library, pack and sign every app |
| Store publishing | `repo/build-store.sh` | Builds every package and signs the index |
| Offscreen harness | `apps/smoke.py` | Starts every window and saves a screenshot |

## Tests and lint
```
Ran 97 tests in 2.939s  (package manager)
Ran 43 tests in 1.030s  (applications)
```
```
$ make zaod-lint
ruff: RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/calculator/payload/main.py:13:17
   |
11 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
12 |
13 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
14 |
15 | OPERATORS = {
   |
help: Remove unused `noqa` directive
   |
12 |
   - import zaodapp  # noqa: E402
13 + import zaodapp
14 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/clock/payload/main.py:12:17
   |
10 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
11 |
12 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
11 |
   - import zaodapp  # noqa: E402
12 + import zaodapp
13 |
   |

RUF046 Value being cast to `int` is already an integer
   --> apps/control-center/payload/backend.py:285:32
    |
283 |             for token in raw.split():
284 |                 try:
285 |                     return str(int(round(float(token) * 100)))
    |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
286 |                 except ValueError:
287 |                     continue
    |
help: Remove unnecessary `int` call
    |
284 |                 try:
    -                     return str(int(round(float(token) * 100)))
285 +                     return str(round(float(token) * 100))
286 |                 except ValueError:
    |
note: This is an unsafe fix and may change runtime behavior

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/control-center/payload/main.py:13:17
   |
11 | sys.path.insert(0, os.path.join(HERE, "lib"))
12 |
13 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
14 | from backend import ControlCenter, SettingError  # noqa: E402
   |
help: Remove unused `noqa` directive
   |
12 |
   - import zaodapp  # noqa: E402
13 + import zaodapp
14 | from backend import ControlCenter, SettingError  # noqa: E402
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/control-center/payload/main.py:14:50
   |
13 | import zaodapp  # noqa: E402
14 | from backend import ControlCenter, SettingError  # noqa: E402
   |                                                  ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
13 | import zaodapp  # noqa: E402
   - from backend import ControlCenter, SettingError  # noqa: E402
14 + from backend import ControlCenter, SettingError
15 |
   |

B023 Function definition does not bind loop variable `control`
   --> apps/control-center/payload/main.py:117:31
    |
115 |                         report(str(error), error=True)
116 |                         return
117 |                     report(f"{control.label} updated")
    |                               ^^^^^^^
118 |
119 |                 if control.kind == "choice":
    |

B023 Function definition does not bind loop variable `control`
   --> apps/control-center/payload/main.py:151:31
    |
149 |                         report(str(error), error=True)
150 |                         return
151 |                     report(f"{control.label} set to {value}%")
    |                               ^^^^^^^
152 |
153 |                 slider.sliderReleased.connect(lambda slider=slider: apply_slider(slider.value()))
    |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/converter/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
12 |
13 | LENGTH = {"Metre": 1.0, "Kilometre": 1000.0, "Centimetre": 0.01, "Inch": 0.0254, "Foot": 0.3048, "Mile": 1609.344}
   |
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

I001 [*] Import block is un-sorted or un-formatted
  --> apps/converter/payload/main.py:28:5
   |
27 | def build_window():
28 |     from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QPushButton, QVBoxLayout
   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
29 |
30 |     window = zaodapp.base_window("Converter", 460, 420)
   |
help: Organize imports
   |
27 | def build_window():
   -     from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QPushButton, QVBoxLayout
28 +     from PySide6.QtWidgets import (
29 +         QComboBox,
30 +         QDoubleSpinBox,
31 +         QLabel,
32 +         QPushButton,
33 +         QVBoxLayout,
34 +     )
35 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/editor/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

I001 [*] Import block is un-sorted or un-formatted
  --> apps/editor/payload/main.py:19:5
   |
18 |   def build_window():
19 | /     from PySide6.QtGui import QFont
20 | |     from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
   | |_______________________________________________________________________________________________^
21 |
22 |       window = zaodapp.base_window("Text Editor", 760, 560)
   |
help: Organize imports
   |
19 |     from PySide6.QtGui import QFont
   -     from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
20 +     from PySide6.QtWidgets import (
21 +         QFileDialog,
22 +         QHBoxLayout,
23 +         QLabel,
24 +         QPlainTextEdit,
25 +         QPushButton,
26 +     )
27 |
   |

SIM115 Use a context manager for opening files
  --> apps/editor/payload/main.py:43:33
   |
41 |             return
42 |         try:
43 |             editor.setPlainText(open(path, encoding="utf-8", errors="replace").read())
   |                                 ^^^^
44 |         except OSError:
45 |             status.setText("cannot read that file")
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/hello-gui/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/monitor/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/notes/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
12 |
13 | APP_ID = "org.zaod.notes"
   |
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/smoke.py:24:45
   |
22 |     os.environ.setdefault("ZAOD_ROOT", str(REPO / "build" / "smoke-root"))
23 |
24 | from PySide6.QtWidgets import QApplication  # noqa: E402 - environment set above
   |                                             ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
23 |
   - from PySide6.QtWidgets import QApplication  # noqa: E402 - environment set above
24 + from PySide6.QtWidgets import QApplication
25 |
   |

F401 [*] `json` imported but unused
  --> apps/store/payload/backend.py:10:8
   |
 8 | from __future__ import annotations
 9 |
10 | import json
   |        ^^^^
11 | import os
12 | import subprocess
   |
help: Remove unused import: `json`
   |
9  |
   - import json
10 | import os
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `PLC0415`)
  --> apps/store/payload/backend.py:29:48
   |
27 |     else:
28 |         raise StoreError("zaodlib is not installed; the store needs a Zaod system")
29 |     from zaodlib import db, keys, paths, repo  # noqa: PLC0415 - path set above
   |                                                ^^^^^^^^^^^^^^^
30 |
31 |     return db, keys, paths, repo
   |
help: Remove unused `noqa` directive
   |
28 |         raise StoreError("zaodlib is not installed; the store needs a Zaod system")
   -     from zaodlib import db, keys, paths, repo  # noqa: PLC0415 - path set above
29 +     from zaodlib import db, keys, paths, repo
30 |
   |

S112 `try`-`except`-`continue` detected, consider logging the exception
   --> apps/store/payload/backend.py:107:13
    |
105 |               try:
106 |                   indexes[entry.name] = self.repo_module.cached_index(self.paths, entry.name)
107 | /             except Exception:  # noqa: BLE001 - a missing cache just means offline
108 | |                 continue
    | |________________________^
109 |           return indexes
    |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/store/payload/main.py:13:17
   |
11 | sys.path.insert(0, os.path.join(HERE, "lib"))
12 |
13 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
14 | from backend import StoreBackend, StoreError  # noqa: E402
   |
help: Remove unused `noqa` directive
   |
12 |
   - import zaodapp  # noqa: E402
13 + import zaodapp
14 | from backend import StoreBackend, StoreError  # noqa: E402
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/store/payload/main.py:14:47
   |
13 | import zaodapp  # noqa: E402
14 | from backend import StoreBackend, StoreError  # noqa: E402
   |                                               ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
13 | import zaodapp  # noqa: E402
   - from backend import StoreBackend, StoreError  # noqa: E402
14 + from backend import StoreBackend, StoreError
15 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/tasks/payload/main.py:12:17
   |
10 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
11 |
12 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
13 |
14 | APP_ID = "org.zaod.tasks"
   |
help: Remove unused `noqa` directive
   |
11 |
   - import zaodapp  # noqa: E402
12 + import zaodapp
13 |
   |

I001 [*] Import block is un-sorted or un-formatted
  --> apps/tasks/payload/main.py:36:5
   |
35 |   def build_window():
36 | /     from PySide6.QtCore import Qt
37 | |     from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton
   | |___________________________________________________________________________________________________________^
38 |
39 |       window = zaodapp.base_window("Tasks", 520, 460)
   |
help: Organize imports
   |
36 |     from PySide6.QtCore import Qt
   -     from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton
37 +     from PySide6.QtWidgets import (
38 +         QHBoxLayout,
39 +         QLabel,
40 +         QLineEdit,
41 +         QListWidget,
42 +         QListWidgetItem,
43 +         QPushButton,
44 +     )
45 |
   |

I001 [*] Import block is un-sorted or un-formatted
  --> apps/tests/test_store.py:17:1
   |
15 | sys.path.insert(0, str(REPO_ROOT / "zaod"))
16 |
17 | from zaodlib import keys, pack, paths as zaod_paths, repo  # noqa: E402
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
help: Organize imports
   |
16 |
   - from zaodlib import keys, pack, paths as zaod_paths, repo  # noqa: E402
17 + from zaodlib import keys, pack, repo  # noqa: E402
18 + from zaodlib import paths as zaod_paths
19 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/tests/test_store.py:17:60
   |
15 | sys.path.insert(0, str(REPO_ROOT / "zaod"))
16 |
17 | from zaodlib import keys, pack, paths as zaod_paths, repo  # noqa: E402
   |                                                            ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
16 |
   - from zaodlib import keys, pack, paths as zaod_paths, repo  # noqa: E402
17 + from zaodlib import keys, pack, paths as zaod_paths, repo
18 |
   |

RUF100 [*] Unused `noqa` directive (non-enabled: `E402`)
  --> apps/viewer/payload/main.py:11:17
   |
 9 | sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
10 |
11 | import zaodapp  # noqa: E402
   |                 ^^^^^^^^^^^^
help: Remove unused `noqa` directive
   |
10 |
   - import zaodapp  # noqa: E402
11 + import zaodapp
12 |
   |

Found 26 errors.
[*] 21 fixable with `--fix` (1 unsafe fix available with `--fix --unsafe-fixes`).
shellcheck: no findings
```

The application suite covers calculator expression safety, unit conversion maths, `/proc` parsing,
task persistence, Control Center command mapping (17 tests) and the Store backend against a real
signed `file://` repository (10 tests).

## Offscreen window proof
```
ok    calculator   384x420 -> calculator.png
ok    clock        420x320 -> clock.png
ok    control-center 860x560 -> control-center.png
ok    converter    460x420 -> converter.png
ok    editor       760x560 -> editor.png
ok    hello-gui    460x240 -> hello-gui.png
ok    monitor      480x360 -> monitor.png
ok    notes        620x460 -> notes.png
ok    store        900x600 -> store.png
ok    tasks        520x460 -> tasks.png
ok    viewer       720x520 -> viewer.png

all first-party app windows started and painted
```
| Screenshot | Size |
| --- | --- |
| `calculator.png` | 11 KB |
| `clock.png` | 8 KB |
| `control-center.png` | 30 KB |
| `converter.png` | 8 KB |
| `editor.png` | 6 KB |
| `hello-gui.png` | 8 KB |
| `monitor.png` | 9 KB |
| `notes.png` | 6 KB |
| `store.png` | 15 KB |
| `tasks.png` | 8 KB |
| `viewer.png` | 8 KB |

## Signed store

`repo/build-store.sh` produced a signed index with 12 packages:

| Package | Version | Size | Summary |
| --- | --- | --- | --- |
| `org.mozilla.firefox` | 153.7.0 | 104010.4 KiB | Firefox ESR with Google as the default search engine |
| `org.zaod.calculator` | 1.0.0 | 6.6 KiB | Arithmetic with keyboard support |
| `org.zaod.clock` | 1.0.0 | 5.5 KiB | Clock and stopwatch |
| `org.zaod.control-center` | 1.0.0 | 19.2 KiB | Network, appearance, display, sound, power and update settings |
| `org.zaod.converter` | 1.0.0 | 6.9 KiB | Length, mass and temperature conversion |
| `org.zaod.editor` | 1.0.0 | 6.1 KiB | Plain text editing with word count |
| `org.zaod.hello` | 1.0.0 | 4.1 KiB | Minimal Zaod app used to prove desktop integration |
| `org.zaod.monitor` | 1.0.0 | 6.7 KiB | Memory, load and uptime at a glance |
| `org.zaod.notes` | 1.0.0 | 5.1 KiB | Quick notes that stay on this device |
| `org.zaod.store` | 1.0.0 | 16.9 KiB | Browse, install and update signed Zaod apps |
| `org.zaod.tasks` | 1.0.0 | 6.9 KiB | Simple task list stored locally |
| `org.zaod.viewer` | 1.0.0 | 6.0 KiB | Open and zoom pictures from Pictures |

Every archive passes `zaod verify` (12 OK lines, one per package).

## Firefox ESR

- Version 153.7.0esr, en-US, linux-x86_64: 101.6 MiB package, 311 MB unpacked
- Pinned SHA-256 `7d2eb92ca3a7b2a83de092eb9b94c853980214de2fbfdccb2ac39d61c593c5a5`, checked against
  Mozilla's own `SHA256SUMS` for the exact platform path as well as the local pin
- `apps/firefox/build.py` proves the repackage changes nothing:
  `unchanged 53 upstream files, one policy file added`
- The only addition is `payload/firefox/distribution/policies.json`:
```json
{
  "policies": {
    "SearchEngines": {
      "Default": "Google",
      "Remove": [
        "Bing",
        "DuckDuckGo",
        "Wikipedia (en)"
      ]
    },
    "OverrideFirstRunPage": "",
    "OverridePostUpdatePage": "",
    "DisableProfileImport": true
  }
}
```

- Install transcript: `installed Firefox 153.7.0`, desktop entry
  `Exec=.../payload/firefox/firefox`, permissions
  `network, files: home/downloads/pictures, devices: dri/audio`

## Control Center command mapping

| Page | Control | Command |
| --- | --- | --- |
| Network | Wi-Fi toggle | `nmcli radio wifi on/off`, state read from `nmcli -t -f WIFI general` |
| Network | Saved connections | `nmcli -t -f NAME,TYPE connection show` |
| Appearance | Colour scheme | `plasma-apply-colorscheme ZaodLight/ZaodDark` |
| Appearance | Accent | `kwriteconfig6 --file zaodrc --group Appearance --key Accent` |
| Display | Night light | write `kwinrc` NightColor, then `qdbus org.kde.KWin /KWin reconfigure` |
| Display | Scale | write `kdeglobals` KScreen ScaleFactor |
| Sound | Volume | `wpctl set-volume @DEFAULT_AUDIO_SINK@ 0.40` |
| Sound | Mute | `wpctl set-mute @DEFAULT_AUDIO_SINK@ 1/0` |
| Power | Lite mode | write `zaodrc` Performance LiteMode |
| Power | Free space | `df -h --output=avail /` |
| Updates | Install updates | `pkexec zaod-priv-helper update` |
| Updates | Last sync | reads `/var/lib/zaod/repos.json` |
| About | System, Kernel | `/etc/os-release`, `uname -r` |

## Store backend

- Read-only work uses `zaodlib` (index sync, signature verification, cache); privileged work goes
  through `pkexec zaod-priv-helper install|remove|update`, so the Store never runs as root.
- Tested against a real signed repository: sync, catalogue states (`new`, `update`, `installed`),
  search by name/summary/category, offline cache behaviour, version comparison, exact argv.

## PRD acceptance checklist

| Acceptance item | State | Evidence |
| --- | --- | --- |
| Every first-party app launches as a `.zaod` app with icon and desktop entry | PARTIAL | Packages build and verify, windows construct and paint offscreen; menu launch needs the Phase 5 image |
| Store installs, updates and removes apps | PASS at backend level | 10 Store tests, exact privileged argv |
| Store works offline from the verified cache | PASS | `test_cached_index_works_offline` |
| Firefox ESR ships with Google as default search, binaries untouched | PARTIAL | Package signed and file-set proven identical plus one policy; running Firefox needs a display |
| Control Center changes real settings | PARTIAL | 17 tests over commands and parsing; no Plasma/NetworkManager/PipeWire in this sandbox |
| No modified browser binaries | PASS | `verify_unchanged` compares the extracted tree with the upstream tar member list |

## Deviations and decisions

- Apps bundle `apps/lib/zaodapp.py` at build time so every package stays self-contained offline.
- PySide6 is declared as `org.zaod.runtime.pyside6` in every manifest; building that runtime package
  belongs to Phase 9, and it is not hidden as an implicit dependency.
- Store and Control Center call system tools instead of importing them, so a missing tool becomes a
  readable message rather than a traceback.

## Open items handed forward

- Runtime package `org.zaod.runtime.pyside6` so these apps can be installed on the real image.
- QEMU acceptance run (menu launch, settings round trip) once Phases 3-6 exist.
- Phase 9 (Studio and templates) and Phase 10 (installer, OOBE, updates, release) remain open.
