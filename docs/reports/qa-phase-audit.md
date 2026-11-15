## Independent QA audit of the PRD phase gates

- Date (UTC): 2026-11-15
- Auditor run: fresh clone of `main` at `6a1aa94`, nothing pushed from other agents touched
- Host: Linux x86_64, 1 vCPU, 2 GB RAM, gVisor sandbox, no KVM, no Docker
- Pinned kernel source: Linux 6.18.63

### Phase-by-phase result

| Phase | Scope present? | Acceptance re-checked here | State |
| --- | --- | --- | --- |
| 1 | yes | `make doctor`, Ruff, ShellCheck, kernel tarball PGP + SHA256 | PASS |
| 2 | config + build script | config validator (95 options), build throughput measured; clean-build reproducibility not evidenced | PARTIAL |
| 3 | no rootfs script or package list | nothing to run | NOT IMPLEMENTED |
| 4 | no initramfs/GRUB/ISO code | nothing to run | NOT IMPLEMENTED |
| 5 | no desktop code | nothing to run | NOT IMPLEMENTED |
| 6 | no design system code | nothing to run | NOT IMPLEMENTED |
| 7 | yes | 97 unit tests, tamper/unsigned/upgrade/store flows re-run by hand | PASS (no-network proof PARTIAL) |
| 8 | no apps, no store UI | nothing to run | NOT IMPLEMENTED |
| 9 | no Studio | nothing to run | NOT IMPLEMENTED |
| 10 | no installer/OOBE/update bundles | nothing to run | NOT IMPLEMENTED |

### Phase 1 evidence

- `make doctor` completes on a 1-core host.
- `ruff check .` and `shellcheck` are clean, so the CI lint gate is satisfied.
- `sha256sums.asc` carries a valid signature from the kernel.org autosigner
  `B8868C80BA62A1FFFAF5FDA9632D3A06589DA6B1`, and the tarball hash
  `81764a545072d160748beff4d9de2e7d95aa9f16e8261110288f067a2cc61d71` matches both the
  signed manifest and `docs/versions.md`.
- The rootfs tarball from Phase 1 cannot be re-verified: the artifact is not
  archived and `scripts/build-rootfs.sh` required Docker, which this host lacks.

### Phase 2 measurement (1 vCPU, this sandbox)

- Config validator: `python3 tests/check_kernel_config.py kernel/zaod_defconfig` -> PASS, 95 required options.
- Kernel build throughput, measured from `build/out/kernel/build.log`: 912 compile
  units in 779 s including configure, i.e. 1.17 units/s (70/min) on a single vCPU.
- Extrapolation for a clean build of this config (2,500-3,500 units): 36-50 min on
  1 core, 20-28 min on 2 cores, 11-16 min on 4 cores. ccache-warm rebuilds are a
  few minutes.
- The build was stopped deliberately after the throughput sample; no artifact was
  produced, so `uname -r` = `6.18.x-zaod` and "two clean builds produce the same
  config and module list" remain unproven by this audit.

### Phase 7 evidence (re-run by hand, not only via the suite)

- `make zaod-test`: 97 tests, OK. `make hello`: package built.
- Signed install, `list`, `info`, desktop entry, payload path and removal: correct,
  and `zaod list` is empty after removal with no leftover files.
- Unsigned package refused with a clear error; accepted only with `--allow-unsigned`.
- Tampered payload: repacked archive rejected with the exact sha256 mismatch
  (`payload/main.py`), exit 5, nothing installed.
- Upgrade 1.0.0 -> 1.1.0 keeps the previous version for rollback and flips `current`.
- Store: `repo build` produced `index.json` + `index.json.sig`, `repo add` + `repo
  sync` cached 2 packages, `search` and `update` behaved, `gc` dropped the stale tree.
- Sandbox: host `/etc/shadow` and the host home directory are hidden from the app.
  Network isolation could NOT be exercised: this host denies `CLONE_NEWNET`, so
  `bwrap --unshare-all` fails. The same limitation is recorded in `phase-7.md`.

### Fixes applied in this audit

1. `scripts/fetch.sh`: the keyserver protocol (hkp/hkps, port 11371) is blocked on
   restricted networks, so `make fetch` aborted with a bare `Error 2`. The script now
   falls back to importing the autosigner key over HTTPS, fails with a readable
   message when the key is unavailable, and rejects an empty checksum entry.
2. `Makefile`: `make doctor` piped its host report over the tracked
   `docs/reports/phase-1.md`, silently destroying committed evidence and dirtying
   the tree. It now writes `build/logs/doctor.log` only.
3. `tests/sandbox-proof.sh` + `Makefile`: a host without network namespaces used to
   print `network=reachable` for the no-network package and still exit 0, which
   could mark an unproven requirement as passing. It now checks the probe output,
   exits 3 for "filesystem proof only", and `make sandbox-proof` surfaces that as
   `INCOMPLETE` instead of green.
4. `scripts/build-rootfs.sh`: was Docker-only. It now falls back to `mmdebstrap`
   and then `debootstrap` for the same Debian trixie base, per the PRD base-image
   decision, so Phase 1 rootfs evidence can be reproduced on hosts without Docker.

### Still blocking the later gates

- Phases 3-6 and 8-10 have no code in this repository; nothing there can be tested.
- The network half of the Phase 7 sandbox proof and the Phase 2 QEMU boot need a
  host with namespace creation, KVM or a real 2-core machine.

## Follow-up: phase 10 push and repairs (later on 2026-11-15)

Phase 10 tooling was added after this audit (`zaodlib/update.py`, `zaod bundle`,
`apps/oobe`, `installer/`, `scripts/release.sh`, user/release/licence docs). Three
defects in the audited push were found and fixed at the same time:

- `scripts/fetch.sh`, `scripts/build-rootfs.sh` and `tests/sandbox-proof.sh` were
  committed without their executable bit; restored.
- `scripts/build-rootfs.sh` built the `--include` list from a line-wrapped variable,
  leaving spaces inside package names, so mmdebstrap/debootstrap would have rejected
  the list; it is now a normalised comma list.
- The rootfs shipped `apt` and `dpkg` even though phase 3 requires a runtime with no
  distro package management; the script now records `build/out/rootfs-packages.txt`,
  strips package management in both backends, verifies the tree, and refuses any
  tarball that still contains `apt`, `dpkg` or `/var/lib/dpkg/status`.

Neither the rootfs artifact nor the ISO exists yet, so the phase 3/4 gates in this
audit stay open.
