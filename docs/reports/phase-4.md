## Zaod OS Phase 4 boot chain report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - the original boot splash artwork pipeline is complete and reproducible; the GRUB menu, initramfs hook, hybrid UEFI/BIOS ISO assembly and USB writer are not in the tree yet.

## What was built

- `boot/plymouth/tools/gen-assets.py`: a dependency-free renderer that draws the
  Zaod boot splash from code using only the Python standard library (own PNG
  encoder, vector rasteriser and bitmap lettering). Nothing is a committed blob
  and every pixel is auditable.
- Generated artwork (build output, not committed): 19 files - six background
  sizes (800x600 to 1920x1080), the Zaod mark, wordmark, tagline, an eight-frame
  spinner and the lit/unlit progress pill.

## Commands executed here

```
python3 boot/plymouth/tools/gen-assets.py --outdir build/out/plymouth-assets --force
  -> wrote 19 PNG files (273659 bytes)
python3 boot/plymouth/tools/gen-assets.py --outdir build/out/plymouth-assets
  -> artwork up to date (19 files), nothing to do   [idempotency proven]
ruff check .                                         -> All checks passed
```

## Still to do (Phase 4 remainder)

1. `boot/plymouth/zaod.plymouth` + `zaod.script` wiring the generated PNGs.
2. `boot/grub/grub.cfg`: graphical menu, `search --label`, UEFI and BIOS paths,
   `nomodeset` safe-graphics entry, install entry, firmware-settings entry.
3. `boot/initramfs/`: hook plus the live-boot init that finds the ZAODOS volume,
   loop-mounts the squashfs, builds the tmpfs overlay, `switch_root`, and drops
   to a rescue shell on failure.
4. `scripts/make-initramfs.sh`, `scripts/make-iso.sh` (xorriso hybrid ISO with a
   FAT EFI system partition built by mkfs.vfat + mtools) and
   `scripts/write-usb.sh`.
5. QEMU boot verification of both firmware paths - requires a build host with
   OVMF and KVM, which this sandbox does not have.

## Honest limitations

The splash artwork has been rendered but never displayed: no Plymouth daemon
exists in this container. The artwork pipeline itself is deterministic and
idempotent, which is verified above.
