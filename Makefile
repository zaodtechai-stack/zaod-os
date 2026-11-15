.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs desktop design apps iso test clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor  - inspect build-host capabilities' \
	  '  fetch   - download and verify the pinned kernel source tarball' \
	  '  firmware - package selected, pinned Linux firmware' \
	  '  kernel  - build the Zaod kernel and firmware bundle' \
	  '  rootfs  - build the minimal Debian trixie tarball evidence artifact' \
	  '  desktop - install and validate the Plasma session configuration' \
	  '  design  - regenerate and verify the design system artefacts' \
	  '  apps    - build Zaod applications (not implemented yet)' \
	  '  iso     - build the bootable ISO (not implemented yet)' \
	  '  test    - run available tests' \
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

apps iso:
	@printf 'Target "%s" is not implemented yet.\n' "$@" >&2
	@exit 2

test:
	@python3 -m unittest discover -s zaod/tests -v
	@python3 -m pytest tests -q

clean:
	@rm -rf build