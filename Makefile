.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs desktop apps iso test clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor  - inspect build-host capabilities' \
	  '  fetch   - download and verify the pinned kernel source tarball' \
	  '  firmware - package selected, pinned Linux firmware' \
	  '  kernel  - build the Zaod kernel and firmware bundle' \
	  '  rootfs  - build the minimal Debian trixie tarball evidence artifact' \
	  '  desktop - assemble desktop components (not implemented yet)' \
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

desktop apps iso:
	@printf 'Target "%s" is not implemented yet.\n' "$@" >&2
	@exit 2

test:
	@python3 -m unittest discover -s zaod/tests -v

clean:
	@rm -rf build