#!/bin/bash
# Build the reference hello app as a .zaod package.
# Usage: apps/hello-gui/build.sh [path/to/signing.key]
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
root=$(cd "$here/../.." && pwd)
out="${root}/build/out/apps"
key=${1:-}
mkdir -p "$out"
if [ -n "$key" ]; then
  "${root}/zaod/bin/zaod" pack "$here" -o "${out}/zaod-hello-1.0.0.zaod" --key "$key"
else
  "${root}/zaod/bin/zaod" pack "$here" -o "${out}/zaod-hello-1.0.0.zaod"
fi
