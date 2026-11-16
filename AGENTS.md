# AGENTS.md: what is built, what is left

Read this first. It is the shared status board for every agent working in
`zaodtechai-stack/zaod-os`. `PRD.md` stays the source of truth for requirements;
this file tracks **where the repository actually stands against it**, with the
command that proves each line. Update the audit log at the bottom after every run.
Work on `main` only, and never revert or rewrite another agent's phase.

## Current position

| Phase | Scope | State | Proof |
| --- | --- | --- | --- |
| 1 | Foundation, toolchain, feasibility | done | `make doctor`, `make fetch`, Ruff + ShellCheck |
| 2 | Kernel 6.18.63 with the Zaod config | partial | `python3 tests/check_kernel_config.py kernel/zaod_defconfig` (95 options) |
| 3 | Rootfs without distro package management | configs pass, artifact blocked | `python3 tests/check_rootfs_config.py` (91 checks); `make rootfs` still needs the kernel artifact and a mount-capable host |
| 4 | Boot chain and live ISO | configs pass, ISO blocked | `python3 tests/check_boot_config.py` (88 checks); `make iso` needs rootfs + initramfs |
| 5 | Plasma 6 desktop session | configs pass, session unverified | `python3 tests/check_desktop_config.py` (715 checks), `tests/test_lite_mode.py` |
| 6 | Zaod Fluent design system | done: tokens, components, icons, wallpapers, 48 screenshots, a11y pass | `python3 tests/check_design_tokens.py` (1653 checks, 60 contrast pairs, min 3.08:1), `python3 tests/check_design_drift.py`, `python3 desktop/design/tools/check_qml.py` (17 surfaces), `python3 desktop/design/tools/capture_surfaces.py --lite` (48 PNGs), `tests/test_design_tools.py` (39 tests) |
| 7 | `.zaod` format and package manager | done (one gap) | `make zaod-test` (97 tests), `make hello` |
| 8 | Core apps, Firefox ESR, Store, Control Center | built, partly unverified | `make apps` (13 packages), `make firefox`, `make store-index`, `make smoke` |
| 9 | Zaod Studio and project templates | done (window launch unverified) | `make studio-test` (16 tests); all five templates build byte-reproducibly, `verify --strict`, and install |
| 10 | Installer, OOBE, updates, release | tooling built, image blocked | `make zaod-test` incl. 9 bundle tests, `apps/oobe`, `installer/`, `make store-release`, `docs/reports/phase-10.md` |

Test totals today: 97 package-manager + 9 update-bundle + 43 application + 16 Studio = **165 tests**.

## Known gaps (in the order they block the release)

1. **Phase 3 has no artifact.** `scripts/build-rootfs.sh` now records the requested
   package set and removes apt/dpkg before packing (and re-checks the tarball), but
   the 150 MB tarball itself has never been produced here: this sandbox denies the
   chroot mounts that mmdebstrap and debootstrap need. Build it on a Docker-capable
   host. Phases 4, 5, 6 and the installer gate depend on it.
2. **Phase 2 has no committed kernel artifact.** `build/` is gitignored, so
   `uname -r` = `6.18.x-zaod` in QEMU, "compressed kernel < 15 MB", and "two clean
   builds produce the same config and module list" are still unproven by anyone
   else. The 1-vCPU sandbox measures 1.17 compile units/s, so a clean build there
   is roughly 40 minutes; record the log hashes in `docs/reports/phase-2.md` when
   it is rebuilt on a real 2-core machine.
3. **Phase 7 network isolation is unproven.** `make sandbox-proof` now exits 3 and
   prints `INCOMPLETE` on hosts that cannot create a network namespace. Run it on a
   Zaod image or any host with `CAP_NET_ADMIN` and record the result.
4. **Phase 8 Control Center is unverified on a real session.** The window paints and
   the settings backend is unit tested, but "each control changes a real system
   setting" needs a live Plasma session from Phase 5.
5. **Phase 9 window launch is unverified.** Templates build byte-reproducibly, pass
   `zaod-studio verify --strict` and install into a scratch root, but `zaod run`
   cannot start here because the sandbox denies network namespaces.
6. **No runtime package exists.** Thirteen app manifests declare
   `runtimes: ["org.zaod.runtime.pyside6"]`, but `org.zaod.runtime.pyside6` is never
   built. Install does not resolve runtimes yet, so apps install fine, but an image
   built today would have no PySide6 to run them. Build it with the phase 3 rootfs.
