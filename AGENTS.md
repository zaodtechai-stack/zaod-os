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
| 2 | Kernel 6.18.63 with the Zaod config | built by the release pipeline, which the image consumes | `python3 tests/check_kernel_config.py kernel/zaod_defconfig` (95 options); `kernel` job of `.github/workflows/iso.yml` |
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

### 2026-11-16: the image ships the Zaod kernel, not a distribution kernel

- The release pipeline now compiles Linux 6.18.63 from the pinned kernel.org archive with
  `kernel/zaod_defconfig` in its own `kernel` job, uploads `vmlinuz`, `System.map`, `config`,
  `modules.tar.gz`, `modules.list` and `firmware.tar.xz`, and the image job consumes that
  artifact. `actions/cache` keyed on the config and build scripts means an ISO-only change
  reuses the previous compile.
- The Debian fallback is gone: `linux-image-amd64` left `rootfs/packages.list`, and
  `scripts/build-rootfs.sh` now fails with an actionable message instead of quietly building
  an image around the archive's kernel. The image job also asserts
  `build/logs/rootfs-report.txt` names a `6.18.*-zaod` kernel before it publishes.
- Released images built before this change carried `linux-image-amd64`; `iso-15` and earlier
  must not be described as running the Zaod kernel.

### 2026-11-16: iso-23 verified, and the panic photo identified

- `iso-23` (kernel 6.18.63-zaod, 1,108,705,280 bytes,
  sha256 `b1f3f66c5fd07747e143d5246a61ecba28b34cb8c47e1e588ede8dda66ecea26`) was downloaded from
  the release and checked against the published digest before being booted.
- Booted from CD: `using boot media /dev/sr0`, squashfs mounted, `kernel 6.18.63-zaod`,
  reached `zaod login`. No panic, and no oops in the network path after the RX fix.
- Booted as a raw USB-style disk under UEFI: `using boot media /dev/sda`, squashfs mounted,
  reached `zaod login`. Legacy BIOS boot of the same raw image stalls in GRUB under SeaBIOS
  with TCG, which the CD and UEFI paths do not, so it is an emulation limit rather than a bad
  boot image.
- The kernel panic reported on real hardware (`Attempted to kill init! exitcode=0x00000100`,
  `PID: 1 Comm: init`, kernel `6.12.107+deb13-amd64`, media-scan wording `(1/30)`) comes from
  an image built before `46b4c93`: a distribution kernel plus the init that could still exit.
  `iso-21` and later carry 6.18.63-zaod and a PID 1 that reopens its rescue shell instead of
  exiting, so that panic cannot recur.

### 2026-11-17: PID 1 is now a supervisor, because the panic was self-inflicted

- The panic reported on real hardware against the new image was
  `Attempted to kill init! exitcode=0x00000100`, `PID: 1 Comm: init`, kernel
  `6.18.63-zaod` on `GOOGLE Enguarde` (a Chromebook). Exit status 0x100 is 1: the
  boot script was PID 1, it enabled `set -e`, and one unguarded command ending the
  shell ended the machine.
- `boot/initramfs/init` is now a supervisor that never exits. It mounts the pseudo
  filesystems, runs the boot logic as a child, reports the child's exit status, and
  only `exec`s `switch_root` after the child has written `boot-ready` and
  `/newroot/sbin/init` is executable. The boot logic itself moved to
  `boot/initramfs/zaod-live` (installed as `/init-boot`), keeps per-step `STEP`
  labels so a screen photo names the step that stopped the boot, and no longer uses
  `set -e` anywhere.
- Media detection reads one 2048-byte sector per ISO descriptor instead of
  skipping 32769 bytes with `bs=1`, prints the candidate list on the first wait and
  a heartbeat at attempt 5 and 20, and `zaod.media=` can name the stick explicitly.
- `tests/test_pid1_supervisor.py` runs the supervisor with a failing child, a
  SIGKILLed child and a ready child, and asserts `/init` and `/init-boot` carry no
  `set -e`. It is wired into `scripts/ci-checks.sh`.

### 2026-11-17: the live account has a password a person can type

