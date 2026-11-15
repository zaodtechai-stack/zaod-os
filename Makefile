.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs desktop apps firefox studio iso test zaod-test apps-test studio-test zaod-lint sandbox-proof smoke hello store-index clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor       - inspect build-host capabilities' \
	  '  fetch        - download and verify the pinned kernel source tarball' \
	  '  firmware     - package selected, pinned Linux firmware' \
	  '  kernel       - build the Zaod kernel and firmware bundle' \
	  '  rootfs       - build the minimal Debian trixie tarball evidence artifact' \
	  '  desktop      - assemble desktop components (not implemented yet)' \
	  '  apps         - build and sign every Zaod application package' \
	  '  firefox      - repackage Firefox ESR with the Google search policy' \
	  '  iso          - build the bootable ISO (not implemented yet)' \
	  '  hello        - build the reference .zaod app package' \
	  '  store-index  - build every package and sign the store index' \
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

firmware:
	@bash scripts/build-firmware.sh

kernel: firmware
	@bash kernel/build.sh

desktop iso:
	@printf 'Target "%s" is not implemented yet.\n' "$@" >&2
	@exit 2

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

store-index:
	@$(if $(ZAOD_KEY),bash repo/build-store.sh $(ZAOD_KEY),@echo "set ZAOD_KEY=path/to/store.key to publish a signed index")

test: zaod-test apps-test studio-test

clean:
	@rm -rf build
