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