- Reported: "ZAOD live ka login pass cut ho gaya, dobara nahi aaya". There was no
  password to read. `scripts/build-rootfs.sh` ran `passwd --lock zaodlive`, so the
  only way in was SDDM autologin; anyone on the text console (graphical session did
  not start, or the prompt scrolled past) had no account at all, and `zaod login:`
  is the hostname, not a user name.
- The build now sets a live password: `zaodlive` / `zaod`. Autologin still starts
  the session by itself, the text console accepts the same credentials, `sudo`
  works because `zaodlive` is in `wheel`, and `/etc/issue` prints both values above
  every login prompt so nothing depends on catching a line mid-scroll.
- Verified against the extracted iso-24 rootfs that the chpasswd step writes a real
  yescrypt hash, and the shipped image after this change accepts that login on
  ttyS0.
- Open: on the QEMU test box the boot reaches `zaod login:` but never reaches
  `multi-user.target`, so `sddm` never starts. The image ships sddm, plasma,
  `default.target -> graphical.target` and `display-manager.service -> sddm.service`,
  so the block is inside the boot transaction (plymouth-quit-wait has not returned
  in every captured run). That is a Phase 5 desktop issue, separate from the
  password fix, and needs a machine with a KMS driver to rule out the emulated GPU.

### 2026-11-17: live media sign in like the installed system

- Requested: "live account me bhi waisa hi flow add kar jaisa pure mode me hai".
- `desktop/sddm/sddm.conf.d/zaod-live.conf` no longer carries `[Autologin]`, so
  live media present the Zaod login screen exactly like an installed system. The
  live account is the real account from the previous entry, `zaodlive` / `zaod`.
- `desktop/sddm/themes/zaod/Main.qml` gained an editable user name field. It used
  to print `userModel.lastUser || "zaodlive"` as a *label* and call
  `sddm.login(userModel.lastUser, ...)`, so on a fresh live boot - where there is
  no last user - the box said "zaodlive" and the login call carried an empty user
  name. Both modes could not sign in on their first boot. `login()` now reads the
  field, refuses an empty name, and the password box keeps focus when a name is
  already filled in.
- `tests/check_desktop_config.py`: 2114 checks, 0 failed.
- Still open from the previous entry: sddm never starts in the QEMU test box (the
  boot stops before `multi-user.target`) - needs a KMS-capable graphics stack or
  real hardware to judge.

### 2026-11-17: first-boot onboarding creates the account

- Requested: "users account create kre and proper waisa he flow onboarding wagera ho ok".
- New `desktop/oobe/oobe.py`: console wizard on tty1 that creates the machine's
  first account (name, account name, password twice, time zone), validates it,
  runs `useradd` with `wheel,audio,video,render,input,netdev`, sets the password
  with `chpasswd`, applies the time zone, writes SDDM `state.conf` so the login box
  opens on the new name, and stamps `/etc/zaod/oobe-done`.
- New `desktop/systemd/zaod-oobe.service`: enabled in the rootfs build, skipped when
  `/etc/zaod/oobe-done` exists, ordered before `display-manager.service` and
  conflicting with `getty@tty1` so the two never fight over the console.
- `desktop/scripts/apply-desktop.sh` installs the wizard to `/usr/lib/zaod/oobe.py`
  and the unit, and creates `/etc/zaod`.
- `tests/test_oobe.py`: 10 tests over the pure rules (reserved names, taken names,
  password rules, `useradd` argv, time-zone matching, remembered login, `--check`).
  `--dry-run` prints the command it would run so the flow is reviewable anywhere.
- Live media run the wizard on every boot (the account lives in the tmpfs layer);
  the wizard says so and lets the person skip to the demo account `zaodlive` / `zaod`.
- Docs: new `docs/onboarding.md`, README phase-10 row updated.
- Still open: nothing here is verified on hardware. The QEMU box reaches `zaod login:`
  but never `multi-user.target`, so neither the wizard nor SDDM has been seen running.

### 2026-11-17: iso-26 shipped, console banner corrected

- iso-26 (`01c5d10`) carries the login flow and the onboarding wizard. Checked inside
  the published image: `/usr/lib/zaod/oobe.py` (0755), `zaod-oobe.service` enabled in
  `multi-user.target.wants`, `zaodlive` with a real yescrypt hash, and no
  `[Autologin]` section in `sddm.conf.d/zaod-live.conf`.
