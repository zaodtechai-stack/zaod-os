.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs rootfs-check desktop design apps firefox studio initramfs iso usb boot zaod test zaod-test apps-test studio-test zaod-lint sandbox-proof smoke hello store-index release store-release clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor       - inspect build-host capabilities' \
	  '  fetch        - download and verify the pinned kernel source tarball' \
	  '  firmware     - package selected, pinned Linux firmware' \
	  '  kernel       - build the Zaod kernel and firmware bundle' \
	  '  rootfs       - build the Zaod base system without distro package management' \
	  '  rootfs-check - validate the rootfs inputs without building' \
	  '  desktop      - install and validate the Plasma session configuration' \
	  '  design       - regenerate and validate Zaod Fluent assets' \
	  '  apps         - build and sign every Zaod application package' \
	  '  initramfs    - assemble the live boot initramfs' \
	  '  firefox      - repackage Firefox ESR with the Google search policy' \
	  '  iso          - build the hybrid UEFI/BIOS ISO' \
	  '  usb          - print the safe USB writer usage' \
	  '  boot         - validate boot-chain configuration' \
	  '  hello        - build the reference .zaod app package' \
	  '  store-index  - build every package and sign the store index' \
	  '  release      - assemble a release directory (needs the ISO)' \
	  '  store-release- assemble a store-only release directory' \
	  '  studio       - package Zaod Studio (optional app)' \
	  '  smoke        - start every app window offscreen and screenshot it' \
	  '  test         - run every test suite' \
	  '  apps-test    - run the application test suite' \
	  '  studio-test  - run the Studio, template and project tests' \
	  '  zaod-test    - run the package manager unit tests' \
	  '  zaod-lint    - Ruff + ShellCheck over the repository' \
	  '  sandbox-proof- prove the bubblewrap isolation rules' \
	  '  clean        - remove generated build outputs'

# The host report is evidence, not a tracked deliverable: write it to the log so
# running make doctor never overwrites the committed docs/reports/phase-1.md.
doctor:
	@mkdir -p build/logs
	@bash scripts/doctor.sh | tee build/logs/doctor.log

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

initramfs:
	@bash scripts/make-initramfs.sh

iso:
	@bash scripts/make-iso.sh

usb:
	@printf 'usage: scripts/write-usb.sh --iso build/out/zaod-os-VERSION-x86_64.iso --device /dev/sdX\n' >&2
	@exit 2

boot:
	@python3 tests/check_boot_config.py

zaod: zaod-test

apps:
	@bash apps/build-all.sh $(if $(ZAOD_KEY),$(ZAOD_KEY),)

firefox:
	@python3 apps/firefox/build.py $(if $(ZAOD_KEY),--key $(ZAOD_KEY),)

apps-test:
	@python3 -m unittest discover -s apps/tests -v

studio:
	@python3 apps/studio/build.py $(if $(ZAOD_KEY),--key $(ZAOD_KEY),)

studio-test:
	@python3 -m unittest discover -s studio/tests -v

smoke:
	@python3 apps/smoke.py

zaod-test:
	@python3 -m unittest discover -s zaod/tests -v
	@python3 -m pytest tests -q

zaod-lint:
	@ruff check .
	@shellcheck scripts/*.sh tests/*.sh tests/qemu*.sh kernel/build.sh apps/*/build.sh apps/*/*.sh

# Exit 3 means the filesystem half ran but this host cannot create a network
# namespace, so network isolation stays unproven. Surface that instead of green.
sandbox-proof:
	@bash tests/sandbox-proof.sh || { \
	  rc=$$?; \
	  if [ $$rc -eq 3 ]; then \
	    printf '%s\n' 'sandbox-proof: INCOMPLETE - filesystem isolation proven, network isolation not exercised on this host.' >&2; \
	    exit 3; \
	  fi; \
	  exit $$rc; \
	}

hello:
	@bash apps/hello-gui/build.sh $(if $(ZAOD_KEY),$(ZAOD_KEY),)

release:
	@bash scripts/release.sh $(VERSION) $(if $(ZAOD_KEY),--key $(ZAOD_KEY),)

store-release:
	@bash scripts/release.sh $(VERSION) $(if $(ZAOD_KEY),--key $(ZAOD_KEY),) --store-only

# The index covers every shipped package, so the packages must exist first.
store-index: apps firefox
	@$(if $(ZAOD_KEY),bash repo/build-store.sh $(ZAOD_KEY),@echo "set ZAOD_KEY=path/to/store.key to publish a signed index")

test: zaod-test apps-test studio-test

clean:
	@rm -rf build