7. **Phase 9 install path is unverified in QEMU.** Templates build and the Studio
   suite passes; "install offline from a local repo in QEMU and launch all five
   templates" needs the Phase 3/4 image.

## How to check the repository in one pass

```bash
make doctor            # host report -> build/logs/doctor.log (never overwrites docs/)
make fetch             # kernel tarball, PGP + SHA256 (falls back to HTTPS key fetch)
make zaod-lint         # ruff + shellcheck over scripts, tests, kernel, apps
make test              # 97 + 43 + 16 tests
make apps              # 12 signed-ready .zaod packages in build/out/apps (+ firefox = 13)
make firefox           # official ESR repackaged, policy added, payload unchanged
make store-index ZAOD_KEY=...   # 14 packages, signed index in build/out/store
make store-release VERSION=1.0.0 ZAOD_KEY=...   # release dir with checksums + notes
make smoke             # every app window started offscreen, PNGs in build/out/screens
make sandbox-proof     # 0 full proof, 3 filesystem-only (no netns), 1 failed
```

## Environment limits seen so far

- 1 vCPU, no KVM, no Docker, gVisor sandbox: kernel and ISO work is slow, and
  `bwrap --unshare-all` and `debootstrap`'s chroot mounts are both denied. Use a
  real host, a Codespace with Docker, or a 2-core machine for Phases 2-6.
- Restricted networks block the PGP keyserver port, plain HTTP mirrors and
  `apt-get` over HTTP. `fetch.sh` and `build-rootfs.sh` now default to HTTPS.

## Rules for agents

1. One phase at a time, in PRD order; do not start phase N+1 before phase N has a
   report with evidence.
2. Never present a stub, placeholder or unverified claim as done. If a host cannot
   prove something, record the failure and the command that would prove it.
3. Keep `make zaod-lint` and `make test` green before pushing to `main`.
4. Evidence goes to `docs/reports/phase-N.md`; the honest host-level audit lives in
   `docs/reports/qa-phase-audit.md`.
5. Do not edit `docs/reports/phase-1.md` by hand: `make doctor` writes the log to
   `build/logs/doctor.log` on purpose.
6. Append a short entry to the audit log below after each working session.

## Audit log

### 2026-11-16: the ISO builds, boots and is published

