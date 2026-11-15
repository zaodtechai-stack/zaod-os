#!/usr/bin/env bash
# Build and sign the store index from the packages in build/apps.
#
#   scripts/build-repo.sh --check                              # list what would be indexed
#   SIGNING_KEY=build/keys/main.seed scripts/build-repo.sh     # write build/repo
#
# Output layout, ready for GitHub Pages or any static host:
#
#   build/repo/index.json                    signed index
#   build/repo/index.json.sha256             its digest
#   build/repo/packages/<id>-<version>.zaod  the packages themselves
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

APPS_DIR="${APPS_DIR:-build/apps}"
REPO_DIR="${REPO_DIR:-build/repo}"
REPO_NAME="${REPO_NAME:-zaod-main}"
TTL_DAYS="${TTL_DAYS:-30}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://packages.zaod.os}"
SIGNING_KEY="${SIGNING_KEY:-}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

say() { printf '\033[1;36m[repo]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[repo] %s\033[0m\n' "$*" >&2; exit 1; }

[[ -d "$APPS_DIR" ]] || fail "$APPS_DIR does not exist (build some packages first)"
mapfile -t packages < <(find "$APPS_DIR" -maxdepth 1 -name '*.zaod' -type f | sort)
(( ${#packages[@]} > 0 )) || fail "no .zaod packages in $APPS_DIR"

say "indexing ${#packages[@]} package(s) from $APPS_DIR"
for package in "${packages[@]}"; do
  printf '  %s (%s)\n' "$(basename "$package")" "$(du -h "$package" | cut -f1)"
done

if (( CHECK )); then
  printf '[repo] --check done, nothing written\n'
  exit 0
fi

if [[ -n "$SIGNING_KEY" ]]; then
  [[ -f "$SIGNING_KEY" ]] || fail "signing key $SIGNING_KEY does not exist"
else
  fail "SIGNING_KEY is required: an unsigned index is rejected by every client"
fi

mkdir -p "$REPO_DIR/packages"
for package in "${packages[@]}"; do
  cp -f "$package" "$REPO_DIR/packages/"
done

python3 - "$REPO_DIR" "$REPO_NAME" "$TTL_DAYS" "$PUBLIC_BASE_URL" "$SIGNING_KEY" <<'PY'
import hashlib
import sys
from pathlib import Path

from zaod import archive, repo, signature

repo_dir = Path(sys.argv[1])
repo_name = sys.argv[2]
ttl_days = int(sys.argv[3])
base_url = sys.argv[4].rstrip("/")
key_path = Path(sys.argv[5])

entries = []
for path in sorted((repo_dir / "packages").glob("*.zaod")):
    payload = path.read_bytes()
    contents = archive.inspect(path)
    try:
        man = contents.manifest
        declared = man.permissions.to_dict()
        permissions = sorted(name for name, value in declared.items() if value is True)
        if not contents.signature:
            print(f"[repo] warning: {path.name} is unsigned")
        entries.append(
            repo.IndexPackage(
                id=man.id,
                version=man.version,
                channel="stable",
                sha256=hashlib.sha256(payload).hexdigest(),
                size=len(payload),
                url=f"{base_url}/packages/{path.name}",
                permissions=permissions,
                min_os=man.min_os,
            ).to_dict()
        )
    finally:
        archive.close_contents(contents)

seed_bytes = bytes.fromhex(key_path.read_text(encoding="ascii").strip())
document = repo.build_index(entries, repo=repo_name, ttl_days=ttl_days)
signed = repo.sign_index(document, seed_bytes)
target = repo.write_index(signed, repo_dir / "index.json")
print(f"[repo] wrote {target} with {len(entries)} package(s), expires {signed['expires']}")
print(f"[repo] signing key id {signature.key_id_for(__import__('zaod').signature.ed25519.public_key_from_seed(seed_bytes[:32]))}")
PY

sha256sum "$REPO_DIR/index.json" | sed "s|$REPO_DIR/||" > "$REPO_DIR/index.json.sha256"
say "signed index ready in $REPO_DIR"
cat "$REPO_DIR/index.json.sha256"
