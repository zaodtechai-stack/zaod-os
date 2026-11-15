## Zaod OS Phase 8 applications, store and repository report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - the signed store is complete and was exercised end to end (build a package, sign an index, verify it, resolve a plan, download and check the digest, reject a tampered index). The Firefox repackaging pipeline and the repository builder are written and dry-run clean. The **Control Center application is not built**, and neither Firefox nor the store UI has been run on a Zaod desktop.
- Phase version: 0.8.0

## What was built

| Path | Purpose |
| --- | --- |
| `zaod/repo.py` | Build, sign, verify and query the store index; rejects tampering, expiry, future dating, bad digests and unknown channels |
| `zaod/store.py` | Client: fetch over `file://`/`http(s)://`, verify, cache with an offline fallback, resolve install/update plans, download with size and SHA-256 checks |
| `zaod/tests/test_store.py` | 28 tests over the index model, the client, offline fallback, download verification and a real signed package round trip |
| `apps/firefox/build-firefox-zaod.sh` | Downloads Firefox ESR `153.7.0esr`, verifies it against Mozilla's `SHA512SUMS`, injects policies and provenance, then packs and optionally signs |
| `apps/firefox/policies.json` | Telemetry, studies, Pocket, feedback and the password manager off; updates off; XDG portal file picker on so the sandbox can still show dialogs |
| `apps/firefox/os.zaod.firefox.desktop` | Desktop entry that runs the payload and declares its package |
| `scripts/build-repo.sh` | Signs the index from `build/apps/*.zaod`, publishes `index.json`, its digest and the packages |
| `tests/check_apps_config.py` | 49 checks over the app packaging, the repo builder and the store's security behaviour |

## Verification performed here

```
python3 -m pytest tests zaod/tests -q   -> 160 passed
python3 tests/check_apps_config.py      -> 49 checks run, 0 failed
bash scripts/ci-checks.sh               -> all checks passed
ruff check .                            -> clean
shellcheck ... apps/firefox/*.sh        -> clean
```

The store was exercised as a whole, not just unit tested:

```
build a signed package            -> build/apps/os.zaod.notes-1.0.0.zaod (763 bytes)
SIGNING_KEY=build/keys/main.seed scripts/build-repo.sh
                                  -> index.json with 1 package, expires 2026-12-15
repo.verify_index(...)            -> zaod-main, verified against the trust store
store.Store(...).updates()        -> ['install os.zaod.notes 1.0.0']
client.download(...)              -> 763 bytes, digest matched
tampered index (size changed)     -> SignatureError
```

## Not verified here (honest limits)

1. **No Firefox was downloaded.** The tarball is 82 MB and the sandbox has no
   route to `ftp.mozilla.org`, so `--check` proves the script's inputs and
   guards, not the packaging. The pinned version `153.7.0esr` and its SHA-512
   were read from Mozilla's own `SHA512SUMS` earlier in this project.
2. **No real HTTP mirror.** Every download test used `file://`. HTTPS fetching,
   redirects, timeouts and mirror failover are written but unexercised.
3. **The Control Center application does not exist yet.** Its pages, the
   permission-consent flow and the settings panels are still to be written; the
   `zaod/permissions.py` vocabulary it should consume does exist.
4. **No store UI.** The client is a library with a CLI-able surface, not a
   window; `apps/store` has no QML.
5. **Firefox sandboxing is unproven.** The manifest asks for `network`, `audio`,
   `dri` and home access, but `zaod run` has never launched Firefox because
   bubblewrap is absent in this container.
6. SBOM, licence inventory and the seed repository contents (packages actually
   published) remain for the packaging stage.

## Owner test steps

```sh
make apps                       # 49 checks + both dry runs
VERSION=153.7.0esr SIGNING_KEY=build/keys/main.seed \
  bash apps/firefox/build-firefox-zaod.sh     # needs network, ~82 MB
SIGNING_KEY=build/keys/main.seed bash scripts/build-repo.sh
python3 -m zaod.cli verify build/apps/os.zaod.firefox-153.7.0esr.zaod
```

## Acceptance status

| Item | Status |
| --- | --- |
| signed store index with expiry and channel support | done and exercised |
| tampered or expired index refused | done and exercised |
| offline catalogue from cache | done and exercised |
| download verified by size and SHA-256 before install | done and exercised |
| Firefox ESR repackaged with hardened policies | script written, not run |
| repository builder producing a signed index | done and exercised |
| Control Center | **not built** |
| Store UI | **not built** |
