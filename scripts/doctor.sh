#!/usr/bin/env bash
set -u

section() {
  printf '\n## %s\n' "$1"
}

section "Zaod OS Phase 1 host report"
printf '\n- Date (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s\n' "- Host: $(uname -a)"

section "Compute and storage"
printf '\n- CPU cores: %s\n' "$(nproc 2>/dev/null || echo unknown)"
printf '%s\n' '- Memory:'
free -m 2>&1 | sed 's/^/  /'
printf '%s\n' '- Workspace filesystem:'
df -h /workspaces 2>&1 | sed 's/^/  /'

section "Required tools"
for tool in make gcc shellcheck ruff python3 debootstrap mmdebstrap docker \
  qemu-system-x86_64 xorriso curl gpg sudo; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '\n- %s: %s\n' "$tool" "$(command -v "$tool")"
  else
    printf '\n- %s: missing\n' "$tool"
  fi
done

section "Privileges and virtualization"
printf '\n- User: %s\n' "$(id -un)"
if sudo -n true >/dev/null 2>&1; then
  printf '%s\n' '- Non-interactive sudo: available'
else
  printf '%s\n' '- Non-interactive sudo: unavailable'
fi
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
  printf '%s\n' '- KVM: accessible'
elif [[ -e /dev/kvm ]]; then
  printf '%s\n' '- KVM: present but not accessible'
else
  printf '%s\n' '- KVM: unavailable'
fi
if [[ -S /var/run/docker.sock ]]; then
  printf '%s\n' '- Docker socket: present'
else
  printf '%s\n' '- Docker socket: unavailable'
fi

section "Network"
if curl --fail --silent --show-error --max-time 10 -I https://www.kernel.org \
  >/dev/null 2>&1; then
  printf '%s\n' '- HTTPS to kernel.org: available'
else
  printf '%s\n' '- HTTPS to kernel.org: unavailable'
fi