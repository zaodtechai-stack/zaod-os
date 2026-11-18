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
# Live media credentials. The account exists only on the live image; the
# installer deletes it. Keep these in step with docs/desktop.md and /etc/issue.
LIVE_USER="${LIVE_USER:-zaodlive}"
LIVE_PASSWORD="${LIVE_PASSWORD:-zaod}"

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

# The desktop is Zaod's own: labwc is the compositor and the panel/app set come
# from desktop/ and apps/, so no Plasma package belongs in this list.
for required in systemd dbus network-manager pipewire wireplumber mesa-vulkan-drivers \
                labwc sddm polkitd bubblewrap zram-tools earlyoom python3 \
                python3-pyside6.qtwidgets hicolor-icon-theme librsvg2-common; do
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

# The image ships the Zaod kernel built from source (kernel/build.sh). A
# distribution kernel is not a fallback: the released image must report
# `uname -r` = 6.18.x-zaod, so a missing kernel artifact is a build failure
# rather than a silent downgrade to whatever the archive ships.
KERNEL_RELEASE=""
missing=()
for artifact in vmlinuz modules.tar.gz firmware.tar.xz; do
  [[ -s "$KERNEL_OUT/$artifact" ]] || missing+=("$KERNEL_OUT/$artifact")
done
(( ${#missing[@]} == 0 )) \
  || fail "no Zaod kernel to install: ${missing[*]} is missing; run scripts/fetch.sh, then make kernel"
mapfile -t kernel_releases < <(tar -tzf "$KERNEL_OUT/modules.tar.gz" \
  | sed -n 's#^\./lib/modules/\([^/]*\)/.*#\1#p' | LC_ALL=C sort -u)
(( ${#kernel_releases[@]} == 1 )) || fail "expected one kernel release in modules.tar.gz"
KERNEL_RELEASE="${kernel_releases[0]}"

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
# The app set, with the .desktop entry for each app the image ships. Without
# this the session starts on an empty desktop: the launcher and the store both
# read /usr/share/applications.
as_root python3 scripts/install-app-set.py --root "$ROOTFS_DIR"
# The built-in web apps: YouTube, WhatsApp, Instagram, Facebook, TikTok and X as
# launcher entries that open in their own Chromium window.
# The web apps and Studio are optional: they are staged so the store can add them
# per person, and nothing social lands in a launcher by default.
as_root python3 scripts/install-web-apps.py --root "$ROOTFS_DIR" --optional
as_root mkdir -p "$ROOTFS_DIR/usr/share/zaod"
as_root install -m 0644 desktop/webapps/webapps.json "$ROOTFS_DIR/usr/share/zaod/webapps.json"

# The Zaod package system the Store and the `zaod` CLI read. Without
# /usr/lib/zaod/zaodlib the store refuses to start at all ("zaodlib is not
# installed; the store needs a Zaod system"), which is one of the apps that did
# nothing when clicked.
as_root mkdir -p "$ROOTFS_DIR/usr/lib/zaod" "$ROOTFS_DIR/etc/zaod/keys" \
  "$ROOTFS_DIR/var/lib/zaod" "$ROOTFS_DIR/zaod/apps"
as_root cp -a zaod/zaodlib "$ROOTFS_DIR/usr/lib/zaod/zaodlib"
# The panel and Control Center share one network layer, so they cannot disagree
# about what nmcli said.
as_root install -m 0644 apps/lib/connectivity.py "$ROOTFS_DIR/usr/lib/zaod/connectivity.py"
# The local backend every app signs into: accounts, Studio projects, the store's
# per-user install list. It runs over a Unix socket, so no port is opened.
as_root install -m 0755 services/zaod-hub/hub.py "$ROOTFS_DIR/usr/local/bin/zaod-hub"
as_root install -m 0644 apps/lib/zaodhub.py "$ROOTFS_DIR/usr/lib/zaod/zaodhub.py"
# The account window the store and Studio share: sign in, sync, sign out.
as_root install -m 0644 apps/lib/zaodaccount.py "$ROOTFS_DIR/usr/lib/zaod/zaodaccount.py"
# Receiving updates: the channel is a release asset, so a fix reaches an installed
# system without a new ISO and without touching anyone's data.
as_root install -m 0755 services/zaod-update/update.py "$ROOTFS_DIR/usr/local/bin/zaod-update"
# The hosted half: sign in to the Supabase-backed account to back this computer up
# and use the same account on a second one. Local files stay the truth offline.
as_root install -m 0755 services/zaod-cloud/cloud.py "$ROOTFS_DIR/usr/local/bin/zaod-cloud"
# The same client as an importable module, for the store and Studio windows.
as_root install -m 0644 services/zaod-cloud/cloud.py "$ROOTFS_DIR/usr/lib/zaod/zaod_cloud.py"
as_root install -D -m 0644 rootfs/files/etc/zaod/update-channel.json \
  "$ROOTFS_DIR/etc/zaod/update-channel.json"
as_root install -m 0755 zaod/bin/zaod "$ROOTFS_DIR/usr/bin/zaod"
as_root install -m 0755 zaod/bin/zaod-priv-helper "$ROOTFS_DIR/usr/lib/zaod/zaod-priv-helper"
as_root mkdir -p "$ROOTFS_DIR/usr/share/zaod/design" \
  "$ROOTFS_DIR/usr/share/wallpapers/zaod" \
  "$ROOTFS_DIR/usr/share/themes/Zaod"
as_root cp -a desktop/design/. "$ROOTFS_DIR/usr/share/zaod/design/"
as_root cp -a desktop/design/wallpapers/. "$ROOTFS_DIR/usr/share/wallpapers/zaod/"
# /usr/share/doc is stripped later to save space, so the wallpaper attribution
# lives with the licences that do survive: the images in the image must always
# carry their credits.
as_root install -D -m 0644 desktop/design/wallpapers/collection/README.md \
  "$ROOTFS_DIR/usr/share/zaod/licenses/wallpaper-credits.md"
as_root cp -a desktop/design/gtk/. "$ROOTFS_DIR/usr/share/themes/Zaod/"

# The default user template is a skel the installer copies, not a login.
as_root mkdir -p "$ROOTFS_DIR/etc/skel/.config"
cat <<'SKEL' | as_root tee "$ROOTFS_DIR/etc/skel/.profile" >/dev/null
# Zaod OS default shell profile
if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi
export XDG_CURRENT_DESKTOP=Zaod
SKEL
as_root chmod 0644 "$ROOTFS_DIR/etc/skel/.profile"

# ---------------------------------------------------------------- 3. kernel
say "installing Phase 2 kernel $KERNEL_RELEASE, modules and pinned firmware"
as_root install -d "$ROOTFS_DIR/boot"
as_root install -m 0644 "$KERNEL_OUT/vmlinuz" "$ROOTFS_DIR/boot/vmlinuz-$KERNEL_RELEASE"
as_root install -m 0644 "$KERNEL_OUT/System.map" "$ROOTFS_DIR/boot/System.map-$KERNEL_RELEASE"
# The modules archive carries its own leading ./lib/ entry. Extracted plainly
# into a merged-/usr tree, that entry replaces the `lib -> usr/lib` symlink with
# a real directory: the modules then land outside usr/lib, and every later path
# under /lib stops existing. That is how a build died with
# "tar: build/rootfs/lib/firmware: Cannot open: No such file or directory" -
# the firmware step was the first thing to notice the symlink was gone.
# --keep-directory-symlink extracts through the existing symlink instead of
# overwriting it, and --no-same-owner keeps /lib/modules owned by root rather
# than by whatever uid packaged the archive.
as_root tar -xzf "$KERNEL_OUT/modules.tar.gz" -C "$ROOTFS_DIR" \
  --keep-directory-symlink --no-same-owner
[[ -d "$ROOTFS_DIR/lib/modules/$KERNEL_RELEASE" ]] \
  || fail "the modules archive did not install into lib/modules/$KERNEL_RELEASE"
as_root depmod -a -b "$ROOTFS_DIR" "$KERNEL_RELEASE"
as_root install -d "$ROOTFS_DIR/lib/firmware"
as_root tar -xJf "$KERNEL_OUT/firmware.tar.xz" -C "$ROOTFS_DIR/lib/firmware" \
  --no-same-owner
[[ -d "$ROOTFS_DIR/lib/firmware" && -n "$(ls -A "$ROOTFS_DIR/lib/firmware" 2>/dev/null)" ]] \
  || fail "the firmware archive unpacked nothing into lib/firmware"
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
# Proof the desktop in this tree can run, while /proc and /dev are still
# mounted: a missing toolkit or icon theme is a black screen on real
# hardware, and it must fail here instead.
# SVG art is rendered to PNG inside the tree: icons and the wallpaper needed an
# SVG loader in the image and were blank without one.
as_root install -m 0755 scripts/render-zaod-art.py "$ROOTFS_DIR/tmp/render-zaod-art.py"
# The offscreen platform plugin is the normal route; the minimal one is the
# fallback so a headless render cannot fail a 40 minute build on its own.
if ! as_root chroot "$ROOTFS_DIR" env QT_QPA_PLATFORM=offscreen /usr/bin/python3 /tmp/render-zaod-art.py; then
  say "offscreen platform unavailable, rendering with minimal"
  as_root chroot "$ROOTFS_DIR" env QT_QPA_PLATFORM=minimal /usr/bin/python3 /tmp/render-zaod-art.py \
    || fail "the SVG art could not be rendered to PNG"
fi
as_root rm -f "$ROOTFS_DIR/tmp/render-zaod-art.py"
as_root chroot "$ROOTFS_DIR" /usr/bin/gdk-pixbuf-query-loaders --update-cache || true
if as_root test -x "$ROOTFS_DIR/usr/bin/gtk-update-icon-cache"; then
  as_root chroot "$ROOTFS_DIR" /usr/bin/gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi

# Every app has to open its window inside the image before it is squashed.
as_root install -m 0755 scripts/smoke-apps-in-image.py "$ROOTFS_DIR/tmp/smoke-apps.py"
say "proving every app opens its window"
if ! as_root chroot "$ROOTFS_DIR" env QT_QPA_PLATFORM=offscreen /usr/bin/python3 /tmp/smoke-apps.py; then
  as_root chroot "$ROOTFS_DIR" env QT_QPA_PLATFORM=minimal /usr/bin/python3 /tmp/smoke-apps.py \
    || fail "an app cannot open its window inside the image"
fi
as_root rm -f "$ROOTFS_DIR/tmp/smoke-apps.py"

# The offscreen check says an app builds a window; this says it opens on the
# Wayland compositor the session actually runs.
as_root install -m 0755 scripts/test-apps-wayland.sh "$ROOTFS_DIR/tmp/test-apps-wayland.sh"
as_root install -m 0755 scripts/gio-launch-entry.py "$ROOTFS_DIR/tmp/gio-launch-entry.py"
say "proving every app opens its window on wayland"
if ! as_root chroot "$ROOTFS_DIR" env HOME=/root /bin/bash /tmp/test-apps-wayland.sh; then
  fail "an app does not run on the wayland session"
fi
as_root rm -f "$ROOTFS_DIR/tmp/test-apps-wayland.sh" "$ROOTFS_DIR/tmp/gio-launch-entry.py"

cleanup_chroot_mounts
trap - EXIT
as_root chroot "$ROOTFS_DIR" /usr/bin/systemctl --root=/ enable NetworkManager.service \
  earlyoom.service systemd-timesyncd.service sddm.service zaod-lite-mode.service \
  zaod-oobe.service zaod-boot-watchdog.service
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
# The live home has to belong to the live account.
#
# /home/zaodlive exists in the rootfs before useradd runs, so useradd leaves it
# owned by root with mode 0700 - and everything a session writes lives under
# $HOME. iso-74 started the desktop and lost it again: labwc, the panel,
# wireplumber and every app were refused "Permission denied" on their own config
# and cache directories, and the console sat at "change directory failed:
# Permission denied" for the same reason. Own the home, then prove it.
# The chown has to run inside the image: the host that builds it has no
# zaodlive account, so `chown zaodlive:zaodlive` on the rootfs path fails with
# "invalid user" and takes the whole build down.
as_root chroot "$ROOTFS_DIR" /usr/bin/chown --recursive \
  "$LIVE_USER:$LIVE_USER" "/home/$LIVE_USER" \
  || fail "the live home could not be given to $LIVE_USER"
as_root chroot "$ROOTFS_DIR" /usr/bin/chmod 0755 "/home/$LIVE_USER"
# Prove the ownership rather than trusting the chown above: a session that
# cannot write $HOME is exactly the iso-74 crash.
home_owner=$(as_root chroot "$ROOTFS_DIR" /usr/bin/stat -c "%U" "/home/$LIVE_USER")
if [ "$home_owner" != "$LIVE_USER" ]; then
  fail "/home/$LIVE_USER is owned by $home_owner, not $LIVE_USER"
fi

# The live account needs a password a person can actually type.
#
# iso-16 .. iso-24 ran `passwd --lock zaodlive`. That is invisible on the SDDM
# autologin path, but it leaves anyone who lands on the text console - a machine
# whose graphical session did not come up, or a login line that scrolled away
# before it was read - with no way into their own live session at all. The
# password below is the live media password, it is printed on the console by
# /etc/issue, and it is documented in docs/desktop.md. It only ever exists on
# the live image: the installer removes the zaodlive account.
# Debian ships passwd/chpasswd in /usr/bin in a merged-usr image, so resolve
# them instead of assuming the split-usr path.
# shellcheck disable=SC2016  # the expansion belongs to the chroot
as_root chroot "$ROOTFS_DIR" /bin/sh -c '
  export PATH=/usr/sbin:/usr/bin:/sbin:/bin
  printf "%s:%s\n" "$1" "$2" | "$(command -v chpasswd)" || {
    echo "chpasswd is missing from the image" >&2
    exit 1
  }
' sh "$LIVE_USER" "$LIVE_PASSWORD" >/dev/null

# The console banner repeats the credentials at every login prompt, so nothing
# has to be caught mid-scroll, and it names the machine separately from the
# account: `zaod login:` is the hostname, not a user name.
as_root tee "$ROOTFS_DIR/etc/issue" >/dev/null <<ISSUE
Zaod OS live session  \\n \\l

  user: $LIVE_USER    password: $LIVE_PASSWORD

The desktop asks for this same login. If it did not come up, log in above and run:
  sudo systemctl start sddm
ISSUE
as_root chmod 0644 "$ROOTFS_DIR/etc/issue"

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

say "verifying the desktop in the image (after the space strip, so this is the tree that ships)"
bash scripts/verify-rootfs-desktop.sh --root "$ROOTFS_DIR"
# mounts come down before anything deletes inside the tree, or a delete could
# reach through a bind mount into the build host
cleanup_chroot_mounts
trap - EXIT

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
# Every path used to be forced to uid 0 here with -all-root. That flag is what
# handed /home/zaodlive back to root: the live account could not write its own
# home inside the image, labwc and the panel died on their config and cache
# directories, and iso-77 booted to a wallpaper with no desktop on it. The
# ownership the rootfs carries is the ownership the image ships.
as_root mksquashfs "$ROOTFS_DIR" "$SQUASHFS" \
  -comp zstd -Xcompression-level "$SQUASH_LEVEL" \
  -noappend -no-progress
as_root chown "$(id -u):$(id -g)" "$SQUASHFS" 2>/dev/null || true

say "writing reproducible rootfs tarball"
as_root tar -C "$ROOTFS_DIR" --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
  --numeric-owner --owner=0 --group=0 --format=posix -cf "$ROOTFS_TARBALL" .
as_root chown "$(id -u):$(id -g)" "$ROOTFS_TARBALL" 2>/dev/null || true

# Read the ownership back out of the squashfs, not out of the build tree: the
# rootfs on disk was correct while the image was not, which is how iso-76 and
# iso-77 both shipped a home owned by root.
live_uid=$(as_root chroot "$ROOTFS_DIR" /usr/bin/id -u "$LIVE_USER")
live_owner=$(unsquashfs -lln "$SQUASHFS" "home/$LIVE_USER" 2>/dev/null \
  | tail -n 1 | awk '{print $2}')
if [ "$live_owner" != "$live_uid/$live_uid" ]; then
  fail "the image gives /home/$LIVE_USER to $live_owner, not $live_uid/$live_uid: a session cannot write that home"
fi
say "live home in the image: /home/$LIVE_USER owned by $live_owner"

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
