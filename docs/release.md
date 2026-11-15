# Release process

Every release is one directory with the image, the store packages, checksums, a signed
manifest and human-readable notes. Nothing is published until `SHA256SUMS` verifies.

## Store release

```bash
make store-index ZAOD_KEY=build/keys/store.key     # build packages and sign the index
make store-release VERSION=1.0.0 ZAOD_KEY=build/keys/release.key
```

That writes `build/release/1.0.0/` containing `store/` (packages, `index.json`,
`index.sig`, `store.pub`), `SHA256SUMS`, `release.json`, `release.json.sig` and
`RELEASE-NOTES.md`.

## Full release

```bash
make iso                                            # not implemented yet; see below
make release VERSION=1.0.0 ZAOD_KEY=build/keys/release.key
```

`scripts/release.sh` refuses to run without `build/out/zaod-os-<version>-amd64.iso` unless
`--store-only` is passed. That guard exists on purpose: a release that silently ships no
image is worse than a release that fails.

## What must be published together

1. `zaod-os-<version>-amd64.iso` and its entry in `SHA256SUMS`.
2. `store/` with the signed index and every package the image references.
3. `release.json` plus `release.json.sig`, signed with the release key.
4. `RELEASE-NOTES.md` with the package list and verification commands.
5. `SOURCE-OFFER.txt` naming the exact tag and the source locations from `docs/licenses.md`.

Users verify with:

```bash
sha256sum -c SHA256SUMS
zaod key trust store/keys/store.pub
zaod verify store/<package>.zaod
```

## Update bundles

Between releases, ship changes as a signed bundle instead of a new image:

```bash
zaod bundle create build/out/apps/*.zaod \
  --out build/out/updates-1.0.1.zaodbundle \
  --base 1.0.0 --target 1.0.1 \
  --notes "Security updates for Files and Firefox" \
  --key build/keys/release.key
zaod bundle verify build/out/updates-1.0.1.zaodbundle
zaod bundle apply  build/out/updates-1.0.1.zaodbundle
```

A bundle is verified before a single file is touched, each package is verified again
before it is installed, and the previously installed versions are snapshotted into
`/var/lib/zaod/updates/<stamp>-<target>/`. If any install fails, the whole run is rolled
back automatically; `zaod bundle rollback <journal>` replays a journal by hand.

## Versioning and tags

`docs/versions.md` is the source of truth for component versions. Tags follow the
phases: `phase-<n>-done`. Every release note names the exact commits it was built from.