- The wizard was then run against a real image rootfs: it created `hassan`
  (uid 1001, home 0700, wheel + audio/video/render/input/netdev, GECOS "Hassan Ali"),
  set the password, pointed `/etc/localtime` at Asia/Karachi, wrote SDDM `state.conf`
  owned by sddm, and stamped `/etc/zaod/oobe-done`.
- `/etc/issue` still said "the desktop starts by itself", which stopped being true
  when autologin was removed. Corrected; the next image carries it.

### 2026-11-17: the boot no longer stalls on a splash that never runs (fixes the desktop)

- Reported: "live account me bhi waisa hi flow add kar jaisa pure mode me hai" -
  the flow was in place but nobody had seen it finish, because the machine never
  reached a login screen.
- Root cause, proven in QEMU on iso-26: `plymouth-quit-wait.service` carries
  `ExecStart=-/usr/bin/plymouth --wait` and `TimeoutSec=0`, while
  `plymouth-start.service` is neither enabled nor pulled in and the custom
  initramfs never starts plymouthd. There was no splash to quit, so the unit sat
  in "starting" for ever and held `multi-user.target`; `sddm.service` and
  `graphical.target` were never started. Booting the same image with
  `plymouth.enable=0` reached `multi-user.target`, `sddm.service` and
  `graphical.target` normally, which confirmed the cause.
- Fix: `splash` is gone from the GRUB command line (the boot stays readable, as
  the rest of the design intends), and two drop-ins gate
  `plymouth-quit-wait.service` and `plymouth-quit.service` on
  `/run/plymouth/pid`, so a splash that is not running can never hold the boot
  again. `apply-desktop.sh` installs them.
- Also fixed the promise the banner had been making: `Press L to skip` had no
  handler, and typing `l` created an account literally named `l`. The wizard now
  treats `l`/`skip` on live media as "leave me alone, tell me the demo login",
  writes nothing and lets the boot continue; installed media do not offer it.
- Verified in QEMU against the wizard: name, account name, password, time zone
  and confirmation all reach "Account hassan is ready. Starting the desktop...".
- `tests/test_oobe.py`: 12 tests, including the two skip paths.
  `tests/check_desktop_config.py`: 2160 checks, 0 failed.

### 2026-11-17: the login screen comes back (the theme never said which Qt it was for)

- Reported: the login screen was SDDM's own default, not the Zaod theme. iso-29
  carries the fix.
- Root cause, from SDDM 0.21's own source: `ThemeMetadata` reads
  `[SddmGreeterTheme]` and defaults `QtVersion` to 5. The Zaod theme declared
  `ConfigFile` under `[Desktop Entry]`, which SDDM never looks at, and said nothing
  about Qt at all. The image ships only `/usr/bin/sddm-greeter-qt6`, so a theme
  claiming Qt 5 had no greeter to run it and SDDM painted the fallback. The same
  wrong section meant `theme.conf` was never read either.
- Fix: `metadata.desktop` uses `[SddmGreeterTheme]` with `MainScript`,
  `ConfigFile`, `Theme-Id`, `Theme-API=2.0` and `QtVersion=6`.
- Verified inside the published iso-29 squashfs: the metadata above,
  `sddm.conf.d/zaod.conf` still selecting `Current=zaod`, all four theme files
  present, `/usr/bin/sddm-greeter-qt6` and the `SddmComponents` QML module shipped.
- `tests/check_desktop_config.py` now asserts the section, the two file names and
  `QtVersion=6`; reverting the key to 5 fails the check, so this cannot come back
  quietly.
- The `lint` gate is green again after six ruff findings in the wizard: both
  scripts executable, `check=False` on the `chpasswd` run whose returncode is
  inspected, `/etc/passwd` read through a context manager, and two string nits.
  ruff 0.17.5 and shellcheck both clean, `pytest tests zaod/tests -q`: 199 passed.

### 2026-11-17: the boot was never frozen - it was reading 3898 libraries off the stick

- Reported, with a photo of the console: the boot stops after
  `Started systemd-rfkill.service` and never goes on, five or six times.
