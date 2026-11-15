#!/bin/bash
# Prove the Phase 7 sandbox rules: a package without the network permission
# cannot reach the network or read host files, and adding the permission
# changes that for the same payload.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
zaod="$repo_root/zaod/bin/zaod"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export ZAOD_ROOT="$work/root"
export HOME="$work/home"
mkdir -p "$HOME"

probe_script="$work/probe.sh"
cat >"$probe_script" <<'PROBE'
#!/bin/bash
echo "uid=$(id -u)"
echo "host-hostname=$(cat /proc/sys/kernel/hostname 2>/dev/null || echo unknown)"
if [ -e /etc/shadow ]; then echo "host-etc-shadow=visible"; else echo "host-etc-shadow=hidden"; fi
if [ -e /root ] || [ -e /home ]; then echo "host-home=visible"; else echo "host-home=hidden"; fi
if timeout 5 bash -c 'exec 3<>/dev/tcp/1.1.1.1/443' 2>/dev/null; then
  echo "network=reachable"
else
  echo "network=blocked"
fi
PROBE
chmod +x "$probe_script"

make_app() {
  local name=$1 dir="$work/src-$1" network=$2
  mkdir -p "$dir/payload/bin"
  cp "$probe_script" "$dir/payload/bin/probe"
  printf '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"/>\n' >"$dir/icon.svg"
  cat >"$dir/MANIFEST.json" <<MANIFEST
{
  "format": 1,
  "id": "org.zaod.probe-$name",
  "name": "Probe $name",
  "version": "1.0.0",
  "kind": "app",
  "arch": "x86_64",
  "min_os": "0.7.0",
  "summary": "Sandbox proof probe ($name)",
  "license": {"spdx": "MIT"},
  "author": {"name": "Zaod OS"},
  "entry": {"exec": "payload/bin/probe", "terminal": true},
  "permissions": {"network": ${network}, "filesystem": [], "devices": []}
}
MANIFEST
  "$zaod" pack "$dir" -o "$work/$name.zaod" --key "$work/dev.key" >/dev/null
}

"$zaod" key generate --out "$work/dev.key" --trust >/dev/null
make_app "nonet" "false"
make_app "net" "true"
"$zaod" install "$work/nonet.zaod" >/dev/null
"$zaod" install "$work/net.zaod" >/dev/null

# Network namespaces need CAP_NET_ADMIN; most CI containers do not grant it.
net_namespaces=1
if ! bwrap --unshare-net --ro-bind / / true >/dev/null 2>&1; then
  net_namespaces=0
  echo "NOTE: this host cannot create a network namespace; the network line below is"
  echo "      shown for the filesystem-only probe. Run on a Zaod system for the full proof."
  echo
fi

run_probe() {
  local app=$1
  if [ "$net_namespaces" = 1 ]; then
    "$zaod" run "$app"
  else
    # Keep the isolation plan, but share the host network so bwrap can start
    # without CAP_NET_ADMIN. Only the network namespace step is replaced.
    local command
    command=$("$zaod" run "$app" --print-command)
    command=${command/--unshare-all/--unshare-all --share-net}
    bash -c "$command"
  fi
}

echo "=== zaod run org.zaod.probe-nonet (no network permission) ==="
run_probe org.zaod.probe-nonet
echo
echo "=== zaod run org.zaod.probe-net (network permission) ==="
run_probe org.zaod.probe-net
