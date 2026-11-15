#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=()
elif sudo -n true >/dev/null 2>&1; then
  SUDO=(sudo -n)
else
  printf '%s\n' 'Non-interactive sudo is required to install system build tools.' >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
if command -v apk >/dev/null 2>&1; then
  "${SUDO[@]}" apk add --no-cache \
    bc bison build-base ccache curl debootstrap diffutils dosfstools e2fsprogs \
    elfutils-dev flex git gnupg grub-bios grub-efi kmod mtools ncurses-dev \
    ovmf py3-pip py3-ruff python3 qemu-system-x86_64 shellcheck squashfs-tools \
    util-linux xorriso
elif command -v apt-get >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y --no-install-recommends \
    bc bison build-essential ccache curl debootstrap diffutils flex g++ gcc git \
    gnupg kmod libelf-dev libncurses-dev libssl-dev make mmdebstrap mtools ovmf \
    python3 python3-pip python3-venv qemu-system-x86 shellcheck squashfs-tools \
    xorriso grub-common grub-efi-amd64-bin grub-pc-bin dosfstools e2fsprogs
else
  printf '%s\n' 'Unsupported host: install apk or apt-get to provision build tools.' >&2
  exit 1
fi

if command -v ruff >/dev/null 2>&1; then
  printf 'ruff already available: %s\n' "$(command -v ruff)"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force ruff
else
  python3 -m pip install --user --break-system-packages ruff
fi

printf '%s\n' 'Zaod OS build tools are installed.'