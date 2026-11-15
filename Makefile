.DEFAULT_GOAL := help

.PHONY: help doctor fetch firmware kernel rootfs desktop apps iso test zaod-test zaod-lint shell-lint sandbox-proof hello store-index clean

help:
	@printf '%s\n' 'Zaod OS build targets:' \
	  '  doctor       - inspect build-host capabilities' \
	  '  fetch        - download and verify the pinned kernel source tarball' \
	  '  firmware     - package selected, pinned Linux firmware' \
	  '  kernel       - build the Zaod kernel and firmware bundle' \
	  '  rootfs       - build the minimal Debian trixie tarball evidence artifact' \
	  '  desktop      - assemble desktop components (not implemented yet)' \
	  '  apps         - build Zaod applications (not implemented yet)' \
	  '  iso          - build the bootable ISO (not implemented yet)' \
	  '  hello        - build the reference .zaod app package' \
	  '  store-index  - build and sign the local store index' \
	  '  test         - run the full test suite' \
	  '  zaod-test    - run the package manager unit tests' \
	  '  zaod-lint    - Ruff + ShellCheck over the repository' \
	  '  sandbox-proof- prove the bubblewrap isolation rules' \
	  '  clean        - remove generated build outputs'

# The host report is evidence, not a tracked deliverable: write it to the log
# so running make doctor never overwrites the committed docs/reports/phase-1.md.
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

desktop apps iso:
	@printf 'Target "%s" is not implemented yet.\n' "$@" >&2
	@exit 2

zaod-test:
	@python3 -m unittest discover -s zaod/tests -v

zaod-lint:
	@ruff check .
	@shellcheck scripts/*.sh tests/*.sh apps/*/build.sh tests/qemu*.sh kernel/build.sh

# Exit 3 means the filesystem half of the proof ran but this host cannot create
# a network namespace, so network isolation stays unproven. Report that loudly
# instead of printing a green result for a proof that did not happen.
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
	@mkdir -p build/out/store
	@cp build/out/apps/*.zaod build/out/store/ 2>/dev/null || true
	@$(if $(ZAOD_KEY),./zaod/bin/zaod repo build build/out/store --name core --key $(ZAOD_KEY),@echo "set ZAOD_KEY=path/to/store.key to sign the index")

test: zaod-test

clean:
	@rm -rf build
