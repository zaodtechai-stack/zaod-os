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
| 3 | Rootfs without distro package management | not implemented | no `rootfs/` package list, no apt/dpkg removal step |
| 4 | Boot chain and live ISO | not implemented | `make iso` exits 2 |
| 5 | Plasma 6 desktop session | not implemented | no `desktop/` sources |
| 6 | Zaod Fluent design system | not implemented | no tokens, no theme, no screenshots |
| 7 | `.zaod` format and package manager | done (one gap) | `make zaod-test` (97 tests), `make hello` |
| 8 | Core apps, Firefox ESR, Store, Control Center | built, partly unverified | `make apps` (13 packages), `make firefox`, `make store-index`, `make smoke` |
| 9 | Zaod Studio and project templates | built | `make studio`, `make studio-test` (16 tests) |
| 10 | Installer, OOBE, updates, QA, release | not implemented | nothing in the tree |

Test totals today: 97 package-manager + 43 application + 16 Studio = **156 tests, all passing**.

## Known gaps (in the order they block the release)

1. **Phase 3 has no code.** There is no `rootfs/packages.list`, no post-install
   hardening, no apt/dpkg removal and no SBOM export. Phases 4, 5, 6 and 10 all
   depend on it, so nothing downstream can be tested until it exists.
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
5. **Phase 9 install path is unverified in QEMU.** Templates build and the Studio
   suite passes; "install offline from a local repo in QEMU and launch all five
   templates" needs the Phase 3/4 image.

## How to check the repository in one pass

```bash
make doctor            # host report -> build/logs/doctor.log (never overwrites docs/)
make fetch             # kernel tarball, PGP + SHA256 (falls back to HTTPS key fetch)
make zaod-lint         # ruff + shellcheck over scripts, tests, kernel, apps
make test              # 97 + 43 + 16 tests
make apps              # 13 signed-ready .zaod packages in build/out/apps
make firefox           # official ESR repackaged, policy added, payload unchanged
make store-index ZAOD_KEY=...   # 14 packages, signed index in build/out/store
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

### 2026-11-15: first pass over phases 8 and 9 (after the store/Studio commits)

- `make apps` builds 13 packages, `make firefox` produces a 101.6 MiB package with
  all 53 upstream files unchanged plus one `policies.json`, `make store-index` signs
  an index over 14 packages, and `make smoke` starts and paints all 12 app windows.
- `make apps-test` 43 tests and `make studio-test` 16 tests pass.
- Not verified here: Store install/update/remove against a hosted repo on a real
  image, Firefox three-tab behaviour on 2 GB, template install in QEMU, Studio
  absent-by-default on the shipped image.
