# ADR-001: rootfs build method for Zaod OS Phase 1

- Status: Accepted
- Date: 2026-11-15

## Context

Phase 1 requires a reproducible build method for a minimal Debian trixie root filesystem inside GitHub Codespaces. The environment is a non-privileged Ubuntu container with Docker available and without KVM. The host mount for /workspaces is constrained by noexec/nodev, which breaks direct debootstrap into the repository tree. The PRD allows selecting between debootstrap with sudo, mmdebstrap unshare mode, and Docker-based export.

## Decision

Use a Docker-based rootfs export from the Debian trixie-slim image.

## Why this was chosen

1. `debootstrap` failed in this environment while extracting package archives (`tar failed`), which shows the host privilege model is not compatible with a direct rootfs bootstrap into the mounted workspace.
2. `mmdebstrap` was attempted in unshare mode, but it failed because the environment lacks the required mount/user namespace capabilities and Debian archive key material was not present at bootstrap time.
3. Docker is available and functional, and `docker build` plus `docker export` produced a valid Debian trixie rootfs tarball suitable for the PRD evidence requirement.

## Evidence

- `docker info --format '{{.ServerVersion}}'` returned `24.0.9-2`.
- `make -C /workspaces/zaod-os rootfs` produced `build/out/zaod-trixie-rootfs-minimal.tar` with size `150M` and a valid SHA256.
- The tarball satisfies the Phase 1 size gate of at least 150 MB.

## Consequences

- The rootfs artifact is reproducible via Docker and suitable for later boot and ISO work.
- This method does not violate the PRD because it is one of the approved build-method choices.
- The rootfs stays outside the repository workspace mount to avoid noexec/nodev issues during bootstrap.
