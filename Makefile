.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs rootfs-check desktop design firefox repo apps initramfs iso usb boot zaod test clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor  - inspect build-host capabilities' \
	  '  fetch   - download and verify the pinned kernel source tarball' \
	  '  firmware - package selected, pinned Linux firmware' \
	  '  kernel  - build the Zaod kernel and firmware bundle' \
	  '  rootfs  - build the Zaod root filesystem and squashfs image' \
	  '  rootfs-check - validate the rootfs inputs without building' \
	  '  desktop - install and validate the Plasma session configuration' \
	  '  design  - regenerate and verify the design system artefacts' \
	  '  apps    - validate the app packaging and the signed store' \
	  '  firefox - build the Firefox ESR .zaod package' \
	  '  repo    - build and sign the store index' \
	  '  initramfs - verify the live-boot initramfs inputs' \
	  '  iso     - assemble the hybrid UEFI/BIOS ISO' \
	  '  usb     - usage reminder for writing an ISO to a USB device' \
	  '  boot    - validate the GRUB, Plymouth and live-boot configuration' \
	  '  zaod    - run the package manager test suite' \
	  '  test    - run every available test' \
	  '  clean   - remove generated build outputs'

doctor:
	@mkdir -p build/logs docs/reports
	@bash scripts/doctor.sh | tee build/logs/doctor.log docs/reports/phase-1.md

fetch:
	@mkdir -p build/cache
	@bash scripts/fetch.sh

rootfs:
	@mkdir -p build/out
	@bash scripts/build-rootfs.sh

rootfs-check:
	@bash scripts/build-rootfs.sh --check
	@python3 tests/check_rootfs_config.py

firmware:
	@bash scripts/build-firmware.sh

kernel: firmware
	@bash kernel/build.sh

desktop:
	@mkdir -p build/logs build/desktop-check/etc
	@bash desktop/scripts/apply-desktop.sh --root "$(CURDIR)/build/desktop-check" --dry-run > build/logs/desktop.log
	@python3 tests/check_desktop_config.py | tee -a build/logs/desktop.log

design:
	@mkdir -p build/logs
	@python3 desktop/design/tools/tokens_to_qml.py --check
	@python3 desktop/design/tools/tokens_to_css.py --check
	@python3 desktop/design/tools/make_wallpapers.py --check
	@python3 tests/check_design_tokens.py --verbose | tee build/logs/design.log
	@python3 desktop/design/tools/scan_assets.py

apps:
	@python3 tests/check_apps_config.py
	@bash apps/firefox/build-firefox-zaod.sh --check
	@bash scripts/build-repo.sh --check

firefox:
	@bash apps/firefox/build-firefox-zaod.sh

repo:
	@bash scripts/build-repo.sh

initramfs:
	@bash scripts/make-initramfs.sh --check

iso:
	@bash scripts/make-iso.sh --check

usb:
	@printf 'usage: scripts/write-usb.sh --iso build/out/zaod-os-VERSION-x86_64.iso --device /dev/sdX\n' >&2
	@exit 2

boot:
	@python3 tests/check_boot_config.py

zaod:
	@python3 -m pytest zaod/tests -q

test:
	@python3 -m pytest tests zaod/tests -q

clean:
	@rm -rf build