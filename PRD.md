# Zaod OS Product Requirements Document

**Version:** 1.0 (build-ready)  
**Date:** 15 November 2026  
**Owner:** Zaod OS product owner  
**Executor:** GitHub Codespaces (AI coding agent), supervised by the owner  
**Delivery model:** 10 strictly sequential phases, each with verifiable acceptance tests

## 1. Purpose and governing rules

This PRD is the single source of truth for Zaod OS. `MUST` is mandatory, `SHOULD` is expected unless technically impossible and reported, and `COULD` is optional. A phase is finished only after its acceptance tests pass and evidence is committed. A demo, stub, placeholder binary, or unsupported claim is not completion. If a requirement cannot be met as specified, stop, record measured facts, and propose options; do not silently reduce scope.

## 2. Product overview

Zaod OS is a lightweight x86_64 Linux desktop for low-end PCs. It combines Linux 6.18 LTS with an original Windows 11-inspired design, a native `.zaod` app ecosystem, Zaod Store, Control Center, optional Zaod Studio, and graphical installer. The installed OS must work offline and must not expose Debian package management to users.

### Goals

- Deliver a bootable, installable live ISO.
- Provide a centered taskbar, Start menu, quick settings, notifications, lock/login screens, light and dark themes, and polished keyboard-accessible UX.
- Preinstall an unmodified official Firefox ESR binary packaged as `.zaod`, using Google as its default search engine.
- Provide a functioning Store and Control Center; Studio builds and tests `.zaod` packages.
- Keep all builds reproducible and scripted from this repository.

### Non-goals for v1.0

No new kernel, bootloader, or firmware; no Windows/Android runtime; no ARM/RISC-V/32-bit support; Secure Boot is unsupported and must be documented as off; no printing/scanning or advanced accessibility; no paid services or cloud accounts.

## 3. Target hardware and budgets

- Minimum: x86_64 two-core Celeron-class CPU, 2 GB RAM with zram, 8 GB storage, UEFI (BIOS best-effort), Linux DRM GPU or software fallback, common redistributable Ethernet/Wi-Fi firmware.
- Recommended: 4 GB RAM and 32 GB storage.
- Live ISO: 1.2-2.0 GB. Below 800 MB is a defect indicator and must be explained.
- Installed OS: at most 6.0 GB.
- Idle RAM: at most 1.0 GB on a 2 GB system in Lite mode, measured after two minutes.
- Login: <=45 s SATA SSD, <=90 s HDD on real hardware.
- Firefox: three tabs usable on 2 GB without OOM.
- Store: <=3 s cold start on minimum hardware.

## 4. Fixed technology decisions

Changes require written owner approval.

- Base: Debian 13 (trixie), used only to build the system image; verify current stable versions and record checksums.
- Final system: remove apt, dpkg, all distro package-manager binaries/databases; user applications install only as `.zaod`.
- Init: systemd. Bootloader: GRUB 2 for x86_64 UEFI and i386 BIOS, hybrid ISO via xorriso.
- Live image: squashfs zstd + overlayfs on tmpfs; custom initramfs.
- Desktop: trimmed KDE Plasma 6, Wayland default, X11 fallback; SDDM with custom Zaod QML theme.
- Audio/network/Bluetooth: PipeWire + WirePlumber, NetworkManager, BlueZ.
- Memory: zram-generator (zstd), earlyoom.
- Apps: Python 3.12+ with PySide6/Qt 6; QML for shell widgets.
- Package manager: Python 3 stdlib + Ed25519 signing library; sandbox via bubblewrap.
- Browser: unmodified official Mozilla Firefox ESR x86_64 release, repackaged as `.zaod`; set policy through official `policies.json` only.
- Installer: Calamares with Zaod branding and post-install module.
- Build: GNU Make, shell/Python scripts, logs under `build/logs/`; static signed store index on GitHub Pages/Releases.

## 5. System architecture and installed layout

Layers: firmware; GRUB/initramfs/Plymouth; Linux 6.18 + modules/firmware; Debian-derived systemd/glibc/NetworkManager/PipeWire/Mesa/Xwayland base stripped of package management; Plasma + Zaod shell; Zaod platform/daemon/sandbox/store index; Zaod apps; user `.zaod` apps.

