# Zaod OS source and artifact versions

## Kernel source

- Version: Linux 6.18.63
- Source archive: `linux-6.18.63.tar.xz`
- Archive SHA256: `81764a545072d160748beff4d9de2e7d95aa9f16e8261110288f067a2cc61d71`
- PGP verification: Verified against the upstream signed `sha256sums.asc` manifest using the Linux kernel checksum autosigner key `B8868C80BA62A1FFFAF5FDA9632D3A06589DA6B1`.

## Rootfs artifact

- Method: Docker export from `debian:trixie-slim`
- Artifact: `build/out/zaod-trixie-rootfs-minimal.tar`
- SHA256: `c84a4dcd2028c37dd5efc413a49d6d52acd305b25531fa65ed72ad91428dac2b`
- Size: 150M

## Notes

- The workspace mount is not suitable for direct debootstrap because it is mounted with noexec/nodev.
- The Docker-export method is the accepted build path for Phase 1 documentation and future reproducible builds.

## Package manager tooling (Phase 7)

- Target runtime: Python 3.12+ standard library only, no third-party modules
- zstd: system `zstd` 1.5.4 (`libzstd.so.1` 1.5.4 available as the `ctypes` fallback)
- Signatures: Ed25519 per RFC 8032, vendored in `zaod/zaodlib/ed25519.py`
- Sandbox: bubblewrap 0.8.0 (`bwrap`)
- Lint on the build host: Ruff 0.17.5, ShellCheck 0.9.0
- Manifest and store index schemas: format version 1 (`zaod/spec/`)
