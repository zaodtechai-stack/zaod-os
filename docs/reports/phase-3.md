# Phase 3 report

Status: IN PROGRESS — implementation committed for delegated build and acceptance testing; not verified by this development run.

- Date: 2026-11-15
- Target version: 0.3.0

## What was built

- Curated Debian trixie package manifest and Zaod base-system overlay.
- Docker-based rootfs builder that injects the Phase 2 kernel, stripped modules, and pinned firmware archive.
- Finalization hooks for the target initramfs, systemd services, Zaod identity, locale, zram, journald, SBOM, and license notices.
- Package-manager removal hook that verifies apt/dpkg commands and databases are absent.
- Build outputs: uncompressed rootfs tarball and zstd level-19 squashfs.

## Acceptance tests

| Test | Command | Result | Evidence |
|---|---|---|---|
| apt/dpkg removal and SBOM | Delegated to the test agent | NOT RUN here | Awaiting delegated test results |
| Zaod os-release and systemd boot | Delegated to the test agent | NOT RUN here | Awaiting delegated test results |
| NetworkManager DHCP/DNS | Delegated to the test agent | NOT RUN here | Awaiting delegated test results |
| Rootfs size <= 3.5 GB | `du -sh` on generated rootfs | NOT RUN here | Build has not been run here |
| zstd level-19 squashfs and license inventory | Build output inspection | NOT RUN here | Build has not been run here |

## Known issues and limitations

- The build requires Phase 2 outputs: `vmlinuz`, `System.map`, `modules.tar.gz`, `firmware.tar.xz`, and `firmware-source-commit.txt` under `build/out/kernel/`.
- This implementation session did not execute builds or tests per the owner's request to delegate testing.
- Phase 3 is not marked PASS until delegated acceptance results and measurements are recorded.

## How to build

1. Build the kernel and firmware with `make kernel`.
2. Build the Phase 3 rootfs and squashfs with `make rootfs`.
3. Run the Phase 3 acceptance suite in the dedicated test environment and append measured results here.