- `/boot`, `/boot/efi`: kernel, initramfs, GRUB, EFI system partition.
- `/usr`, `/etc`, `/var`: managed system image, no distro package manager.
- `/zaod/apps/<id>/<version>`: read-only app payload; `/zaod/apps/<id>/current` symlink.
- `/zaod/runtimes`: shared runtimes.
- `/etc/zaod/keys`: trusted public keys only.
- `~/.zaod/data/<id>`: per-app user data.
- `/var/lib/zaod`: installed database, caches, store index cache.

## 6. Repository structure

`Makefile`; `PRD.md`; `docs/` (ADRs, versions, reports, screens); `scripts/`; `kernel/`; `rootfs/` (package list, hooks, overlay); `boot/` (GRUB, initramfs, Plymouth); `desktop/` (Plasma, KWin, SDDM, theme, wallpapers); `zaod/` (CLI, daemon, sandbox, spec, tests); `apps/`; `installer/`; `repo/`; `tests/`; ignored `build/` outputs.

## 7. Build environment constraints

Codespaces may lack KVM and privileged mounts. Determine and document viable bootstrap methods. Builds must be resumable, use ccache, cache downloads, avoid repeated kernel builds, and keep large artifacts out of Git. QEMU TCG tests need generous timeouts. `scripts/setup-tools.sh` installs required packages, including kernel build tools, ccache, shellcheck, squashfs-tools, xorriso, GRUB tools, mtools, QEMU and OVMF. Stop the Codespace when idle.

## 8. Agent operating rules

1. Work strictly one phase at a time; do not start phase N+1 until phase N passes, its report is committed, and the owner approves.
2. Never fake output or present stubs/placeholders as complete; remove non-working controls.
3. Record commands, raw results, sizes, hashes, screenshots and measurements in `docs/reports/phase-N.md`.
4. On an unmet requirement, stop, report facts and 2-3 options; never silently drop scope.
5. Builds must be idempotent and reproducible from a fresh Codespace; log to `build/logs/`.
6. Pin versions and SHA256 for downloads; verify upstream signatures where available.
7. Use original or compatible open-license assets only; no Microsoft/Windows assets, fonts, sounds, logos or trademarks.
8. Commit often and tag phase ends `phase-N-done`; never commit private keys/secrets.
9. Python passes Ruff and has unit tests for logic; shell scripts pass ShellCheck.
10. At phase end, provide a short summary, measurements and exact test steps.
11. Ask only when an owner decision is truly required.

## 9. Sequential phase plan

Development version is `0.N.0`. Version 1.0.0 is only after Phase 10.

### Phase 1: Foundation, toolchain and feasibility (0.1.0)

**Goal/deliverables:** repo skeleton; `make doctor`; toolchain; measured bootstrap comparison and ADR; signed/checksummed kernel fetch; rootfs build method; Makefile; GitHub Actions lint; devcontainer; QEMU helper; versions and report.

**Acceptance:** `make doctor` succeeds and report is saved; Debian trixie rootfs tar is >=150 MB and size/hash are reported; kernel tarball PGP verification is reported; QEMU helper boots a minimal kernel/initramfs and captures screenshot or serial proof; CI ShellCheck/Ruff pass.

### Phase 2: Kernel (0.2.0)

**Goal:** build Linux 6.18 LTS from source with Zaod config for low-end hardware and sandboxing.

**Tasks:** start from x86_64 defconfig; enable EFI stub/framebuffer, AHCI, NVMe, xHCI/EHCI/storage/HID, ext4/vfat/squashfs-zstd/overlay/ISO9660/loop/tmpfs/devtmpfs; DRM i915/amdgpu/radeon/virtio/simpledrm/fbcon; evdev/libinput/touchpad; Intel and Realtek Ethernet/Wi-Fi, Atheros ath9k/10k/11k, redistributable Broadcom, cfg80211/mac80211, Bluetooth; HDA/Realtek/USB audio/SOF; ACPI, CPU frequency, thermal, battery, backlight; namespaces, cgroups v2, seccomp, zram zstd, KVM guest, virtio, zswap off; hardening and `-zaod` release. Gather only required firmware from official linux-firmware into a firmware archive with license notice. Build `vmlinuz`, `System.map`, config, stripped modules and firmware archives; use ccache and all cores.

**Acceptance:** QEMU `uname -r` is `6.18.x-zaod`; minimal initramfs reaches shell and mounts proc, sys, devtmpfs; validator checks every required config option; compressed kernel <15 MB and stripped modules <250 MB; two clean builds have identical config and module list.

### Phase 3: Base system without distro packages (0.3.0)

**Goal:** reproducible Debian trixie rootfs that boots to multi-user, with distro package management removed.