- Reproduced in QEMU on iso-29. The console sits in
  `Job ldconfig.service/start running (12s / no limit)` and only then reaches
  `basic.target`. `ldconfig.service` has no timeout, and on a live root it reads
  the ELF header of every library in the squashfs - 3898 here - straight off the
  boot media. On a USB stick that is minutes of a screen that never changes, so
  it reads as a hang. The image already ships a correct `/etc/ld.so.cache`, and a
  read-only live root cannot change its libraries, so the rebuild has nothing to
  find.
- iso-29 also still ran plymouthd (`plymouth.enable=0` was never in the image's
  command line): it took the console the onboarding wizard draws on, and
  `plymouth-quit-wait` (TimeoutSec=0) waits for a splash that cannot quit.
- Fix, `boot/initramfs/zaod-live`: the live boot masks `ldconfig.service` and the
  four plymouth units in the tmpfs write layer (the media is still never
  written), and enables `getty@tty2` so Ctrl+Alt+F2 is always a way in.
  `plymouth.enable=0` is now on the GRUB command line too, and
  `rootfs/overlay/.../ldconfig.service.d/10-zaod-timeout.conf` caps the unit at
  60 s on an installed system, where the cache refresh is still wanted.
- Verified on the rebuilt ISO in QEMU: `ldconfig` and `plymouth` never appear in
  the boot log at all, `basic.target` and `getty.target` are reached in about
  40 s under TCG, `getty@tty2` comes up, `zaod-oobe` starts, and the VGA
  screendump reads "Welcome to Zaod OS ... Your name:" - the wizard, on screen,
  instead of a frozen log.
- `tests/check_boot_config.py` grows checks for the command line and the masks,
  and two long-stale checks (it still expected `set -eu` in a script that
  deliberately has none, and looked for the rescue loop in the wrong file) now
  read the file they describe: 92 checks, 0 failed.

### 2026-11-17 (iso-31): the blank screen after switch_root was the console going to a dead serial port

- Reported on real hardware, with a photo: the initramfs log ends at the new line
  `[zaod] kernel 6.18.63-zaod, handing over to the live system` and the screen
  stays blank after it. iso-30 did fix the ldconfig stall - that log is gone.
- Cause: iso-30's command line had `console=tty0 console=ttyS0,115200`, and the
  kernel hands /dev/console to the LAST one. systemd writes its own status to
  /dev/console, so on a laptop that exposes a /dev/ttyS0 node but has no serial
  port, every systemd line after switch_root went into a device nobody reads and
  the screen showed nothing. QEMU never showed this because there ttyS0 is real.
- Fix: `console=ttyS0,115200 console=tty0` - the screen is last, so it gets
  /dev/console - plus `systemd.show_status=1`. Serial still gets its copy, so a
  headless boot stays debuggable. `tests/check_boot_config.py` now fails if tty0
  is not the last console.
- 93 boot checks, ruff and 93 tests green.

### 2026-11-17 (iso-32): a slow boot now explains itself on the screen

- iso-31 got the boot text back on the screen (the console fix held), and the
  report from hardware is a still photo of unit lines stopping around polkit,
  NetworkManager, bluetooth and zaod-lite-mode. Which one is holding the boot
  could not be read off that photo, and the laptop's top row has no F-keys, so
  "switch to a text console and run systemctl" was not a reasonable ask.
- Two additions, neither of which needs a key press:
  - `system.conf.d/20-zaod-boot-guard.conf` caps any unit's start at 75 s and its
    stop at 25 s, so no unit can hold the whole boot forever.
  - `zaod-boot-watchdog.service` (sysinit, `Type=simple`, so it cannot delay the
    boot it watches) waits 95 s for graphical.target; if it is still not there it
    writes the pending jobs and the failed units onto tty1 and starts
    display-manager directly. It never writes over the onboarding wizard.
- `tests/check_boot_config.py`: 104 checks, 0 failed.

### 2026-11-17 (iso-33): the live session stops carrying an installed system's work

- Owner's words after iso-31: no errors at all on screen, fast boot. The hardware
  photo still showed unit lines stopping around polkit and, before that, kernel
  messages about Intel bluetooth firmware that read as failures.
- The live mask list now also covers what a live root can never use: e2scrub
  (`_reap` and the timer), apt-daily and apt-daily-upgrade, fstrim, logrotate,
  dpkg-db-backup, systemd-tmpfiles-clean, bluetooth.service (this radio has no
  firmware in the image, so bluez has nothing to do but fail) and
  wpa_supplicant.service (NetworkManager runs its own). Only the live root is
  masked; an installed system keeps every one of them.
