# The `.zaod` package format, version 1

A `.zaod` file is a **zstd-compressed POSIX tar** with a fixed member layout.
The reader also accepts a plain (uncompressed) tar so that debugging is
possible, but `zaod pack` always writes zstd.

## Members

| Member | Required | Contents |
| --- | --- | --- |
| `MANIFEST.json` | yes | Canonical UTF-8 JSON: two-space indent, sorted keys, trailing newline |
| `CHECKSUMS` | yes | One line per payload file: `sha256:<64 hex> <size> <path>` |
| `SIGNATURE` | when signed | 128 lowercase hex characters: the raw 64-byte Ed25519 signature |
| `icon.svg` / `icon.png` | optional | Referenced by `manifest.icon` |
| `screenshots/*.png` | optional | Referenced by `manifest.screenshots` |
| `payload/**` | when `kind` needs a payload | Files installed below `<root>/usr/lib/zaod/apps/<id>/<version>/` |

`MANIFEST.json` is excluded from `CHECKSUMS` on purpose: the signature covers
`MANIFEST.json` and `CHECKSUMS` together, which is what binds a signed payload
to exactly one manifest.

## Signed document

```
signature = Ed25519(private_key, b"zaod-format-v1\n" + MANIFEST.json + b"\n" + CHECKSUMS)
```

The domain-separation prefix stops a signature over a package document from
being reusable anywhere else.

## Determinism

Two builds of the same source tree produce byte-identical archives:

* members are sorted by name
* `mtime` is fixed to `1704067200` (2024-01-01T00:00:00Z), `uid`/`gid` to 0,
  `uname`/`gname` to `root`
* regular files are `0644`, directories `0755`
* `MANIFEST.json` is written from the validated manifest, never copied verbatim
* `zstd` runs single-threaded without a checksum frame

## Safety rules enforced by the reader

1. Member names must be relative, forward-slash separated, and free of `..`,
   backslashes, drive letters and control characters.
2. Only regular files, directories and symlinks are allowed. Hard links,
   devices and FIFOs are rejected.
3. A symlink target must be relative, `..`-free and resolve inside the package.
4. Duplicate member names are rejected.
5. Extraction writes regular files and directories first and symlinks last,
   each with `O_CREAT | O_EXCL | O_NOFOLLOW`, so a pre-existing symlink in the
   destination can never be followed or overwritten.
6. Bomb bounds: at most 20 000 members, 2 GiB per file, 8 GiB total and a
   compression ratio ceiling of 400:1.

## Trust

Public keys live in `<root>/etc/zaod/keys/<key_id>.pub` as 64 hex characters.
`key_id` is `sha256(public_key).hexdigest()[:16]`. A package that carries a
signature is verified against every trusted key (the set is small); a package
without a signature is refused unless the operator passes `--allow-unsigned`.

## Installing

```
zaod install notes-1.0.0.zaod          # verify, stage, promote, record
zaod list
zaod remove os.zaod.notes
zaod verify notes-1.0.0.zaod
zaod info notes-1.0.0.zaod
zaod pack ./my-app -o my-app-1.0.0.zaod --sign-with seed.hex
zaod keys add 3f7c...c91a
```

An install is transactional: the payload is unpacked into
`var/lib/zaod/staging/`, moved into place, the `current` symlink is swapped
atomically and only then is the database written. Any failure removes the
staging directory, restores the previous `current` symlink and leaves the
database untouched.