**Tasks:** curated `rootfs/packages.list` for systemd/udev/dbus, NetworkManager/wpa_supplicant/BlueZ, PipeWire/WirePlumber, Mesa/libinput, licensed Inter/Noto/JetBrains Mono fonts, zram-generator, earlyoom, polkit, bubblewrap, Python/PySide6/Qt/Plasma dependencies. Install Phase 2 kernel/modules/firmware and generate initramfs. Add Zaod `/etc/os-release`, hostname, en_US.UTF-8, timezone handling, default-user template, sudo/polkit rules, journald limits and zram config. Export installed package/license inventory to `/usr/share/zaod/licenses` and `/usr/share/zaod/sbom.txt`, then remove apt/apt-get/apt-cache/dpkg/dpkg-deb/dpkg-query, libraries, `/etc/apt`, `/var/lib/apt`, `/var/lib/dpkg` and verify absent. Strip docs/man pages/unused locales/unneeded firmware. Build squashfs zstd level 19.

**Acceptance:** in QEMU/systemd-nspawn, apt, apt-get, dpkg and aptitude are unavailable and apt/dpkg databases absent; os-release identifies Zaod OS; systemd is running or degraded with units explained; NetworkManager starts and DHCP works under QEMU user networking (external ping/DNS when available); uncompressed rootfs <=3.5 GB and squashfs size reported; SBOM covers all binary packages and license directory exists.

### Phase 4: Boot chain and live ISO (0.4.0)

**Goal:** hybrid UEFI/BIOS ISO boots live Zaod.

**Tasks:** initramfs finds labeled media, mounts read-only squashfs and tmpfs overlay, supports `zaod.live`, `zaod.safegfx`, `zaod.toram`, switches root; GRUB graphical menu for normal, safe graphics, install, first disk, UEFI settings; original Plymouth splash; xorriso hybrid ISO named `zaod-os-VERSION-x86_64.iso` plus SHA256/size; safe `scripts/write-usb.sh`; guide.

**Acceptance:** QEMU OVMF and BIOS boot same ISO to login/session, screenshots saved; all menu entries present and safe graphics passes parameters; ISO size explained; partition table and xorriso volume label verified.

### Phase 5: Desktop session (0.5.0)

Trimmed Plasma 6 core, Wayland default/X11 fallback, SDDM live autologin and installed login, RAM/GPU adaptive Lite mode, zram/earlyoom/swappiness, volatile live journald, Xwayland/clipboard/input/fonts/audio/network applets.

**Acceptance:** QEMU 2 GB boots Plasma and screenshot saved; idle RAM <=1 GB in Lite mode after two minutes; Wayland and X11 fallback verified; Dolphin/Konsole/Kate open/close; Lite mode auto-selects at 2 GB and disables at 4 GB.

### Phase 6: Zaod Fluent design system (0.6.0)

Original reusable tokens (4 px grid, specified radii, blue default/selectable accent, contrast >=4.5:1, 120-250 ms ease-out), Inter/JetBrains Mono, licensed icons/cursor, floating centered taskbar, searchable pinned/recent Start menu, keyboard navigation, quick settings/notifications/calendar, window snapping, lock/login/splash, three original generated wallpapers in light/dark, Qt/GTK theme, design-system docs.

**Acceptance:** 12 named screenshots; automated tokens/contrast validation; license inventory and Microsoft asset scan; taskbar/Start behavior verified including Meta key; owner visual approval before proceeding.

### Phase 7: `.zaod` format and package manager (0.7.0)

Specify v1 and JSON schema. Python CLI: install/remove/list/info/verify/update/search/pack/sign/run/repo add/sync/gc; privilege helper; sha256 + Ed25519 + arch/version/min OS checks; transactional `/zaod/apps` installs and rollback; bubblewrap permission sandbox; desktop integration; explicit confirmation for unsigned developer packages; >=40 tests.

**Acceptance:** test suite passes; tampered payload rejected/not installed; hello-gui desktop entry launches and uninstall removes files; no-network sandbox is proven; interrupted update preserves previous install.

### Phase 8: Core apps (0.8.0)

Official Firefox ESR verified/repackaged unchanged as `.zaod`, Google search policy/default association; PySide6 Control Center pages that change real system settings; Store with signed/cached index, search/details/install/update/remove/offline/error/retry; signed repo tools and >=8 real licensed seed apps; default associations.

**Acceptance:** Firefox works with three tabs on 2 GB; each Control Center page/control tested, real changes take effect; Store installs/updates/removes >=5 apps from local and hosted repos and refuses bad signatures; cold starts <=3 s.

