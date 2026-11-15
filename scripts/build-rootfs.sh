#!/usr/bin/env bash
# Build the Zaod OS root filesystem.
#
#   scripts/build-rootfs.sh --check    # validate inputs on this host, write nothing
#   sudo scripts/build-rootfs.sh       # build, strip, de-package and squash
#
# Stages, in order:
#   1. debootstrap a Debian trixie base from rootfs/packages.list
#   2. install the Zaod configuration files from rootfs/files
#   3. install the Phase 2 kernel, modules and firmware from build/out
#   4. export the SBOM and the licence texts to /usr/share/zaod
#   5. strip documentation, manuals and unused locales
#   6. remove the Debian package manager and hard-fail if anything survives
#   7. squash the result with zstd level 19 and report sizes
#
# Nothing here is reversible: the target directory is deleted first.
set -euo pipefail
IFS=$'\n\t'

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ROOTFS_DIR="${ROOTFS_DIR:-build/rootfs}"
OUT_DIR="${OUT_DIR:-build/out}"
SQUASHFS="${SQUASHFS:-$OUT_DIR/zaod-rootfs.squashfs}"
SQUASH_LEVEL="${SQUASH_LEVEL:-19}"
DEBIAN_SUITE="${DEBIAN_SUITE:-trixie}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"
MAX_UNCOMPRESSED_MB="${MAX_UNCOMPRESSED_MB:-3584}"
PACKAGE_LIST="rootfs/packages.list"
REMOVE_LIST="rootfs/rootfs.remove.list"
FILES_DIR="rootfs/files"
CHECK=0

[[ "${1:-}" == "--check" ]] && CHECK=1

say() { printf '\033[1;36m[rootfs]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[rootfs] %s\033[0m\n' "$*" >&2; exit 1; }

as_root() {
  if (( EUID == 0 )); then "$@"; else sudo -n "$@"; fi
}

