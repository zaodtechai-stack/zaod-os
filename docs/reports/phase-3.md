## Zaod OS Phase 3 base system report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - the package set, every shipped configuration file and the full build script are written and validated by 91 static checks plus a working `--check` dry run. The rootfs itself has **not** been built here: `debootstrap` needs root, a mirror and roughly 2 GB of downloads, none of which this container has.
- Phase version: 0.3.0

## What was built

| Path | Purpose |
| --- | --- |
| `rootfs/packages.list` | 105 curated packages in eight groups: init, boot and storage, networking, audio/video, graphics and input, desktop, session helpers, memory, Python/Qt |
| `rootfs/rootfs.remove.list` | 22 paths: the `apt`/`dpkg` front ends, their databases, configuration and the two libraries only they link |
| `rootfs/files/etc/os-release`, `lsb-release`, `hostname`, `hosts` | Zaod identity (`ID=zaod`, `NAME="Zaod OS"`) and no Debian branding |
| `rootfs/files/etc/locale.gen`, `default-locale` | `en_US.UTF-8` generated and default |
| `rootfs/files/etc/timezone-note` | Records the deliberate decision not to bake in a timezone |
| `rootfs/files/etc/sudoers.d/zaod-desktop` | `%wheel` may administer, no `NOPASSWD` |
| `rootfs/files/etc/polkit-1/rules.d/50-zaod-desktop.rules` | `wheel` is the admin group, PackageKit is refused so only `zaod` installs packages |
| `rootfs/files/etc/systemd/journald.conf.d/zaod.conf` | Bounded persistent journal (200 MB cap, 2 week retention) |
| `rootfs/files/etc/systemd/journald.conf.d/zaod-live.conf` | `Storage=volatile` so a live session never writes to the boot media |
| `rootfs/files/etc/systemd/zram-generator.conf.d/zaod.conf` | `zram0` sized `min(ram/2, 4096)`, zstd |
| `rootfs/files/etc/sysctl.d/90-zaod-memory.conf` | `swappiness=100`, cache pressure, `min_free_kbytes` |
| `rootfs/files/etc/earlyoom.conf` | Protects the session processes, prefers killing browsers |
| `scripts/build-rootfs.sh` | Seven-stage build: bootstrap, config, kernel, SBOM, strip, remove package manager, squash |
| `tests/check_rootfs_config.py` | 91 static checks over all of the above |

## Verification performed here

```
bash scripts/build-rootfs.sh --check   -> inputs ok, 105 packages, 22 removal paths, nothing written
python3 tests/check_rootfs_config.py   -> 91 checks run, 0 failed
shellcheck scripts/*.sh                -> clean
bash scripts/ci-checks.sh              -> all checks passed
python3 -m pytest tests zaod/tests -q  -> 176 passed
```

The `--check` mode is not decorative: it fails when `mksquashfs` or a bootstrap
tool is missing, when the package list is empty, when a required package is
missing, when the removal list stops covering `/usr/bin/apt`, `/usr/bin/dpkg`,
`/var/lib/dpkg`, `/var/lib/apt` or `/etc/apt`, and when `os-release` no longer
says `ID=zaod`.

Checks on the script that guard the acceptance criteria:

- the SBOM is generated from `dpkg-query` **before** the database is removed,
  and licence texts land in `/usr/share/zaod/licenses`
- removal is verified twice: every listed path must be gone, and
  `command -v apt`, `apt-get`, `apt-cache`, `dpkg`, `dpkg-query`, `dpkg-deb`
  must fail inside the chroot
- the uncompressed size is measured before squashing and the build fails above
  the 3.5 GB budget
- every removal path is expanded as `${ROOTFS_DIR:?}/…`, so an unset variable can
  never delete a host directory
- the squash uses `-comp zstd -Xcompression-level 19`

## Not verified here (honest limits)

1. **No rootfs was produced.** There is no root, no mirror access and no 2 GB of
   package downloads in this sandbox, so the actual install, the removal run, the
   SBOM export and the final squashfs size are all unmeasured.
2. **Package names are not resolved against a live mirror.** The list was written
   against Debian trixie naming, and `wpasupplicant` was already corrected once
   during review; a real `debootstrap` run may still find a renamed package.
3. **`apt`/`dpkg` library removal is untested.** `libapt-pkg` is not linked by the
   desktop, but that claim has not been proven with `ldd` inside a built rootfs.
   If a binary does link it, the desktop will fail to start and the removal list
   must drop those two lines.
4. **No `systemd-nspawn` or QEMU boot.** Nothing has started the resulting system,
   so NetworkManager DHCP and the "degraded units explained" acceptance item are
   open.
5. The size budget of 3.5 GB is an estimate from the package set, not a measured
   number.

## Owner test steps

```sh
sudo apt-get install -y debootstrap squashfs-tools
make kernel                 # produces build/out/vmlinuz and modules
make rootfs-check           # 91 checks + dry run
sudo make rootfs            # builds, strips, de-packages, squashes
cat build/logs/rootfs-report.txt

sudo systemd-nspawn -D build/rootfs /bin/sh -c \
  'command -v apt; command -v dpkg; ls /var/lib/dpkg; cat /etc/os-release'
sudo mksquashfs build/rootfs /tmp/check.squashfs -comp zstd -Xcompression-level 19 -noappend
```

## Acceptance status

| PRD acceptance item | Status |
| --- | --- |
| curated package list for systemd, networking, audio, graphics, fonts, memory tools, Python/Qt | written, 105 packages, statically checked |
| kernel, modules and firmware installed from Phase 2 | scripted, gated on `build/out/vmlinuz` existing |
| Zaod `os-release`, hostname, locale, timezone policy, user template, sudo and polkit, journald, zram | all shipped and checked |
| SBOM and licence inventory exported | scripted from `dpkg-query`, unrun |
| apt/apt-get/apt-cache/dpkg/dpkg-deb removed with databases absent, verified | scripted with a two-step verification, unrun |
| docs, man pages and unused locales stripped | scripted with `find -delete`, unrun |
| squashfs zstd level 19, size reported | scripted, unrun |
| boot in QEMU or systemd-nspawn with no apt, DHCP working | **not done here** |
