#!/usr/bin/env bash
set -euo pipefail

ROOTFS_DIR="${ROOTFS_DIR:-/tmp/zaod-rootfs-minimal}"
OUT_DIR="${OUT_DIR:-build/out}"
TARBALL_PATH="${TARBALL_PATH:-$OUT_DIR/zaod-trixie-rootfs-minimal.tar}"

mkdir -p "$OUT_DIR"
if [[ $(id -u) -eq 0 ]]; then
  RM=()
else
  RM=(sudo -n)
fi
"${RM[@]}" rm -rf "$ROOTFS_DIR" "$TARBALL_PATH" "$TARBALL_PATH.sha256"

docker rm -f zaod-rootfs-builder >/dev/null 2>&1 || true

BUILD_DIR="$(mktemp -d)"
cat > "$BUILD_DIR/Dockerfile" <<'EOF'
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt bash ca-certificates coreutils curl dbus findutils grep gzip iproute2 \
    less openssl procps python3 sed systemd systemd-sysv tar tzdata util-linux xz-utils \
    netbase vim-tiny && rm -rf /var/lib/apt/lists/*
EOF

docker build -t zaod-rootfs-builder "$BUILD_DIR" >/dev/null

docker create --name zaod-rootfs-builder-container zaod-rootfs-builder >/dev/null

docker export zaod-rootfs-builder-container -o "$TARBALL_PATH"
docker rm -f zaod-rootfs-builder-container >/dev/null 2>&1 || true
rm -rf "$BUILD_DIR"

sha256sum "$TARBALL_PATH" > "$TARBALL_PATH.sha256"
ls -lh "$TARBALL_PATH"
printf 'Root filesystem tarball created: %s\n' "$TARBALL_PATH"
