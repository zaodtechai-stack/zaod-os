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
export DEBIAN_FRONTEND=noninteractive

cd "$(dirname "${BASH_SOURCE[0]}")/.."

ROOTFS_DIR="${ROOTFS_DIR:-build/rootfs}"
OUT_DIR="${OUT_DIR:-build/out}"
SQUASHFS="${SQUASHFS:-$OUT_DIR/zaod-rootfs.squashfs}"
ROOTFS_TARBALL="${ROOTFS_TARBALL:-$OUT_DIR/zaod-rootfs.tar}"
KERNEL_OUT="${KERNEL_OUT:-$OUT_DIR/kernel}"
SQUASH_LEVEL="${SQUASH_LEVEL:-19}"
DEBIAN_SUITE="${DEBIAN_SUITE:-trixie}"
# A host keyring older than the suite being bootstrapped cannot verify its
# InRelease file; point this at a current debian-archive-keyring when needed.
DEBIAN_KEYRING="${DEBIAN_KEYRING:-}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-https://deb.debian.org/debian}"
MAX_UNCOMPRESSED_MB="${MAX_UNCOMPRESSED_MB:-3584}"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1794700800}"
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

# Kernel source: Phase 2 artifacts when they exist, otherwise the kernel the
# installed packages provide (linux-image-amd64). Building the kernel from
# source needs a toolchain and hours; a released image must not depend on that.
KERNEL_SOURCE="phase2"
if [[ -s "$KERNEL_OUT/vmlinuz" && -s "$KERNEL_OUT/modules.tar.gz" ]]; then
  mapfile -t kernel_releases < <(tar -tzf "$KERNEL_OUT/modules.tar.gz" \
    | sed -n 's#^\./lib/modules/\([^/]*\)/.*#\1#p' | LC_ALL=C sort -u)
  (( ${#kernel_releases[@]} == 1 )) || fail "expected one kernel release in modules.tar.gz"
  KERNEL_RELEASE="${kernel_releases[0]}"
else
  KERNEL_SOURCE="packages"
  KERNEL_RELEASE=""
  grep -qx 'linux-image-amd64' "$PACKAGE_LIST" \
    || fail "no Phase 2 kernel and linux-image-amd64 is not in $PACKAGE_LIST"
fi

printf '[rootfs] inputs ok\n  builder     %s\n  suite       %s\n  packages    %d\n  removal     %d paths\n  squashfs    %s (zstd level %s)\n' \
  "$BUILDER" "$DEBIAN_SUITE" "${#packages[@]}" "${#removals[@]}" "$SQUASHFS" "$SQUASH_LEVEL"

if (( CHECK )); then
  printf '[rootfs] --check done, nothing written\n'
  exit 0
fi

(( EUID == 0 )) || say "not root: privileged steps run through sudo -n"
if (( EUID != 0 )); then
  sudo -n true >/dev/null 2>&1 || fail "rootfs build needs root or working sudo -n"
fi
mount_probe="$(mktemp -d)"
if ! as_root mount -t tmpfs tmpfs "$mount_probe" >/dev/null 2>&1; then
  rmdir "$mount_probe" 2>/dev/null || true
  fail "this host denies privileged mounts; use a Docker-capable or mount-capable build host"
fi
as_root umount "$mount_probe"
rmdir "$mount_probe"

# ---------------------------------------------------------------- 1. debootstrap
say "building a $DEBIAN_SUITE base in $ROOTFS_DIR"
as_root rm -rf "$ROOTFS_DIR"
mkdir -p "$ROOTFS_DIR" build

printf '%s\n' "${packages[@]}" > build/packages.resolved.txt
INCLUDE="$(paste -sd, build/packages.resolved.txt)"
if [[ "$BUILDER" == "mmdebstrap" ]]; then
  as_root mmdebstrap \
    ${DEBIAN_KEYRING:+--keyring="$DEBIAN_KEYRING"} \
    --variant=important \
    --include="$INCLUDE" \
    --components=main,contrib,non-free-firmware \
    --aptopt='APT::Install-Recommends "false";' \
    "$DEBIAN_SUITE" "$ROOTFS_DIR" "$DEBIAN_MIRROR"
else
  as_root debootstrap ${DEBIAN_KEYRING:+--keyring="$DEBIAN_KEYRING"} --variant=minbase --components=main,contrib,non-free-firmware \
    --include="$INCLUDE" \
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
as_root bash desktop/scripts/apply-desktop.sh --root "$ROOTFS_DIR"
as_root mkdir -p "$ROOTFS_DIR/usr/share/zaod/design" \
  "$ROOTFS_DIR/usr/share/wallpapers/zaod" \
  "$ROOTFS_DIR/usr/share/themes/Zaod"
as_root cp -a desktop/design/. "$ROOTFS_DIR/usr/share/zaod/design/"
as_root cp -a desktop/design/wallpapers/. "$ROOTFS_DIR/usr/share/wallpapers/zaod/"
as_root cp -a desktop/design/gtk/. "$ROOTFS_DIR/usr/share/themes/Zaod/"

# The default user template is a skel the installer copies, not a login.
as_root mkdir -p "$ROOTFS_DIR/etc/skel/.config"
cat <<'SKEL' | as_root tee "$ROOTFS_DIR/etc/skel/.profile" >/dev/null
# Zaod OS default shell profile
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi
export XDG_CURRENT_DESKTOP=KDE
SKEL
as_root chmod 0644 "$ROOTFS_DIR/etc/skel/.profile"

# ---------------------------------------------------------------- 3. kernel
if [[ "$KERNEL_SOURCE" == "packages" ]]; then
  # The package manager already placed the kernel, its modules and the firmware
  # in the root. Record them where the ISO and the initramfs tools look for a
  # Phase 2 kernel, so the rest of the pipeline is source-agnostic.
  KERNEL_RELEASE="$(basename "$(find "$ROOTFS_DIR/lib/modules" -maxdepth 1 -mindepth 1 \
    -type d | LC_ALL=C sort | tail -n 1)")"
  [[ -n "$KERNEL_RELEASE" ]] || fail "no kernel modules found in the rootfs"
  say "no Phase 2 kernel artifacts: using packaged kernel $KERNEL_RELEASE"
  as_root install -d "$KERNEL_OUT"
  for artifact in "vmlinuz:$ROOTFS_DIR/boot/vmlinuz-$KERNEL_RELEASE" \
                  "System.map:$ROOTFS_DIR/boot/System.map-$KERNEL_RELEASE" \
                  "config:$ROOTFS_DIR/boot/config-$KERNEL_RELEASE"; do
    name="${artifact%%:*}"; source_path="${artifact#*:}"
    if [[ -f "$source_path" ]]; then
      cp -f "$source_path" "$KERNEL_OUT/$name"
    fi
  done
  if [[ ! -s "$KERNEL_OUT/vmlinuz" ]]; then
    fail "packaged kernel $KERNEL_RELEASE has no vmlinuz in /boot"
  fi
  tar -czf "$KERNEL_OUT/modules.tar.gz" -C "$ROOTFS_DIR" "./lib/modules/$KERNEL_RELEASE"
  if [[ -d "$ROOTFS_DIR/lib/firmware" ]]; then
    tar -cJf "$KERNEL_OUT/firmware.tar.xz" -C "$ROOTFS_DIR" ./lib/firmware
  fi
  printf 'packaged kernel %s from the Debian %s archive\n' \
    "$KERNEL_RELEASE" "$DEBIAN_SUITE" > "$KERNEL_OUT/firmware-source-commit.txt"
  as_root depmod -a -b "$ROOTFS_DIR" "$KERNEL_RELEASE" || true
else
say "installing Phase 2 kernel $KERNEL_RELEASE, modules and pinned firmware"
as_root install -d "$ROOTFS_DIR/boot" "$ROOTFS_DIR/lib/firmware"
as_root install -m 0644 "$KERNEL_OUT/vmlinuz" "$ROOTFS_DIR/boot/vmlinuz-$KERNEL_RELEASE"
as_root install -m 0644 "$KERNEL_OUT/System.map" "$ROOTFS_DIR/boot/System.map-$KERNEL_RELEASE"
as_root tar -xzf "$KERNEL_OUT/modules.tar.gz" -C "$ROOTFS_DIR"
as_root depmod -a -b "$ROOTFS_DIR" "$KERNEL_RELEASE"
as_root tar -xJf "$KERNEL_OUT/firmware.tar.xz" -C "$ROOTFS_DIR/lib/firmware"
as_root mkdir -p "$ROOTFS_DIR/usr/share/zaod/licenses/linux-firmware"
for notice in LICENSE LICENSE-CRITERIA.md WHENCE; do
  if [[ -f "$ROOTFS_DIR/lib/firmware/$notice" ]]; then
    as_root cp "$ROOTFS_DIR/lib/firmware/$notice" \
      "$ROOTFS_DIR/usr/share/zaod/licenses/linux-firmware/$notice"
  fi
done
if [[ -d "$ROOTFS_DIR/lib/firmware/LICENSES" ]]; then
  as_root cp -a "$ROOTFS_DIR/lib/firmware/LICENSES" \
    "$ROOTFS_DIR/usr/share/zaod/licenses/linux-firmware/"
fi
as_root install -m 0644 "$KERNEL_OUT/firmware-source-commit.txt" \
  "$ROOTFS_DIR/usr/share/zaod/licenses/linux-firmware/source-commit.txt"
fi

# The initramfs must be generated before package management is removed.
say "generating initramfs for $KERNEL_RELEASE"
CHROOT_MOUNTS=()
cleanup_chroot_mounts() {
  local index
  for ((index=${#CHROOT_MOUNTS[@]} - 1; index >= 0; index--)); do
    as_root umount -R "$ROOTFS_DIR/${CHROOT_MOUNTS[index]}" >/dev/null 2>&1 || true
  done
}
trap cleanup_chroot_mounts EXIT
for pseudo in dev proc sys run; do
  as_root mount --rbind "/$pseudo" "$ROOTFS_DIR/$pseudo"
  as_root mount --make-rslave "$ROOTFS_DIR/$pseudo"
  CHROOT_MOUNTS+=("$pseudo")
done
as_root chroot "$ROOTFS_DIR" /usr/sbin/update-initramfs -c -k "$KERNEL_RELEASE"
cleanup_chroot_mounts
trap - EXIT
as_root chroot "$ROOTFS_DIR" /usr/bin/systemctl --root=/ enable NetworkManager.service \
  earlyoom.service systemd-timesyncd.service sddm.service zaod-lite-mode.service
if ! as_root chroot "$ROOTFS_DIR" /usr/bin/getent group wheel >/dev/null 2>&1; then
  as_root chroot "$ROOTFS_DIR" /usr/sbin/groupadd --system wheel
fi
for group in audio video render input netdev; do
  if ! as_root chroot "$ROOTFS_DIR" /usr/bin/getent group "$group" >/dev/null 2>&1; then
    as_root chroot "$ROOTFS_DIR" /usr/sbin/groupadd --system "$group"
  fi
done
if ! as_root chroot "$ROOTFS_DIR" /usr/bin/getent passwd zaodlive >/dev/null 2>&1; then
  as_root chroot "$ROOTFS_DIR" /usr/sbin/useradd --create-home --shell /bin/bash \
    --groups wheel,audio,video,render,input,netdev zaodlive
fi
as_root chroot "$ROOTFS_DIR" /usr/sbin/passwd --lock zaodlive >/dev/null

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

for binary in apt apt-get apt-cache apt-config aptitude dpkg dpkg-query dpkg-deb; do
  if as_root chroot "$ROOTFS_DIR" /bin/sh -c "command -v $binary" >/dev/null 2>&1; then
    fail "$binary is still on PATH inside the rootfs"
  fi
done
for library in apt-pkg apt-private dpkg; do
  while IFS= read -r -d '' path; do
    as_root rm -f "$path"
  done < <(find "$ROOTFS_DIR/usr/lib" -type f -name "lib${library}.so*" -print0 2>/dev/null || true)
done
for database in /etc/apt /var/lib/apt /var/lib/dpkg; do
  [[ ! -e "$ROOTFS_DIR$database" ]] || fail "package manager database remains: $database"
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
  -noappend -all-root -no-progress
as_root chown "$(id -u):$(id -g)" "$SQUASHFS" 2>/dev/null || true

say "writing reproducible rootfs tarball"
as_root tar -C "$ROOTFS_DIR" --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
  --numeric-owner --owner=0 --group=0 --format=posix -cf "$ROOTFS_TARBALL" .
as_root chown "$(id -u):$(id -g)" "$ROOTFS_TARBALL" 2>/dev/null || true
sha256sum "$ROOTFS_TARBALL" > "$ROOTFS_TARBALL.sha256"
sha256sum "$SQUASHFS" > "$SQUASHFS.sha256"

squash_mb=$(( $(stat -c %s "$SQUASHFS") / 1024 / 1024 ))
mkdir -p build/logs
{
  printf 'rootfs report\n'
  printf 'date: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'suite: %s\n' "$DEBIAN_SUITE"
  printf 'packages: %d\n' "${#packages[@]}"
  printf 'kernel: %s\n' "$KERNEL_RELEASE"
  printf 'uncompressed: %s MB\n' "$uncompressed_mb"
  printf 'rootfs tar: %s\n' "$ROOTFS_TARBALL"
  printf 'rootfs tar sha256: %s\n' "$(cut -d' ' -f1 "$ROOTFS_TARBALL.sha256")"
  printf 'squashfs: %s MB (zstd level %s)\n' "$squash_mb" "$SQUASH_LEVEL"
  printf 'squashfs sha256: %s\n' "$(cut -d' ' -f1 "$SQUASHFS.sha256")"
  printf 'package manager: removed and verified absent\n'
} | tee build/logs/rootfs-report.txt

say "wrote $SQUASHFS (${squash_mb} MB)"
