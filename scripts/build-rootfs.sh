#!/usr/bin/env bash
set -euo pipefail

ROOTFS_DIR="${ROOTFS_DIR:-/tmp/zaod-rootfs-minimal}"
OUT_DIR="${OUT_DIR:-build/out}"
TARBALL_PATH="${TARBALL_PATH:-$OUT_DIR/zaod-trixie-rootfs-minimal.tar}"
SUITE="${SUITE:-trixie}"
MIRROR="${MIRROR:-http://deb.debian.org/debian}"
PACKAGES="apt bash ca-certificates coreutils curl dbus findutils grep gzip iproute2 \
less openssl procps python3 sed systemd systemd-sysv tar tzdata util-linux xz-utils \
netbase vim-tiny"

mkdir -p "$OUT_DIR"
if [[ $(id -u) -eq 0 ]]; then
  RM=()
else
  RM=(sudo -n)
fi
"${RM[@]}" rm -rf "$ROOTFS_DIR" "$TARBALL_PATH" "$TARBALL_PATH.sha256"

docker_usable=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker_usable=1
fi

if [[ "$docker_usable" == "1" ]]; then
  BUILD_DIR="$(mktemp -d)"
  cat > "$BUILD_DIR/Dockerfile" <<EOF
FROM debian:$SUITE-slim
RUN apt-get update && apt-get install -y --no-install-recommends \\
    $(echo "$PACKAGES" | tr '\n' ' ') && rm -rf /var/lib/apt/lists/*
EOF

  docker build -t zaod-rootfs-builder "$BUILD_DIR" >/dev/null
  docker create --name zaod-rootfs-builder-container zaod-rootfs-builder >/dev/null
  docker export zaod-rootfs-builder-container -o "$TARBALL_PATH"
  docker rm -f zaod-rootfs-builder-container >/dev/null 2>&1 || true
  rm -rf "$BUILD_DIR"
else
  # No usable Docker: fall back to the Debian bootstrap tools from
  # scripts/setup-tools.sh, which the PRD names as the base-image method.
  include=$(echo "$PACKAGES" | tr '\n' ',' | sed 's/,$//')
  if command -v mmdebstrap >/dev/null 2>&1; then
    printf 'Docker unavailable: building the %s rootfs with mmdebstrap.\n' "$SUITE"
    "${RM[@]}" mmdebstrap --variant=apt --include="$include" "$SUITE" "$ROOTFS_DIR" "$MIRROR"
  elif command -v debootstrap >/dev/null 2>&1; then
    printf 'Docker unavailable: building the %s rootfs with debootstrap.\n' "$SUITE"
    "${RM[@]}" debootstrap --variant=minbase --include="$include" "$SUITE" "$ROOTFS_DIR" "$MIRROR"
  else
    printf 'No rootfs build backend available: install docker, mmdebstrap or debootstrap.\n' >&2
    exit 1
  fi
  "${RM[@]}" tar -C "$ROOTFS_DIR" -cf "$TARBALL_PATH" .
fi

sha256sum "$TARBALL_PATH" > "$TARBALL_PATH.sha256"
ls -lh "$TARBALL_PATH"
printf 'Root filesystem tarball created: %s\n' "$TARBALL_PATH"
