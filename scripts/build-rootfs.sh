#!/usr/bin/env bash
# Build the minimal Debian trixie rootfs artifact (PRD phase 3 evidence).
#
# The runtime image must not carry distro package management, so the requested
# package set is recorded as evidence and apt/dpkg are stripped from the image
# before the tarball is produced. The tarball is then checked again, because a
# rootfs that still contains apt is not a Zaod rootfs.
set -euo pipefail

ROOTFS_DIR="${ROOTFS_DIR:-/tmp/zaod-rootfs-minimal}"
OUT_DIR="${OUT_DIR:-build/out}"
TARBALL_PATH="${TARBALL_PATH:-$OUT_DIR/zaod-trixie-rootfs-minimal.tar}"
SUITE="${SUITE:-trixie}"
MIRROR="${MIRROR:-https://deb.debian.org/debian}"
PACKAGES="apt bash ca-certificates coreutils curl dbus findutils grep gzip iproute2
less openssl procps python3 sed systemd systemd-sysv tar tzdata util-linux xz-utils
netbase vim-tiny"

# Everything Debian package management needs, and nothing the runtime needs.
STRIP_PATHS="/usr/bin/apt /usr/bin/apt-get /usr/bin/apt-cache /usr/bin/apt-config
/usr/bin/apt-mark /usr/bin/dpkg /usr/bin/dpkg-deb /usr/bin/dpkg-divert /usr/bin/dpkg-query
/usr/bin/dpkg-split /usr/bin/dpkg-statoverride /usr/bin/dpkg-trigger /usr/sbin/dpkg-preconfigure
/etc/apt /var/lib/apt /var/lib/dpkg /var/cache/apt /usr/lib/apt"

mkdir -p "$OUT_DIR"

if [[ $(id -u) -eq 0 ]]; then
  RM=()
else
  RM=(sudo -n)
fi

"${RM[@]}" rm -rf "$ROOTFS_DIR" "$TARBALL_PATH" "$TARBALL_PATH.sha256"

# Evidence: what the image was asked to contain, before anything is stripped.
{
  printf 'suite: %s\n' "$SUITE"
  printf 'mirror: %s\n' "$MIRROR"
  printf 'packages:\n'
  # shellcheck disable=SC2086  # the package list is intentionally split into lines
  printf '%s\n' $PACKAGES
} > "$OUT_DIR/rootfs-packages.txt"

strip_in_tree() {
  local root=$1
  local path
  local remove=("${RM[@]}")
  for path in $STRIP_PATHS; do
    "${remove[@]}" rm -rf "${root:?}$path"
  done
}

verify_no_package_manager() {
  local root=$1
  local found
  found=$(find "$root" -maxdepth 3 \
    \( -name apt -o -name apt-get -o -name dpkg -o -name dpkg-query \) 2>/dev/null || true)
  if [ -n "$found" ] || [ -e "$root/var/lib/dpkg/status" ]; then
    printf 'Rootfs still contains distro package management:\n%s\n' "$found" >&2
    exit 1
  fi
  printf 'Verified: no apt or dpkg in the rootfs image.\n'
}

docker_usable=0
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker_usable=1
fi

if [[ "$docker_usable" == "1" ]]; then
  BUILD_DIR="$(mktemp -d)"
  # shellcheck disable=SC2086,SC2016  # the package and path lists are words for the Dockerfile
  {
    printf 'FROM debian:%s-slim\n' "$SUITE"
    printf 'RUN apt-get update && apt-get install -y --no-install-recommends %s && rm -rf /var/lib/apt/lists/*\n' \
      "$(printf '%s ' $PACKAGES)"
    printf 'RUN for path in %s; do rm -rf "$path"; done\n' "$(printf '%s ' $STRIP_PATHS)"
  } > "$BUILD_DIR/Dockerfile"

  docker build -t zaod-rootfs-builder "$BUILD_DIR" >/dev/null
  docker create --name zaod-rootfs-builder-container zaod-rootfs-builder >/dev/null
  docker export zaod-rootfs-builder-container -o "$TARBALL_PATH"
  docker rm -f zaod-rootfs-builder-container >/dev/null 2>&1 || true
  rm -rf "$BUILD_DIR"
else
  # No usable Docker: fall back to the Debian bootstrap tools from
  # scripts/setup-tools.sh, which the PRD names as the base-image method.
  # shellcheck disable=SC2086  # comma list needs the packages split into words
  include=$(printf '%s\n' $PACKAGES | paste -sd, -)
  # debootstrap and mmdebstrap need privileged mounts inside the target, so fail
  # early with a readable reason instead of leaving a half-built directory.
  if [[ $(id -u) -ne 0 ]]; then
    printf 'Rootfs bootstrap needs root (or Docker); re-run with sudo.\n' >&2
    exit 1
  fi
  probe=$(mktemp -d)
  if ! mount -t tmpfs tmpfs "$probe" >/dev/null 2>&1; then
    rmdir "$probe" 2>/dev/null || true
    printf 'This host denies privileged mounts, so chroot/proc inside the target image cannot be mounted.\n' >&2
    printf 'Build the rootfs on a host or CI runner with mount privileges, or install Docker.\n' >&2
    exit 1
  fi
  umount "$probe" >/dev/null 2>&1 || true
  rmdir "$probe" 2>/dev/null || true
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
  strip_in_tree "$ROOTFS_DIR"
  verify_no_package_manager "$ROOTFS_DIR"
  "${RM[@]}" tar -C "$ROOTFS_DIR" -cf "$TARBALL_PATH" .
fi

# Final gate: whichever backend ran, the tarball itself must be clean.
if tar -tf "$TARBALL_PATH" | grep -Eq '(^|/)(usr/bin/(apt|apt-get|dpkg|dpkg-query)|var/lib/dpkg/status)$'; then
  printf 'Rootfs tarball still contains apt or dpkg; refusing to publish it.\n' >&2
  exit 1
fi

sha256sum "$TARBALL_PATH" > "$TARBALL_PATH.sha256"
ls -lh "$TARBALL_PATH"
printf 'Root filesystem tarball created: %s\n' "$TARBALL_PATH"
printf 'Package set recorded in %s/rootfs-packages.txt\n' "$OUT_DIR"