### Phase 9: Zaod Studio (0.9.0)

Optional Studio `.zaod`, toolchain runtime `.zaod`, project archive, templates for Python+Qt, Python CLI, C/C++ CMake, shell, web wrapper; editor with syntax highlighting/search/tree/console/errors; deterministic build recipe, manifest generation, pack/sign; developer keys under user home; sandbox run/debug; guide.

**Acceptance:** install offline from local repo in QEMU; all five templates build/install/launch; invalid manifest provides precise error and produces no package; Studio absent by default; output passes Phase 7 validators.

### Phase 10: Installer, OOBE, updates, QA and release (1.0.0)

Branded Calamares UEFI/BIOS installer, partitioning/account/optional encrypted home, post-install GRUB/initramfs/system setup, one-time OOBE, signed rollback-capable update bundles (SHOULD), hardware matrix, user/developer/build docs, licenses/source offers, release ISO/checksums/signature/notes/store hosting, complete QA and roadmap.

**Acceptance:** UEFI QEMU installs to 8 GB disk, boots and stays <=6 GB; Firefox/Store/Control Center work on 2 GB; BIOS best-effort documented; apt/dpkg absent and `.zaod` installs; real hardware matrix completed by owner; no shipped TODO/FIXME/lorem; all earlier phase tests pass.

## 10. `.zaod` format v1

A zstd-compressed tar archive with `MANIFEST.json`, sorted `CHECKSUMS` for every payload file, `SIGNATURE` (Ed25519 over manifest + checksums for store packages), app `icon.svg` (PNG fallback), `payload/`, optional screenshots. Manifest includes format version, reverse-DNS id, name, semver, kind (app/runtime/theme/project/system-update), `x86_64`, min OS, entry exec/args, description, categories, license, author, runtimes and permissions. Store install rejects malformed schema, hash/signature/key/id collisions, wrong arch, incompatible OS and downgrades unless admin-forced. Install stages/verifies, atomically moves, updates DB/current symlink and desktop entries; rollback on any failure. Signed `index.json` lists package metadata, sizes, hashes, URLs and permissions.

## 11. Security

Only trusted public keys ship at `/etc/zaod/keys`; private root key stays offline. bubblewrap is default least privilege; permissions shown to users. No default installed password; root login disabled; live user isolated; nftables defaults; updates opt-in and signed; systemd service hardening; supply-chain hashes, SBOM, licenses and GPL source offers.

## 12. UI and UX

One Zaod Fluent system across shell/apps/installer; immediate light/dark and accent changes; adaptive Lite mode; loading/empty/error states; keyboard access; responsive 1024x600-4K and 100-200% scaling; no ads/tracking; gettext/Qt translations.

## 13. Quality gates and definition of done

Each phase: all acceptance tests pass, evidence in `docs/reports/phase-N.md`, clean build reproduces, CI lint/tests pass, no unresolved shipped TODO/FIXME, phase tag created, owner explicitly approves next phase. Report must include status, date, commit/Codespace, duration, build outputs, acceptance table with command/result/evidence, sizes/RAM/timings, honest limitations, owner test steps, and deviations/approvals.

## 14. Risks

Codespace hours/storage: resume/cache/ccache and stop when idle. No KVM: generous serial-based QEMU tests, real-PC owner test. Restricted mounts: use measured bootstrap alternatives. Plasma RAM: Lite mode/zram/earlyoom and report measured failure rather than changing scope. Firefox OOM: policies/zram/earlyoom. Firmware gaps: common redistributable blobs/safe graphics/compatibility matrix. Scope: strict phase gates/no stubs. Legal: original/open assets, unmodified Firefox, license register. Secure Boot: document disabled requirement.

## 15. Licensing and trademarks

Zaod original code license to be chosen by owner; kernel/Debian/KDE licenses remain; ship license list and source offers. Inter/JetBrains Mono use SIL OFL; Fluent UI System Icons MIT. Record each asset/license. Windows/Microsoft/Fluent/Firefox names are trademarks; no affiliation or compatibility claims.

## Appendix: phase-start prompt and glossary

Follow sections 4 and 8. Work one phase at a time from Phase 1, never fake results, report deviations with evidence, run tests, report and wait for owner approval before the next phase. `.zaod` is the package/project format; Lite mode reduces effects on low-RAM/software GPU; live ISO runs without install; OOBE is first-boot setup; SBOM lists shipped components; TCG is QEMU software emulation.
