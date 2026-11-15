#!/usr/bin/env bash
# Reproduce the CI gate locally. The GitHub workflow runs the same steps.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

printf '\n== shellcheck ==\n'
shellcheck scripts/*.sh tests/*.sh desktop/scripts/*.sh kernel/*.sh

printf '\n== ruff ==\n'
ruff check .

printf '\n== pytest ==\n'
python3 -m pytest tests zaod/tests -q

printf '\n== generated design artefacts ==\n'
python3 desktop/design/tools/tokens_to_qml.py --check
python3 desktop/design/tools/tokens_to_css.py --check
python3 desktop/design/tools/make_wallpapers.py --check

printf '\n== design tokens and accessibility ==\n'
python3 tests/check_design_tokens.py

printf '\n== boot chain configuration ==\n'
python3 tests/check_boot_config.py

printf '\n== desktop session configuration ==\n'
python3 tests/check_desktop_config.py

printf '\n== vendor asset scan ==\n'
python3 desktop/design/tools/scan_assets.py

printf '\nall checks passed\n'