- Combined with the 75 s unit ceiling and the watchdog from iso-32, a stuck unit
  can no longer hold the boot, and the screen explains itself if one tries.
- Boot config checks: 111 run, 0 failed. ruff clean, 93 tests pass.

### 2026-11-17 (kernel console): the blank screen after the GPU driver loads

- Reported cause, and it contradicts nothing in the earlier logs: `boot/grub/grub.cfg`
  writes the boot to the EFI/VESA framebuffer the firmware hands over. udev then
  loads i915/amdgpu/radeon, the modesetting driver replaces that framebuffer, and
  the kernel had `# CONFIG_DRM_FBDEV_EMULATION is not set` with
  `CONFIG_DRM_CLIENT_DEFAULT=""`, so no text console was created on the new one.
  The machine kept booting with nothing on screen, and `zaod-boot-watchdog` could
  not help: it writes to the tty whose console had just disappeared.
- `kernel/build.sh` now enables CONFIG_DRM_FBDEV_EMULATION,
  CONFIG_DRM_CLIENT_DEFAULT_FBDEV, CONFIG_SYSFB_SIMPLEFB and CONFIG_DRM_CLIENT_LOG,
  and `kernel/zaod_defconfig` carries the result (CONFIG_DRM_CLIENT_DEFAULT="fbdev").
  Verified against the v6.18 Kconfig: the client options moved to
  drivers/gpu/drm/clients/Kconfig, and DRM_FBDEV_EMULATION depends on
  DRM_CLIENT_SELECTION, which this config already sets.
- SYSFB_SIMPLEFB also fixes the other half: DRM_SIMPLEDRM was built in with no
  system framebuffer to bind, so the "safe graphics" (nomodeset) entry had no DRM
  device and could not start Plasma.
- `tests/check_kernel_config.py` requires all four, with the reason inline, so the
  next change cannot quietly turn the console off again.
- Login theme: `palette.button: root.accent` inside the Sign in Button killed the
  whole theme. Qt Quick Controls in this image has no `palette` property on
  Button, and the greeter answers one unknown property by discarding the file and
  drawing its own red "The current theme cannot be loaded due to the errors below"
  panel over the login box - visible on the user's photo of iso-35's screen.
  The button now paints through `background` (Rectangle) and `contentItem` (Text),
  and `tests/check_desktop_config.py::check_theme_qml` fails any `palette.<name>:`
  assignment in the theme, comments excluded.

### 2026-11-17 (desktop): Plasma out, the Zaod desktop in

- The user rejected Plasma/KDE outright and asked for the branded desktop, an app
  store and a full app set. Plasma and KDE are gone from `rootfs/packages.list`
  and `desktop/package-list.txt` (26 packages), together with the KDE skel/config
  files, both Plasma session entries, `xdg-desktop-portal-kde` and
  `polkit-kde-agent-1`; `tests/check_rootfs_config.py` fails if any of that
  spelling comes back.
- New `desktop/shell/`: `panel.py` (GTK3 panel on gtk-layer-shell, app grid built
  from `/usr/share/applications`, pinned first-party apps, clock, volume, power),
  `zaod-session` (exports the Zaod environment, execs labwc), `labwc/` (rc.xml,
  autostart with swaybg + panel, menu.xml) and `themerc` for the window border in
  Zaod colours. The session entry is `desktop/sessions/zaod.desktop`, and SDDM
  starts `Session=zaod`.
- The image was booting to an empty desktop because nothing installed the app set:
  `scripts/install-app-set.py` now stages each app from `apps/` into
  `/opt/zaod/apps/<slug>` with `/usr/share/applications/<id>.desktop` and its
  icon, called from `scripts/build-rootfs.sh` right after the desktop layer
  (12 apps: store, editor, notes, tasks, viewer, calculator, clock, converter,
  monitor, control-center, oobe, hello).
- `desktop/scripts/apply-desktop.sh` installs the shell instead of KDE configs;
  `foot` (terminal) and `thunar` (file manager) replace konsole and dolphin, and
  `check_desktop_config.py` now checks the session, the panel and the app set.

