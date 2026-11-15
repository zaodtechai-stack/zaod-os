# Operating system updates

Zaod OS updates are published from the **ZAOD Control Center** app and consumed
by every installed machine. Nothing about the update path is vendor-specific: a
release is a version, a signed feed entry, an ISO and its digest.

## Flow

```
Control Center  ──publish──▶  os-release-feed.json (signed)
   (OsRelease entity)              │
                                   ├──▶ zaod-update on each machine: verify,
                                   │    pick a release for this channel and
                                   │    this machine's rollout bucket
                                   ▼
                            download ISO ── verify SHA-256 ──▶ installer
                                                          (transactional, keeps
                                                           the previous slot)
```

1. A release is created in the control center as `draft` (version, channel,
   `iso_url`, `sha256`, size, notes, minimum supported version, rollout).
2. Publishing it sets `published_at` and writes a `release_published` audit
   event. The control center can also pause, resume, archive, or promote a beta
   release to stable.
3. The release list is exported and signed into the feed:
   `scripts/build-os-feed.py --releases build/os-releases.json --key …`
4. Machines read the feed with `zaod.update`, verify the Ed25519 signature and
   the expiry, and decide whether to update.

## Feed format

`zaod/spec/os-release-feed-v1.schema.json` is the normative schema. Each release
carries `version`, `channel` (`stable`/`beta`/`lts`), `status`, `iso_url`
(https only), `sha256` (64 hex), `size`, `min_supported_version`,
`rollout_percent`, `blocker` and an optional `notes_url`. The whole document is
signed over its canonical JSON, and the signature member is excluded from that
canonical form.

## How a machine decides

| Rule | Behaviour |
| --- | --- |
| Channel visibility | `beta` sees beta, stable and lts; `stable` sees stable and lts; `lts` sees lts only |
| Draft, paused, archived | never offered |
| Downgrade | never offered, updates are forward only |
| Rollout | `bucket = sha256(device_id + ":" + version)[:8] mod 100`; offered when `bucket < rollout_percent`, so a machine gets the same answer each time |
| Blocker | offered to every machine on the channel regardless of rollout |
| `min_supported_version` | a machine older than it gets a mandatory update |

The last two are the only ways an update becomes mandatory; nothing else in the
feed can force one.

## Verification before installing

`zaod.update.verify_image(path, release)` re-hashes the downloaded ISO and
compares both the digest and the declared size before the installer is allowed
to touch it. The installer itself is transactional: it stages the new system,
switches a symlink, and rolls back on any failure, including an interrupted
update, so a machine is never left between two versions.

## What still needs doing

- The `zaod-update` daemon and its systemd timer that call `zaod.update.plan` on
  a schedule, download in the background and prompt before rebooting.
- Delta updates (the feed already carries full images; deltas will need a second
  document type).
- Feeding the control center's export into `scripts/build-os-feed.py`
  automatically instead of a manual `build/os-releases.json`.
- A real published ISO; the feed currently points at URLs that do not exist yet.
