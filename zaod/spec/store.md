# Zaod Store index, version 1

A repository is a directory (served over `file://`, `https://` or `http://`)
containing package archives plus a signed index:

```
index.json      JSON index of every package
index.json.sig  {"format": 1, "key_id": "...", "sig": "<base64 Ed25519>", "signed": "index"}
*.zaod          package archives referenced by the index
```

The signature covers the exact bytes of `index.json`, so any change to a
package's hash, size or URL invalidates the index. The client refuses an index
signed by a key that is not trusted for that repository.

## Index fields

| Field | Meaning |
| --- | --- |
| `format` | `1`. |
| `name` | Repository name, must match the name the client configured. |
| `generated` | UTC timestamp of index creation. |
| `packages[]` | `id`, `name`, `version`, `kind`, `arch`, `min_os`, `summary`, `description`, `categories`, `license`, `author`, `permissions`, `runtimes`, `size`, `sha256`, `filename`, `url`. |

`url` may be relative to the repository base URL. The client builds the package
URL from the repository URL plus `filename` when `url` is absent.

## Client behaviour

- `zaod repo add NAME URL --key K.pub` trusts `K` and records the repository.
- `zaod repo sync` downloads `index.json` and `index.json.sig`, verifies the
  signature, validates the body against `store-index.schema.json`, and caches
  both files under `/var/lib/zaod/cache/index/NAME/`.
- `zaod install <id>` downloads the archive, checks its sha256 against the
  signed index, and only then runs the normal package verification.
- `zaod search`, `zaod update` and the Store UI read the cached index, so
  browsing works offline.
- Bad signatures, wrong repository names, hash mismatches and unreachable
  servers are reported as errors; nothing is installed.

Build an index for a directory of packages with:

```
zaod repo build ./repo-dir --name core --key ./keys/store.key
```
