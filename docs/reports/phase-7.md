## Zaod OS Phase 7 package manager report

- Date (UTC): 2026-11-15
- Status: **PASS for the library, CLI and tests** - the `.zaod` format, signing, trust store, installed database, transactional installer, sandbox argument builder and a 13-command CLI are implemented and covered by 103 tests. Running a real sandboxed application and privileged installation under `/` still need a booted system.
- Phase version: 0.7.0

## What was built

| Module | Purpose |
| --- | --- |
| `zaod/errors.py` | Exception hierarchy with exit codes |
| `zaod/crypto/ed25519.py` | Pure-Python Ed25519 (sign, verify, key ids), stdlib only |
| `zaod/semver.py` | SemVer 2.0.0 parsing, precedence and constraint matching |
| `zaod/manifest.py` | Strict manifest validator to a frozen dataclass, canonical signing bytes |
| `zaod/checksums.py` | Sorted CHECKSUMS format, strict parser, streaming SHA-256 |
| `zaod/compress.py` | Pluggable compressor: zstd CLI, plain tar, optional Python zstd |
| `zaod/archive.py` | Deterministic packing, inspection, checksum verification, safe unpacking |
| `zaod/signature.py` | Sign/verify over manifest + checksums, trust store, key files |
| `zaod/db.py` | Installed-package database with atomic writes |
| `zaod/installer.py` | Transactional install, update, downgrade guard, remove |
| `zaod/sandbox.py` | Bubblewrap argument vector derived from manifest permissions |
| `zaod/build.py` | Source directory to signed `.zaod` |
| `zaod/cli.py` | `install`, `remove`, `list`, `info`, `verify`, `pack`, `keys`, `run`, `version` |

## Verification performed here

```
python3 -m pytest zaod/tests -q   -> 103 passed
ruff check .                      -> All checks passed
```

Coverage highlights (all executed):

- Ed25519 against the RFC 8032 vectors in `zaod/tests/data/rfc8032_ed25519.json`
- Deterministic packing: two builds of the same tree are byte identical
- Tampered payload detected by CHECKSUMS; tampered manifest or CHECKSUMS rejected by the signature
- Archive safety: absolute paths, `..`, backslashes, drive letters, control characters, hard links, symlink escapes, duplicate members and member-count limits all rejected
- Extraction refuses to overwrite an existing file and never follows a symlink
- Installer: unsigned refused by default, signed install records the key id, min-OS gate, downgrade refused then allowed, reinstall and update paths, remove cleans the tree and the desktop entry, failed install leaves nothing behind
- CLI end to end: pack, verify, info, install, list, remove, keys

## Not verified here (honest limits)

1. **Bubblewrap is not installed in this container**, so `zaod run` prints the
   constructed argument vector and is unit tested on that vector; it has never
   launched a real sandbox.
2. **Privileged installation into `/` was not performed.** Every install test
   runs against a temporary root via the injectable `--root`.
3. **zstd is exercised through the CLI** (`/usr/bin/zstd` 1.5.4 is present), not
   through the optional Python binding, which is not installed here.
4. The desktop integration only writes `.desktop` entries; icon installation
   into the theme cache and `.desktop` validation with `desktop-file-validate`
   need a booted system.
5. No store client yet: fetching an index and resolving updates belongs to
   Phase 8.

## Owner test steps after the Codespaces build

```sh
make zaod                                   # 103 tests
python3 -m zaod.cli version                 # CLI is importable
sudo bwrap --version                        # sandbox prerequisite
sudo zaod install /path/to/firefox-zaod.zaod
zaod list && zaod run os.zaod.firefox
```
