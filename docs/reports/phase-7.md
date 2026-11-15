## Zaod OS Phase 7 report: `.zaod` format and package manager

- Date (UTC): 2026-11-15
- Version: 0.7.0
- Host: Linux x86_64, Python 3.11.15, 1 CPU core, gVisor-based build sandbox
- zstd backend used: system `zstd` binary (libzstd and the `zstandard` module are fallbacks)
- Kernel and QEMU are **not** used by this phase: everything here runs unprivileged with `ZAOD_ROOT` pointed at a scratch directory.

## Deliverables

| Path | Contents |
| --- | --- |
| `zaod/spec/format-v1.md` | `.zaod` v1 archive, manifest, CHECKSUMS, SIGNATURE, install pipeline |
| `zaod/spec/manifest.schema.json` | Manifest JSON Schema; unknown fields rejected |
| `zaod/spec/permissions.md` | Permission model and its bubblewrap mapping |
| `zaod/spec/store.md` | Signed store index format and client behaviour |
| `zaod/spec/store-index.schema.json` | Store index JSON Schema |
| `zaod/zaodlib/ed25519.py` | RFC 8032 Ed25519 in pure Python (validated against the RFC vectors) |
| `zaod/zaodlib/` | `manifest`, `schema`, `verify`, `archive`, `keys`, `db`, `pack`, `install`, `desktop`, `sandbox`, `repo`, `cli` |
| `zaod/bin/zaod` | CLI: install, remove, list, info, verify, update, search, pack, sign, run, repo, key, gc |
| `zaod/bin/zaod-priv-helper` | Root helper behind pkexec/sudo with an allowlist of package operations |
| `zaod/tests/` | 97 unit tests in 10 modules |
| `apps/hello-gui/` | Reference app (PySide6) plus `build.sh`, packaged by `make hello` |
| `tests/sandbox-proof.sh` | Runtime isolation proof |

## Test and lint evidence

```
$ make zaod-test
Ran 97 tests in 2.9s
OK

$ make zaod-lint
ruff check .          All checks passed!
shellcheck *.sh       no findings
```

Per-module test counts:

```
test_install   17   test_manifest  13   test_repo     11   test_verify   10
test_sandbox   10   test_cli        9   test_schema    8   test_keys      7
test_ed25519    7   test_archive    5
```

The suite covers the RFC 8032 signature vectors, manifest schema rejection paths,
archive traversal and absolute-symlink rejection, checksum/signature tampering,
transactional install rollback, downgrade refusal, desktop entry creation and
removal, MIME association registration, sandbox argument construction, signed
store index verification and the full CLI round trip.

## Package build

```
$ make hello ZAOD_KEY=build/out/apps/dev.key
built build/out/apps/zaod-hello-1.0.0.zaod (1.7 KiB, 3 files)
  id: org.zaod.hello 1.0.0
  sha256: 168d1b4b3373d285a82bcb6f150ca99811ec7e7fbe6dcea0485044311eab7cf0
  signed: yes
```

Pack time 0.13 s for the reference app. zstd level 19 is the default; the CLI
exposes `--level`.

## Install, inspect and remove transcript

```
$ export ZAOD_ROOT=$PWD/build/demo-root
$ zaod key generate --out build/out/apps/dev.key --trust
private key: build/out/apps/dev.key (keep it offline)
public key:  456931f68f8cfe21
trusted in .../etc/zaod/keys
$ zaod install build/out/apps/zaod-hello-1.0.0.zaod
installed Hello 1.0.0 (org.zaod.hello)
  files: 3, source: local
  permissions: device: dri
$ cat $ZAOD_ROOT/usr/share/applications/org.zaod.hello.desktop
[Desktop Entry]
Type=Application
Name=Hello
Exec=<root>/zaod/apps/org.zaod.hello/current/payload/main.py
Icon=<root>/zaod/apps/org.zaod.hello/current/icon.svg
Terminal=false
Categories=Utility;
X-Zaod-AppId=org.zaod.hello
X-Zaod-Version=1.0.0
$ zaod info org.zaod.hello
id:            org.zaod.hello
version:       1.0.0
key_id:        456931f68f8cfe21
license:       MIT
permissions:   device: dri
$ zaod remove org.zaod.hello
removed org.zaod.hello 1.0.0
$ zaod list
no apps installed
```

