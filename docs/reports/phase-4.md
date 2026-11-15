## Zaod OS Phase 4 boot chain report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - the complete boot chain is written and statically validated, and the ISO really assembles with the right volume label and both El Torito entries. It has **not** been booted: this container has no kernel modules, no QEMU and no root, so QEMU OVMF/BIOS boot to a session remains for the Codespaces or hardware run.
- Phase version: 0.4.0

## What was built

| Path | Purpose |
| --- | --- |
| `boot/plymouth/zaod.plymouth`, `boot/plymouth/zaod.script` | Original Plymouth theme: fade-in mark, eight-frame spinner, progress pill, message hook |
| `boot/plymouth/tools/gen-assets.py` | Draws all 19 splash images from code with the standard library only (own PNG encoder and rasteriser) |
| `boot/grub/grub.cfg` | Graphical menu: live session, safe graphics, copy-to-RAM, installer, first internal disk, UEFI firmware settings, memtest, rescue shell |
| `boot/grub/theme/zaod/theme.txt` | Original GRUB theme in the Zaod palette |
| `boot/initramfs/zaod-live` | Live-boot init: parses `zaod.*`, finds the ZAODOS label, mounts squashfs read-only, stacks a tmpfs overlay, `switch_root` |
| `scripts/make-initramfs.sh` | Standalone cpio + zstd initramfs containing only the modules the live init needs |
| `scripts/make-iso.sh` | Hybrid UEFI/BIOS ISO through xorriso, EFI partition built with mtools (no loop device, no privileged tools) |
| `scripts/write-usb.sh` | Guarded USB writer |
| `tests/check_boot_config.py` | 88 static checks over all of the above |

## Verification performed here

```
python3 tests/check_boot_config.py   -> 88 checks run, 0 failed
bash scripts/ci-checks.sh            -> all checks passed
python3 -m pytest tests zaod/tests -q -> 176 passed
shellcheck scripts/*.sh tests/*.sh desktop/scripts/*.sh kernel/*.sh -> clean
```

Checks that exercise real tools rather than text matching:

- `scripts/make-initramfs.sh --check` fails with a clear message on a host with no
  kernel modules ("no kernel modules found below /lib/modules") and never writes a
  partial image.
- `scripts/make-iso.sh` was run end to end on this host with placeholder kernel,
  initramfs and squashfs files. It produced
  `build/out/zaod-os-0.4.0-x86_64.iso` (15 MB), and inspection with independent
  tools confirmed the structure:

```
xorriso -indev ... -pvd_info      -> Volume Id : ZAODOS
file ...                          -> ISO 9660 CD-ROM filesystem data 'ZAODOS' (bootable)
xorriso -report_el_torito         -> 1  BIOS  y  none  ... /boot/grub/i386-pc/eltorito.img
                                     2  UEFI  y  none  ... /boot/efiboot.img
```

- `scripts/write-usb.sh` safety guards were exercised: a non-block device is
  refused, a partition path is refused, mounted partitions are refused, an
  undersized target is refused, a mismatched confirmation aborts, and the written
  label is re-read after `dd`.

## Not verified here (honest limits)

1. **No boot test.** There is no `/lib/modules` tree and no QEMU/OVMF in this
   container, so neither the initramfs nor the ISO has been booted. The ISO's
   boot records are structurally correct; that is not proof it boots.
2. **The ISO above is an assembly test with placeholder inputs**, not a shippable
   image. It proves the xorriso/mtools/grub-mkimage pipeline, the label and the
   dual El Torito entries.
3. **GRUB theme is not rendered.** `theme.txt` syntax follows the GRUB theme
   format but the `select_*.png` pixmaps it names are not generated yet, so the
   menu currently falls back to the default style.
4. **Plymouth artwork is generated but never shown.** Plymouth itself is not
   installed in this container.
5. `zaod.toram=1` memory arithmetic is written and linted but not measured on a
   real machine.

## Owner test steps

```sh
# on Ubuntu 24.04 with root, after the kernel stage produced build/out/vmlinuz
sudo apt-get install -y xorriso mtools grub-pc-bin grub-efi-amd64-bin busybox-static
make kernel
sudo bash scripts/build-rootfs.sh          # produces build/out/zaod-rootfs.squashfs
sudo bash scripts/make-initramfs.sh
sudo bash scripts/make-iso.sh
sha256sum -c build/out/zaod-os-0.4.0-x86_64.iso.sha256

qemu-system-x86_64 -m 4096 -enable-kvm \
  -bios /usr/share/OVMF/OVMF_CODE.fd \
  -cdrom build/out/zaod-os-0.4.0-x86_64.iso
qemu-system-x86_64 -m 4096 -cdrom build/out/zaod-os-0.4.0-x86_64.iso   # BIOS path

sudo bash scripts/write-usb.sh --iso build/out/zaod-os-0.4.0-x86_64.iso --device /dev/sdX
```

## Acceptance status

| PRD acceptance item | Status |
| --- | --- |
| initramfs finds labelled media, mounts squashfs read-only with tmpfs overlay | written, static checks pass, not booted |
| `zaod.live`, `zaod.safegfx`, `zaod.toram` supported | written and checked in the menu and the init |
| switch_root into the live system | written, not executed |
| graphical GRUB menu with all entries | all eight entries present and checked; theme pixmaps missing |
| original Plymouth splash | artwork generated from code, theme written, not displayed |
| hybrid ISO named `zaod-os-VERSION-x86_64.iso` with SHA256 and size | assembled and inspected; label and both boot records confirmed |
| safe `write-usb.sh` | guards implemented and exercised |
| QEMU OVMF and BIOS boot to login | **not done here**, needs the Codespaces or hardware run |
