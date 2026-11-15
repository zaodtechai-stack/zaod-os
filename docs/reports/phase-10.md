## Zaod OS Phase 10 report: installer, first boot, updates and release

- Date (UTC): 2026-11-15
- Host: Linux x86_64, Python 3.11.15, PySide6 6.12.0, Calamares configuration only (the
  Calamares binary is not installed here)
- Verification style: real package/bundle operations against a development root, plus
  configuration and tooling checks. Anything needing a bootable image is marked BLOCKED,
  because this repository still contains no Phases 3-6 output (rootfs, Plasma, ISO).

## What shipped in this phase

| Deliverable | Path | State |
| --- | --- | --- |
| Signed update bundles with rollback | `zaod/zaodlib/update.py`, `zaod bundle` CLI | working |
| Update bundle tests | `zaod/tests/test_update.py` | 9 tests |
| First-boot setup app | `apps/oobe/` (backend + window + manifest) | working |
| Installer configuration and branding | `installer/settings.conf`, `installer/branding/`, `installer/modules/` | configuration complete, image missing |
| Release tooling | `scripts/release.sh`, `make release`, `make store-release` | working |
| User, release and licence documents | `docs/user/guide.md`, `docs/release.md`, `docs/licenses.md` | written |
| Store/OOBE application sets | `installer/modules/packages.conf` | written |

## Update bundles

A bundle is an archive with `bundle.json`, `CHECKSUMS`, `SIGNATURE` and `packages/*.zaod`.
The signature covers `bundle.json` plus `CHECKSUMS` with the same Ed25519 scheme packages
use, and every package hash is checked before anything is unpacked.

Applying is transactional over the system, not just over one package:

1. The bundle is verified (signature, then every listed hash).
2. Each package is verified again on its own before it is installed.
3. Before each install, the currently installed version is snapshotted into
   `/var/lib/zaod/updates/<stamp>-<target>/`.
4. On any failure, every package installed in that run is rolled back and the command
   exits with `update failed and was rolled back: <reason>`.

Rollback prefers a pointer switch: the previous version directory is still on disk, so the
`current` symlink and the database record are restored without reinstalling. If that
directory is gone, the journal's snapshot package is reinstalled instead.

Real run on the development root (`ZAOD_ROOT=build/studio-demo`, which reports OS 1.0.0):

```
$ zaod bundle create /tmp/shdemo-0.2.0.zaod --out /tmp/updates-0.2.0.zaodbundle \
      --base 0.1.0 --target 0.2.0 --key .../developer.key
wrote /tmp/updates-0.2.0.zaodbundle (1 packages, e08be056660c569d)
  0.1.0 -> 0.2.0
  signed by: 8295c5e15dbf0f65
$ zaod bundle verify /tmp/updates-0.2.0.zaodbundle
OK bundle 0.1.0 -> 0.2.0 (1 packages)
$ zaod bundle apply /tmp/updates-0.2.0.zaodbundle
updated org.zaodstudio.shdemo
applied 0.2.0; journal .../updates/20261115T130315Z-0.2.0
$ zaod list | grep shdemo
org.zaodstudio.shdemo   0.2.0
$ zaod bundle rollback .../updates/20261115T130315Z-0.2.0
restored org.zaodstudio.shdemo 0.1.0
```

Bundle tests cover: round trip and signature, unsigned bundle refused by default, untrusted
key refused, tampered package detected, apply installs the newer version, a forced failure
mid-bundle rolls everything back, journal replay, empty bundle refused, and the inner
package still being verified.

## First boot (OOBE)

`apps/oobe` is a three-step offline setup: welcome, appearance, privacy and updates, then a
summary page. `payload/backend.py` holds the state logic:

- Defaults are private: `telemetry: false`, `location: false`.
- Theme, accent and update policy are validated against fixed lists.
- `finish()` requires a chosen update policy and writes `~/.config/zaod/oobe.json` with mode
  `0600`, atomically.
- Running again is refused unless `--force`; the window says setup is already complete.

There is no network code in the app at all, which is why it can be offered on a machine
that has never been online.