# Inside the target root, paths are absolute. This helper removes directory
# contents without ever touching the build host, because it only runs chrooted.
strip_inside() {
  # shellcheck disable=SC2016  # this script runs inside the target root
  as_root chroot "$ROOTFS_DIR" /bin/sh -c '
    export PATH=/usr/sbin:/usr/bin:/sbin:/bin
    for range in /usr/share/doc /usr/share/man /usr/share/info /usr/share/lintian \
                 /usr/share/gtk-doc /var/cache/apt /var/lib/apt/lists; do
      [ -d "$range" ] && find "$range" -mindepth 1 -delete 2>/dev/null
    done
    for locale_dir in /usr/share/locale/*; do
      [ -d "$locale_dir" ] || continue
      case "$(basename "$locale_dir")" in
        en|en_US|en_GB|C|POSIX) continue ;;
      esac
      find "$locale_dir" -mindepth 1 -delete 2>/dev/null
      rmdir "$locale_dir" 2>/dev/null || true
    done
    [ -f /var/lib/dpkg/status-old ] && rm -f /var/lib/dpkg/status-old
    exit 0
  '
}

# ---------------------------------------------------------------- input checks
command -v mksquashfs >/dev/null || fail "mksquashfs is missing (install squashfs-tools)"
BUILDER=""
for candidate in mmdebstrap debootstrap; do
  if command -v "$candidate" >/dev/null; then BUILDER="$candidate"; break; fi
done
[[ -n "$BUILDER" ]] || fail "need mmdebstrap or debootstrap on the build host"

[[ -f "$PACKAGE_LIST" ]] || fail "$PACKAGE_LIST is missing"
[[ -f "$REMOVE_LIST" ]] || fail "$REMOVE_LIST is missing"
[[ -d "$FILES_DIR" ]] || fail "$FILES_DIR is missing"

mapfile -t packages < <(grep -vE '^[[:space:]]*(#|$)' "$PACKAGE_LIST")
(( ${#packages[@]} > 0 )) || fail "the package list is empty"

mapfile -t removals < <(grep -vE '^[[:space:]]*(#|$)' "$REMOVE_LIST")
(( ${#removals[@]} > 0 )) || fail "the removal list is empty"

for required in systemd dbus network-manager pipewire wireplumber mesa-vulkan-drivers \
                plasma-desktop sddm polkitd bubblewrap zram-generator earlyoom python3; do
  printf '%s\n' "${packages[@]}" | grep -qx "$required" \
    || fail "the package list is missing $required"
done

for required in /usr/bin/apt /usr/bin/dpkg /var/lib/dpkg /var/lib/apt /etc/apt; do
  printf '%s\n' "${removals[@]}" | grep -qx "$required" \
    || fail "the removal list does not cover $required"
done

[[ -f "$FILES_DIR/etc/os-release" ]] || fail "$FILES_DIR/etc/os-release is missing"
grep -qx 'ID=zaod' "$FILES_DIR/etc/os-release" || fail "os-release does not identify Zaod OS"
grep -q 'NAME="Zaod OS"' "$FILES_DIR/etc/os-release" || fail "os-release name is wrong"

printf '[rootfs] inputs ok\n  builder     %s\n  suite       %s\n  packages    %d\n  removal     %d paths\n  squashfs    %s (zstd level %s)\n' \
  "$BUILDER" "$DEBIAN_SUITE" "${#packages[@]}" "${#removals[@]}" "$SQUASHFS" "$SQUASH_LEVEL"

if (( CHECK )); then
  printf '[rootfs] --check done, nothing written\n'
  exit 0
fi

(( EUID == 0 )) || say "not root: privileged steps run through sudo -n"

# ---------------------------------------------------------------- 1. debootstrap
say "building a $DEBIAN_SUITE base in $ROOTFS_DIR"
as_root rm -rf "$ROOTFS_DIR"
mkdir -p "$ROOTFS_DIR" build

printf '%s\n' "${packages[@]}" > build/packages.resolved.txt
INCLUDE="$(paste -sd, build/packages.resolved.txt)"
if [[ "$BUILDER" == "mmdebstrap" ]]; then
  as_root mmdebstrap \
    --variant=important \
    --include="$INCLUDE" \
    --components=main,contrib,non-free-firmware \
    --apt-options="--no-install-recommends" \
    "$DEBIAN_SUITE" "$ROOTFS_DIR" "$DEBIAN_MIRROR"
else
  as_root debootstrap --variant=minbase --include="$INCLUDE" \
    "$DEBIAN_SUITE" "$ROOTFS_DIR" "$DEBIAN_MIRROR"
fi

# ---------------------------------------------------------------- 2. Zaod files
say "installing Zaod configuration files"
as_root mkdir -p "$ROOTFS_DIR"/etc "$ROOTFS_DIR"/usr/share/zaod/licenses \
  "$ROOTFS_DIR"/var/lib/zaod/keys "$ROOTFS_DIR"/usr/share/plymouth/themes
as_root cp -a "$FILES_DIR"/. "$ROOTFS_DIR"/
as_root install -m 0644 "$FILES_DIR/etc/default-locale" "$ROOTFS_DIR/etc/default/locale"
as_root install -m 0440 "$FILES_DIR/etc/sudoers.d/zaod-desktop" "$ROOTFS_DIR/etc/sudoers.d/zaod-desktop"
as_root chmod 0755 "$ROOTFS_DIR/etc/sudoers.d"
as_root cp -a boot/plymouth "$ROOTFS_DIR/usr/share/plymouth/themes/zaod"

# The default user template is a skel the installer copies, not a login.
as_root mkdir -p "$ROOTFS_DIR/etc/skel/.config"
cat <<'SKEL' | as_root tee "$ROOTFS_DIR/etc/skel/.profile" >/dev/null
# Zaod OS default shell profile
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi
export XDG_CURRENT_DESKTOP=KDE
SKEL
as_root chmod 0644 "$ROOTFS_DIR/etc/skel/.profile"

# ---------------------------------------------------------------- 3. kernel
if [[ -f "$OUT_DIR/vmlinuz" ]]; then
  say "installing the Phase 2 kernel, modules and firmware"
  as_root install -m 0644 "$OUT_DIR/vmlinuz" "$ROOTFS_DIR/boot/vmlinuz"
  for tree in lib/modules lib/firmware; do
    if [[ -d "$OUT_DIR/$tree" ]]; then
      as_root mkdir -p "$ROOTFS_DIR/$tree"
      as_root cp -a "$OUT_DIR/$tree/." "$ROOTFS_DIR/$tree/"
    fi
  done
else
  say "warning: $OUT_DIR/vmlinuz is absent, this rootfs ships without a kernel (run 'make kernel' first)"
fi

# ---------------------------------------------------------------- 4. SBOM
say "exporting the SBOM and licence texts"
# shellcheck disable=SC2016  # variables here belong to the chroot, not the host
as_root chroot "$ROOTFS_DIR" /bin/sh -c '
  export PATH=/usr/sbin:/usr/bin:/sbin:/bin
  {
    printf "Zaod OS software bill of materials\n"
    printf "generated: %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf "package\tversion\tarchitecture\tmaintainer\n"
    dpkg-query -W -f="\${Package}\t\${Version}\t\${Architecture}\t\${Maintainer}\n" | sort
  } > /usr/share/zaod/sbom.txt
  mkdir -p /usr/share/zaod/licenses
  for pkg in $(dpkg-query -W -f="\${Package}\n"); do
    if [ -f "/usr/share/doc/$pkg/copyright" ]; then
      cp "/usr/share/doc/$pkg/copyright" "/usr/share/zaod/licenses/$pkg.txt" 2>/dev/null || true
    fi
  done
  printf "packages: %s\nlicence files: %s\n" \
    "$(dpkg-query -W -f="\${Package}\n" | wc -l)" \
    "$(find /usr/share/zaod/licenses -type f | wc -l)" >> /usr/share/zaod/sbom.txt
'

# ---------------------------------------------------------------- 5. strip
say "stripping documentation, manuals and unused locales"
strip_inside

# ---------------------------------------------------------------- 6. remove apt/dpkg
say "removing the Debian package manager"
while IFS= read -r path; do
  case "$path" in ''|'#'*) continue ;; esac
  as_root rm -rf "${ROOTFS_DIR:?}${path}"
done < "$REMOVE_LIST"

survivors=()
while IFS= read -r path; do
  case "$path" in ''|'#'*) continue ;; esac
  [[ -e "${ROOTFS_DIR}${path}" ]] && survivors+=("$path")
done < "$REMOVE_LIST"
(( ${#survivors[@]} == 0 )) || fail "the package manager survived removal: ${survivors[*]}"

for binary in apt apt-get apt-cache dpkg dpkg-query dpkg-deb; do
  if as_root chroot "$ROOTFS_DIR" /bin/sh -c "command -v $binary" >/dev/null 2>&1; then
    fail "$binary is still on PATH inside the rootfs"
  fi
done
say "apt, apt-get and dpkg are gone and their databases are absent"

# ---------------------------------------------------------------- 7. squash
uncompressed_kb="$(as_root du -sk "$ROOTFS_DIR" | cut -f1)"
uncompressed_mb=$(( uncompressed_kb / 1024 ))
say "uncompressed rootfs: ${uncompressed_mb} MB (limit ${MAX_UNCOMPRESSED_MB} MB)"
(( uncompressed_mb <= MAX_UNCOMPRESSED_MB )) \
  || fail "the rootfs exceeds the size budget: ${uncompressed_mb} MB > ${MAX_UNCOMPRESSED_MB} MB"

mkdir -p "$OUT_DIR"
say "squashing with zstd level $SQUASH_LEVEL"
as_root rm -f "$SQUASHFS"
as_root mksquashfs "$ROOTFS_DIR" "$SQUASHFS" \
  -comp zstd -Xcompression-level "$SQUASH_LEVEL" \
  -noappend -all-root -no-progress -wildcards \
  -e 'boot/vmlinuz' -e 'lib/modules/*' -e 'lib/firmware/*'
as_root chown "$(id -u):$(id -g)" "$SQUASHFS" 2>/dev/null || true

squash_mb=$(( $(stat -c %s "$SQUASHFS") / 1024 / 1024 ))
mkdir -p build/logs
{
  printf 'rootfs report\n'
  printf 'date: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'suite: %s\n' "$DEBIAN_SUITE"
  printf 'packages: %d\n' "${#packages[@]}"
  printf 'uncompressed: %s MB\n' "$uncompressed_mb"
  printf 'squashfs: %s MB (zstd level %s)\n' "$squash_mb" "$SQUASH_LEVEL"
  printf 'package manager: removed and verified absent\n'
} | tee build/logs/rootfs-report.txt

say "wrote $SQUASHFS (${squash_mb} MB)"
