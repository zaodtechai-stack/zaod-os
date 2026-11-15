#!/usr/bin/env bash
set -euo pipefail

SBOM_DIR=/usr/share/zaod
LICENSE_DIR="$SBOM_DIR/licenses"

mkdir -p "$LICENSE_DIR/debian"
dpkg-query -W -f='${binary:Package}\t${Version}\t${Architecture}\n' \
  | LC_ALL=C sort > "$SBOM_DIR/sbom.txt"
sha256sum "$SBOM_DIR/packages.list" > "$SBOM_DIR/packages.list.sha256"

mapfile -d '' -t copyright_files < <(find /usr/share/doc -type f -name copyright -print0)
if (( ${#copyright_files[@]} == 0 )); then
  printf '%s\n' 'No Debian copyright notices found; refusing to remove package metadata.' >&2
  exit 1
fi
for notice in "${copyright_files[@]}"; do
  cp --parents "$notice" "$LICENSE_DIR/debian"
done
cat > "$LICENSE_DIR/README.txt" <<'EOF'
Debian copyright notices are preserved under debian/usr/share/doc.
Linux firmware license files and WHENCE are preserved under linux-firmware.
The SBOM records installed binary package names, versions, and architectures.
EOF

apt-get clean
find /usr/share/doc -mindepth 1 -maxdepth 1 -exec rm -rf {} +
rm -rf /usr/share/man /usr/share/info
if [[ -d /usr/share/locale ]]; then
  find /usr/share/locale -mindepth 1 -maxdepth 1 \
    ! -name en ! -name en_US ! -name en_US.UTF-8 ! -name locale.alias \
    -exec rm -rf {} +
fi

rm -f /usr/bin/apt /usr/bin/apt-* /usr/sbin/apt /usr/sbin/apt-*
rm -f /usr/bin/dpkg /usr/bin/dpkg-* /usr/sbin/dpkg /usr/sbin/dpkg-*
rm -f /usr/bin/aptitude /usr/bin/nala /usr/bin/update-alternatives
rm -f /usr/bin/deb-systemd-helper /usr/bin/deb-systemd-invoke
rm -rf /usr/lib/apt /usr/lib/dpkg /usr/share/apt /usr/share/dpkg
rm -rf /etc/apt /etc/dpkg /var/lib/apt /var/lib/dpkg /var/cache/apt /var/log/apt
find /usr/lib /usr/libexec -type f \
  \( -name 'libapt-pkg.so*' -o -name 'libdpkg.so*' \) -delete
rm -f /usr/share/bash-completion/completions/apt*
hash -r

for binary in apt apt-get apt-cache apt-config aptitude dpkg dpkg-deb dpkg-query; do
  if command -v "$binary" >/dev/null 2>&1; then
    printf 'Package manager binary remains: %s\n' "$binary" >&2
    exit 1
  fi
done
for database in /etc/apt /var/lib/apt /var/lib/dpkg; do
  if [[ -e "$database" ]]; then
    printf 'Package manager database remains: %s\n' "$database" >&2
    exit 1
  fi
done
