# Building the Zaod OS ISO

The ISO cannot be built inside the assistant sandbox: the container has no
`CAP_SYS_ADMIN`, so `debootstrap`/`mmdebstrap` cannot mount `/proc` inside the target root
(`mount: permission denied`), there is no `/dev/kvm` for a virtual machine fallback, and
`mmdebstrap --mode=fakechroot` is broken by glibc 2.41
(`undefined symbol: __tunable_is_initialized`). A configured Plasma 6 rootfs needs real
maintainer scripts, so a chroot-less workaround would produce an unbootable image.

The reproducible path is the workflow in `.github/workflows/iso.yml`, which builds on a runner that
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

## Running it

The workflow lives at `.github/workflows/iso.yml` and runs on every push to `main` that
touches `scripts/`, `rootfs/`, `boot/`, `apps/`, `desktop/`, the `Makefile` or the workflow
itself, and on demand from Actions -> iso -> Run workflow. It needs the `contents: write`
permission the file already declares, which is what lets it publish a release.

## Measured sizes (run #10, packaged kernel 6.12.107+deb13-amd64)

| Artifact | Measured |
| --- | --- |
| `zaod-rootfs.squashfs` | 818 MB (zstd 19, from a 2203 MB uncompressed tree) |
| `zaod-rootfs.tar` | 2.2 GB uncompressed, reproducible |
| `initramfs.img` | 2.0 MB (23 modules: the 18 boot drivers plus their `modules.dep` closure) |
| `zaod-os-0.4.0-x86_64.iso` | 847 MB |
| rootfs package count | 108 |

The wall-clock cost on a `ubuntu-24.04` runner is about 7 minutes: roughly 3 for the
bootstrap, 3 for the squash at level 19, and seconds for the initramfs and the ISO assembly.

## Defects that had to be fixed before the build went green

Each of these failed a run on its own, and two of them reported the same misleading error.

- **Rootfs package names** (run #2): four names in `rootfs/packages.list` do not exist in
  trixie (`plasma-workspace-wayland`, `kscreenlocker`, `zram-generator`, `python3-pyqt6-svg`).
- **Runner keyring** (run #1): the image ships a Debian keyring older than trixie, so
  `InRelease` could not be verified. The workflow installs the current
  `debian-archive-keyring` first.
- **Initramfs module mapping** (run #7): the gate demanded a hand-written map from every
  config option to a module name and only knew four options.
- **`CONFIG_DEVTMPFS_MOUNT`** (run #8): treated as mandatory although Debian leaves it unset
  and the live init mounts devtmpfs itself.
- **`modules.dep` missing** (run #9): two defects produced one message. `build-rootfs.sh`
  packed `/lib/modules` before `depmod` had written `modules.dep`, and the check itself piped
  a tar listing into `grep -q`, so grep's early exit killed tar with SIGPIPE and `pipefail`
  reported the broken pipe as a missing file. `depmod` now runs before the pack, the archive
  is listed once into a temp file, and nothing pipes a listing into `grep -q` or `head`.
- **`/sbin/modprobe` missing** (same fix): the image only provided applet symlinks in `/bin`,
  but the kernel autoloads modules through `/sbin/modprobe`. `squashfs` and `overlay` were
  therefore never loaded and `mount -t squashfs` dropped every boot into the rescue shell.
  The image now ships `/sbin/modprobe` and the live init modprobes the whole boot stack,
  including `sr_mod`/`cdrom` for optical boot.
- **`SHA256SUMS: Permission denied`** (run #10): the ISO was written successfully and the
  next step failed, because every build step runs through `sudo` and `build/out` belonged to
  root. The workflow now chowns `build/out` back to the runner before the checksum step.

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

## USB boot: the initramfs carried no USB host-controller glue

A stick written with release `iso-13` reached our own init and then died with
`Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000100` on a
Chromebook. Reproduced in QEMU by attaching the same image as a USB mass-storage
device: the live init found no media, printed `waiting for the ZAODOS media
(30/30)` and only `/dev/sr0` existed - no `/dev/sda` at all.

Two defects, both invisible from a CD boot:

- The kernel is Debian's, where `CONFIG_USB_XHCI_PCI` is a module. The initramfs
  carried `xhci-hcd`/`ehci-hcd`/`ohci-hcd` (the shared cores) but not
  `xhci-pci`/`ehci-pci`/`ohci-pci` (the PCI glue), so no controller ever bound
  and `usb-storage` had nothing to drive. `BOOT_MODULES` now carries them plus
  `uas` and `virtio_pci`.
- `console=tty0 console=ttyS0,115200` makes `/dev/console` ttyS0. On a machine
  with no serial port every message the init printed went to a dead port, so the
  failure was invisible; `fail()` then exec'd a shell on that dead console, the
  shell hit EOF and exited, and PID 1 dying is what produced the panic. The init
  now mirrors its messages and the rescue shell to `/dev/tty0`, and an EXIT trap
  reports an unexpected failure with its line number instead of panicking.
