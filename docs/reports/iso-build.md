# Building the Zaod OS ISO

The ISO cannot be built inside the assistant sandbox: the container has no
`CAP_SYS_ADMIN`, so `debootstrap`/`mmdebstrap` cannot mount `/proc` inside the target root
(`mount: permission denied`), there is no `/dev/kvm` for a virtual machine fallback, and
`mmdebstrap --mode=fakechroot` is broken by glibc 2.41
(`undefined symbol: __tunable_is_initialized`). A configured Plasma 6 rootfs needs real
maintainer scripts, so a chroot-less workaround would produce an unbootable image.

The reproducible path is the workflow in `ci/iso-workflow.yml`, which builds on a runner that
allows privileged mounts.

## What the workflow does

1. Frees runner disk space, then installs `debootstrap`, `mmdebstrap`, `squashfs-tools`,
   `xorriso`, `mtools`, `grub-pc-bin`, `grub-efi-amd64-bin`, `busybox-static`, `zstd`, `cpio`.
2. `scripts/build-rootfs.sh`: bootstraps Debian trixie from `rootfs/packages.list`
   (108 packages, Plasma 6, SDDM, Qt 6), applies the Zaod configuration, the Phase 6
   desktop layer, the apps, an initramfs, the SBOM, then squashes to
   `build/out/zaod-rootfs.squashfs`.
3. `scripts/make-initramfs.sh`: assembles the live initramfs from the kernel's modules.
4. `scripts/make-iso.sh`: builds the hybrid UEFI/BIOS ISO with `grub-mkimage`, an ESP made by
   `mformat`/`mcopy`, and `xorriso`. No loop device is needed.
5. Publishes `build/out/zaod-os-<version>-x86_64.iso` and `SHA256SUMS` as release assets, and
   keeps a 30-day workflow artifact.

The kernel comes from the packaged `linux-image-amd64`, because the repository still has no
Phase 2 from-source kernel artifact. `scripts/build-rootfs.sh` exports `vmlinuz`, `config`,
`modules.tar.gz` and `firmware.tar.xz` into `build/out/kernel/` so the ISO and initramfs steps
are identical either way.

## Enabling it (one step, needs repo owner)

Adding a workflow file requires the `workflow` scope, which the current GitHub authorization
does not have (`git push` returns: `refusing to allow an OAuth App to create or update workflow
.github/workflows/iso.yml without workflow scope`).

Either:

- re-authorize the GitHub connection with the `workflow` scope, then run:
  ```bash
  git mv ci/iso-workflow.yml .github/workflows/iso.yml
  git commit -m "ci: build the ISO" && git push
  ```
- or in the GitHub web UI: Actions → New workflow → paste the contents of
  `ci/iso-workflow.yml` as `.github/workflows/iso.yml` and commit.

The push triggers the build. Expect roughly 20-35 minutes for the bootstrap and squash, then
the ISO is downloadable from Releases (`iso-<run number>`) and from the run's artifacts.

## Expected sizes

| Artifact | Approximate |
| --- | --- |
| `zaod-rootfs.squashfs` | 1.4-1.8 GB (zstd, level from `SQUASH_LEVEL`) |
| `initramfs.img` | 20-40 MB |
| `zaod-os-0.4.0-x86_64.iso` | 1.5-1.9 GB |

## Verifying a build

```bash
sha256sum -c SHA256SUMS
# BIOS/QEMU smoke test
qemu-system-x86_64 -m 2048 -smp 2 -cdrom zaod-os-0.4.0-x86_64.iso
# write to USB (destroys the target device)
sudo scripts/write-usb.sh /dev/sdX zaod-os-0.4.0-x86_64.iso
```

Acceptance for a release candidate: boots to SDDM at 1366x768 with 2 GB RAM, the Zaod session
starts Plasma 6, the 13 application packages launch, and `zaod-lite-mode.service` is active.
Until a build has been booted, the image is untested and must not be published as final.