- Workflow `iso` is green on `main` from `0975c5c` (run #11) and `dff4c18` (run #12).
  Releases `iso-11` and `iso-12` carry `zaod-os-0.4.0-x86_64.iso` (847 MB) plus
  `SHA256SUMS`; the asset is publicly downloadable and 200s on a HEAD request.
- Measured on the runner: squashfs 818 MB (zstd 19 from a 2203 MB tree), initramfs
  2.0 MB, ISO 847 MB, 108 packages, ~7 min wall clock.
- Boot evidence: the ISO mounts itself (`using boot media /dev/sr0`), unpacks the
  squashfs, stacks the tmpfs overlay and hands over to systemd, which reaches a
  `zaod login:` prompt on `ttyS0`. That closes the media-detection and module-loading
  blockers that had every earlier boot landing in the rescue shell.
- Defects fixed on the way, each of which failed a run on its own: rootfs package
  names that trixie does not ship, an old runner keyring, the initramfs module
  mapping, `CONFIG_DEVTMPFS_MOUNT` treated as mandatory, `modules.dep` packed before
  `depmod` ran, a `tar | grep -q` pipeline reporting SIGPIPE as a missing file,
  `/sbin/modprobe` absent from the image, `build/out` owned by root when the checksum
  step ran, and media detection that trusted an iso9660 label busybox cannot read.
- Still unverified here: GRUB's graphical hand-off and the Plasma 6 session. In this
  1-vCPU sandbox every ISO, including the published `iso-11`, freezes at the El Torito
  hand-off under QEMU, so the graphics check needs a machine with KVM or a real GPU.
  Phase 5 and the phase 10 acceptance run stay open until then.

### 2026-11-15: QA audit of phases 1, 2, 7 (1 vCPU sandbox)

- Phase 1: `make doctor` clean; `sha256sums.asc` signature from the kernel.org
  autosigner verified; tarball hash `81764a54...` matches the signed manifest and
  `docs/versions.md`.
- Phase 2: config validator passes all 95 required options; build throughput
  measured at 1.17 units/s on one vCPU (=> 36-50 min clean build, 20-28 min on two
  cores, 11-16 min on four); no artifact kept.
- Phase 7: tampered payload rejected with the exact sha256 mismatch and nothing
  installed; unsigned package refused without `--allow-unsigned`; upgrade keeps the
  previous version for rollback; store index, sync, search, update and gc behave.
- Fixes merged to `main`: `scripts/fetch.sh` HTTPS key fallback and empty-checksum
  guard, `make doctor` no longer overwrites `docs/reports/phase-1.md`,
  `tests/sandbox-proof.sh` exit 3 plus `INCOMPLETE` verdict instead of a false green,
  `scripts/build-rootfs.sh` mmdebstrap/debootstrap fallback with an early privilege
  and mount preflight, `make store-index` now depends on `apps` and `firefox`.
- Rootfs evidence still missing: this sandbox denies the chroot mounts debootstrap
  needs, so the 150 MB trixie tarball must be produced on a Docker-capable host.

### 2026-11-15: repository review, six more defects fixed

- `apps/oobe` manifest used `kind: "system"`, which the validator does not accept, so
  `make apps` would have died on the setup package. Now `kind: "app"`; all 14 packages
  build.
- `repo/build-store.sh` published the first-boot app and Studio, and never published the
  store's public key, while the installer expected `keys/store.pub`. The index now skips
  `oobe-*` and `studio-*` and writes `build/out/store/keys/store.pub`.
- `scripts/release.sh` read the store from `repo/build/` and its directory reset removed
  the `store/` subdirectory, so a release run failed on `cp`. Both fixed; a store-only
  release now verifies end to end (SHA256SUMS plus `release.json.sig`).
- `apps/build-all.sh` never cleaned `build/out/apps`, so packages for removed apps kept
  being published. It now cleans the output directory too.
- Rebuilt state: 14 packages, 12-package signed index, release directory for 1.1.0 with
  checksums and signature. README phase table now lists all ten phases with honest
  states, and the missing `org.zaod.runtime.pyside6` package is recorded as a gap.

### 2026-11-15: phase 10 tooling, plus repairs to the phase 3/QA push

- Phase 10 landed on `main`: `zaodlib/update.py` with the `.zaodbundle` format
  (bundle.json + CHECKSUMS + Ed25519 SIGNATURE + packages), `zaod bundle
  create/verify/apply/rollback`, 9 bundle tests, `apps/oobe` first-boot setup with
  privacy switches off by default, `installer/` Calamares settings and branding,
  `scripts/release.sh` (+ `make release`/`store-release`) emitting SHA256SUMS,
  release.json(.sig), RELEASE-NOTES.md and SOURCE-OFFER.txt, and the docs
  (`docs/user/guide.md`, `docs/release.md`, `docs/licenses.md`).
- Real bundle run: shell demo 0.1.0 -> 0.2.0 applied and rolled back to 0.1.0 with
  the snapshot kept in `/var/lib/zaod/updates/<stamp>-<target>/`.
- Repairs to the previous push: `scripts/fetch.sh`, `scripts/build-rootfs.sh` and
  `tests/sandbox-proof.sh` had lost their executable bit (restored); the rootfs
  `--include` list was built with line-wrap spaces inside the names, so a bootstrap
  would have failed (now a clean comma list); and the rootfs still shipped apt and
  dpkg, contradicting the phase 3 requirement, so the script now records
  `build/out/rootfs-packages.txt`, strips package management from both the Docker
  and bootstrap paths, and refuses a tarball that still matches apt/dpkg.
- Still blocked here: every QEMU/ISO item (no image), the Phase 2 kernel artifact,
  the Phase 7 network half of the sandbox proof, and the owner's hardware matrix.

### 2026-11-15: first pass over phases 8 and 9 (after the store/Studio commits)

- `make apps` builds 13 packages, `make firefox` produces a 101.6 MiB package with
  all 53 upstream files unchanged plus one `policies.json`, `make store-index` signs
  an index over 14 packages, and `make smoke` starts and paints all 12 app windows.
- `make apps-test` 43 tests and `make studio-test` 16 tests pass.
- Not verified here: Store install/update/remove against a hosted repo on a real
  image, Firefox three-tab behaviour on 2 GB, template install in QEMU, Studio
  absent-by-default on the shipped image.

### 2026-11-15: phases 8 and 9 exercised end to end (second pass)

- Store round trip on a scratch `ZAOD_ROOT`: `repo add file://... --key`, `repo sync`
  cached 14 packages, `search`, then `install org.zaod.notes` resolved the signed
  index and recorded `source: repo:core`; `remove` left nothing behind.
- Phase 9: all five templates (`python-qt`, `python-cli`, `c-cmake`, `shell`,
  `web-wrapper`) scaffold, build twice to the **same sha256**, pass
  `zaod-studio verify --strict` with a trusted developer key, and install.
- **Bug fixed: every Studio-built package was uninstallable.** `zaodstudio` stamped
  `min_os` 0.9.0 while the platform is 0.7.0, so `zaod verify`/`install` rejected all
  Studio output with a `CompatibilityError`. The default now comes from
  `zaodlib.DEFAULT_OS_VERSION`; a project can still raise it in `zaod.project.json`.
- **Bug fixed: `zaod-studio` leaked Python tracebacks** for package-level failures.
  It now prints one `zaod-studio: error: ...` line and returns the error's exit code.
- Still open here: `zaod run` cannot execute (bwrap cannot create a network namespace
  in this sandbox), so window launch stays a real-image check.

### 2026-11-15: Phase 10 store release made usable (three release.sh bugs)

- `make store-release VERSION=x ZAOD_KEY=...` never worked: `find -delete` removed the
  freshly created `store/` directory, so every copy failed. Fixed by recreating it.
- The signed index was never shipped: the loop copied `index.sig` and
  `repo/build/keys/store.pub`, neither of which exists, so a release shipped packages
  with no index. It now re-signs the index with the release key, copies
  `index.json` + `index.json.sig` (failing loudly if absent) and ships every
  package-signing public key under `store/keys/`.
- Verified end to end on a fresh root: trust `store/keys/*.pub`, `repo add official`,
  `repo sync` -> 14 packages, `install org.zaod.calculator` -> `source: repo:official`.
  Release output: 20 artifacts.
- Still blocked for Phase 10: the ISO side (`make release` without `--store-only`),
  OOBE and the installer need the Phase 3/4 image.

### 2026-11-16: phases 3-6 landed; configs verified, artifacts still gated on the kernel

- New on main: Phase 3 rootfs pipeline (`rootfs/`, curated package set, shipped config),
  Phase 4 boot chain (`boot/grub`, `initramfs`, `plymouth`, USB writer), Phase 5 session
  and Phase 6 design system (`desktop/`).
- Verified here: `check_rootfs_config` 91/91, `check_boot_config` 88/88,
  `check_design_tokens` 532/532 with 42 contrast pairs, `check_desktop_config` 715/715,
  `test_design_tools` 38 tests, plus the existing 106 + 43 + 16 suites. Lint clean.
- Design note: the lowest contrast pair is 3.13:1. That clears AA for large text and UI
  components but not for small body text, so a designer should confirm where it is used.
- `make rootfs-check` now fails with "Phase 2 input is missing: build/out/kernel/vmlinuz",
  so the kernel build is the single gate for phases 3, 4 and the ISO items in 10.
  A `make kernel` run was started on this host (1 core, firmware fetch included).

### 2026-11-16: Phase 6 design system audit

Found that the design system was largely non-functional while every gate was green:
`ZaodTheme.qml` did not compile (generator emitted `readonly property` inside the palette
object literals), `ZaodButton` overrode the final `hovered` property, type names were
`typeBodysm`/`typeBodystrong`, and `scrim` was emitted opaque so the shell panels blacked out
the desktop. All fixed, plus: token-driven `layout`/`opacity`/`focus`/`lite` blocks,
`tokens_to_python.py` for the 13 Python apps, border tokens retuned to clear 3:1 on every
surface, 39 nav glyphs and 15 app tiles, a flat wallpaper tier, and two new gates
(`check_design_drift.py`, `check_qml.py`). 48 screenshots at 1366x768 in
`docs/reports/phase-6-screenshots/`. Report: `docs/reports/phase-6.md`.
Calendar and Files still have no app package; Firefox and every image-level item stay
blocked until Phases 3-5 produce a bootable rootfs/ISO.
