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
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y --no-install-recommends \
  bc bison build-essential ccache curl debootstrap flex g++ gcc git gnupg kmod \
  libelf-dev libncurses-dev libssl-dev make mmdebstrap mtools ovmf \
  python3 python3-pip python3-venv qemu-system-x86 shellcheck squashfs-tools \
  xorriso grub-common grub-efi-amd64-bin grub-pc-bin

if command -v ruff >/dev/null 2>&1; then
  printf 'ruff already available: %s\n' "$(command -v ruff)"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force ruff
else
  python3 -m pip install --user --break-system-packages ruff
fi

printf '%s\n' 'Zaod OS build tools are installed.'