## Runtime sandbox proof

`tests/sandbox-proof.sh` builds two packages with the same payload: one without
the network permission, one with it, installs both and runs them.

```
NOTE: this host cannot create a network namespace; the network line below is
      shown for the filesystem-only probe. Run on a Zaod system for the full proof.

=== zaod run org.zaod.probe-nonet (no network permission) ===
uid=0
host-hostname=modal
host-etc-shadow=hidden
host-home=hidden
network=reachable

=== zaod run org.zaod.probe-net (network permission) ===
uid=0
host-hostname=modal
host-etc-shadow=hidden
host-home=hidden
network=reachable
```

What this run proves on this host: the sandbox hides `/etc/shadow`, hides the
host home directory and only exposes the app's own data directory as `HOME`.

What it could **not** prove here: network isolation. This build sandbox runs
under gVisor, where `unshare(CLONE_NEWNET)` is denied and the container has no
`CAP_NET_ADMIN`, so `bwrap --unshare-all` fails with
`bwrap: loopback: Failed RTM_NEWADDR: No such file or directory`. The proof
script detects that case, says so in its output, and re-runs the filesystem
probe with `--share-net` so the rest of the isolation still gets exercised.
Network isolation is asserted at the plan level by the unit tests
(`--share-net` present only with the permission). The live proof must run on a
Zaod system or any host that grants namespace creation.

## PRD acceptance checklist

| Acceptance item | State | Evidence |
| --- | --- | --- |
| Test suite passes | PASS | 97 tests, 0 failures |
| Tampered payload rejected and not installed | PASS | `test_tampered_package_leaves_no_install`, `test_tampered_payload_rejected` |
| `hello-gui` desktop entry created, uninstall removes every file | PASS for the desktop entry and file removal (transcript above). Launching the window is **not** verified: this host has no PySide6/Qt and no Zaod image | install/remove transcript |
| No-network sandbox proven | PARTIAL | Plan-level assertions pass; runtime network-namespace proof blocked by the host (see above) |
| Interrupted update preserves the previous install | PASS | `test_interrupted_update_preserves_previous_install` (install aborts on a database failure, `current` still points at 1.0.0, no 1.1.0 directory left) |
| >= 40 tests | PASS | 97 tests |

## Design decisions

- **Ed25519 is vendored.** The target image has no `cryptography` or `pynacl`, so
  `zaod/zaodlib/ed25519.py` implements RFC 8032 in standard-library Python and is
  checked against the RFC test vectors.
- **SIGNATURE is a small JSON document** (`format`, `key_id`, `sig`, `signed`)
  over `MANIFEST.json || 0x0A || CHECKSUMS`, so the key that produced it is
  explicit and a missing or unknown key is reported precisely.
- **The zstd backend is layered**: `zstd` binary, then the `zstandard` module,
  then `libzstd` via `ctypes`. A frame without a content size needs the binary.
- **Installation is transactional on one filesystem**: extract to
  `/zaod/apps/.staging-*`, verify, atomic rename, strip write bits, swap the
  `current` symlink, then commit the database row; every failure path restores
  the previous symlink and deletes the new directory.
- **`ZAOD_ROOT`** relocates every path, which is what makes the whole manager
  testable unprivileged and reproducible in CI.
- **Privilege separation**: `zaod` re-executes itself through
  `zaod-priv-helper` under `pkexec`/`sudo` for system operations; the helper
  re-verifies signatures against root-owned trusted keys, so a caller cannot
  skip verification by passing different flags.

## Open items handed to the next phases

- Phases 3-6 (rootfs, boot chain, Plasma session, design system) are not present
  in this repository, so the following must run once that image exists:
  launching `hello-gui` through the Plasma launcher, the real `/etc/xdg/mimeapps.list`
  default association, and the network-namespace half of the sandbox proof.
- A Plasma shell widget for "install app" (`zaod install <file>` from Dolphin) is
  part of the Phase 6/8 desktop integration.
- `zaod update` currently trusts the store index ordering; a per-app channel or
  pinning policy is deferred to the update work in Phase 10.
