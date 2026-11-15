# `.zaod` package format, version 1

A `.zaod` file is a zstd-compressed POSIX tar archive. Every Zaod application,
runtime, theme, project and system update is shipped in this one format, and
the system contains no other package manager.

## Archive layout

```
MANIFEST.json      required, JSON object described by manifest.schema.json
CHECKSUMS          required, sorted "<sha256>  <path>" lines for every other file
SIGNATURE          optional, Ed25519 signature document (required for store packages)
icon.svg           required for kind "app" (icon.png accepted as a fallback)
payload/           required for kind "app" and "project"; the app's own files
screenshots/*.png  optional store screenshots
```

`MANIFEST.json`, `CHECKSUMS` and `SIGNATURE` are archive metadata and are never
listed in `CHECKSUMS` themselves.

## Manifest fields

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `format` | `1` | yes | Format version. Anything else is rejected. |
| `id` | string | yes | Reverse-DNS identifier, lowercase, e.g. `org.zaod.hello`. |
| `name` | string | yes | Display name, 1-64 characters. |
| `version` | `MAJOR.MINOR.PATCH` | yes | Package version. |
| `kind` | enum | yes | `app`, `runtime`, `theme`, `project`, `system-update`. |
| `arch` | `"x86_64"` | yes | Only x86_64 exists for v1. |
| `min_os` | `MAJOR.MINOR.PATCH` | yes | Oldest Zaod OS release that may install it. |
| `summary` | string | yes | One line for the store and desktop. |
| `description` | string | no | Longer store text. |
| `categories` | string[] | no | Desktop categories. |
| `license` | object | yes | `{"spdx": "MIT"}` plus optional `name`/`url`. |
| `author` | object | yes | `{"name": "..."}` plus optional `contact`. |
| `entry` | object | for `app`/`project` | `exec` (`payload/...`), optional `args`, `terminal`. |
| `icon` | string | no | `icon.svg`, `icon.png` or a screenshot path. |
| `permissions` | object | yes | See `permissions.md`. |
| `runtimes` | string[] | no | Runtime package ids this app needs. |
| `associations` | string[] | no | MIME types this app registers as default handler. |
| `built_at`, `build` | object | no | Provenance metadata. |

Unknown fields are rejected, so a typo cannot silently disable a permission.

## CHECKSUMS

```
<sha256>  payload/bin/hello
<sha256>  icon.svg
```

Paths are relative, sorted, use `/`, and must not contain `..` or start with `/`.
Every file in the archive except the three metadata files must appear exactly
once. A missing file, an extra file, or a hash mismatch aborts the install.

## SIGNATURE

```json
{"format": 1, "key_id": "2febb0afee0527d3", "sig": "<base64 Ed25519>", "signed": "manifest+checksums"}
```

The signed byte string is exactly:

```
<raw MANIFEST.json bytes> || 0x0A || <raw CHECKSUMS bytes>
```

`key_id` is the first 16 hex characters of `sha256(public_key)`. Trusted public
keys live in `/etc/zaod/keys/<key_id>.pub` as base64, root-owned. Store
packages must be signed by a trusted key. Unsigned packages are only installed
when the user passes `--allow-unsigned`, and `zaod install` prints the
permission summary and the warning before doing so.

## Installed layout

```
/zaod/apps/<id>/<version>/        read-only payload, MANIFEST, CHECKSUMS, SIGNATURE
/zaod/apps/<id>/current -> <version>
/zaod/runtimes/<id>/current       shared runtimes
/usr/share/applications/<id>.desktop
/etc/zaod/keys/<key_id>.pub       trusted public keys only
/var/lib/zaod/db.json             installed-state database
/var/lib/zaod/repos.json          configured repositories
/var/lib/zaod/cache/              verified index and package cache
~/.zaod/data/<id>/                per-app writable data, the sandbox "HOME"
```

## Verification pipeline

`zaod install` runs these steps; any failure leaves the previous install intact.

1. Extract into `/zaod/apps/.staging-<random>` on the same filesystem.
2. Reject archive members that are absolute, contain `..`, are devices, or are
   symlinks pointing outside the package root.
3. Validate `MANIFEST.json` against `manifest.schema.json`.
4. Verify the signature over the raw manifest and checksum bytes.
5. Verify every checksum and reject missing or unlisted files.
6. Check `arch`, `min_os`, and that `entry.exec` is part of the payload.
7. Refuse downgrades and re-installs unless `--force` is given.
8. Atomically move the staged tree to `/zaod/apps/<id>/<version>`, strip write
   permission, swap the `current` symlink, write the desktop entry, then commit
   the database row. Any error restores the previous symlink and removes the new
   version directory.