## Installer configuration

`installer/settings.conf` defines the Calamares sequence: welcome, locale, keyboard,
partitioning, users, an application-set chooser, then the exec sequence including
`zaod-repo` and `bootloader`. Branding lives in `installer/branding/` (`branding.desc`,
`logo.svg`, `welcome.svg`, `show.qml`), and `installer/modules/packages.conf` offers
Minimal, Essentials and Essentials-with-Firefox.

The application set is installed from the local repository baked into the image, so the
installer never needs a network. `installer/modules/zaod-repo.conf` registers that
repository and its trusted key on the installed system.

## Release tooling

`scripts/release.sh` builds one release directory:

```
store/            packages + index.json + index.sig + keys/store.pub
SHA256SUMS        every file in the release
release.json      version, timestamp, artifact hashes and sizes
release.json.sig  Ed25519 signature over release.json (when --key is given)
RELEASE-NOTES.md  version, package list, verification commands
SOURCE-OFFER.txt  licence source offer for every third-party binary
```

It refuses to produce a full release without `build/out/zaod-os-<version>-amd64.iso` unless
`--store-only` is passed, and refuses to run at all when `build/out/apps` has no packages.
ShellCheck is clean.

## PRD acceptance checklist

| Acceptance item | State | Evidence |
| --- | --- | --- |
| UEFI QEMU installation completes and boots to the desktop | BLOCKED | No ISO exists in this repository; `installer/` configuration is complete and the release script refuses to fake an image |
| BIOS installation works best effort | BLOCKED | Same reason |
| Firefox, Store and Control Center usable on 2 GB RAM | BLOCKED | Needs the running image; the apps themselves are built and render offscreen |
| No `apt`/`dpkg` present at runtime | BLOCKED (unverifiable here) | The rootfs is built from Debian packages in Phase 3, which this repository does not contain; the apps and installer depend only on `zaod` |
| Updates install as signed bundles and roll back on failure | PASS | 9 bundle tests plus the real 0.1.0 to 0.2.0 apply and rollback run above |
| First boot presents privacy options with telemetry off by default | PASS | `apps/oobe/payload/backend.py` defaults and `Setup.finish()` rules |
| Licences and source offers documented | PASS | `docs/licenses.md` plus `SOURCE-OFFER.txt` generated by the release script |
| Device matrix (wired networking) on real hardware | BLOCKED | Owner action: needs physical machines, listed in the roadmap |
| No shipped `TODO`, `FIXME` or placeholder text | PASS | repository scan of `docs`, `apps`, `zaod` and `installer` finds none |
| Every earlier phase's tests still pass | In progress | Phase 7-9 suites ran green before Phase 10 additions; the separate testing agent re-runs them |

## Deviations and decisions

- Calamares is configured, not bundled: the binary comes from Debian in the image rootfs.
  The module list references `unpackfs`, `bootloader` and the rest of the standard set,
  which only exist inside the image.
- Setup is a `kind: system` package so the installer can place it in the first-boot slot
  without it appearing in the Store as an ordinary app.
- Rollback reuses the previous version directory instead of reinstalling whenever possible,
  which makes rollback a millisecond pointer change rather than a full unpack.
- Bundle creation signs with a caller-supplied key file; there is no ambient signing key on
  purpose.

## Handover: what still blocks a real 1.0.0

1. **Image pipeline (Phases 3-6).** Without rootfs, Plasma and ISO targets, every installer
   and hardware acceptance item stays BLOCKED. `make iso` still prints "not implemented".
2. **Runtime package.** `org.zaod.runtime.pyside6` is referenced by every Qt app but is not
   built yet; it is the first package a real image needs.
3. **QEMU harness.** A repeatable UEFI/BIOS install test with the two RAM profiles has to be
   written once an image exists.
4. **Hardware matrix.** The owner runs the device checklist; results belong in
   `docs/reports/hardware-matrix.md`.
5. **Release tag.** Once an image is built, `make release VERSION=1.0.0` produces the full
   directory and `v1.0.0` can be tagged.
