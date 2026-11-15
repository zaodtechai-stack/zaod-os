## Zaod OS Phase 6 design system report

- Date (UTC): 2026-11-15
- Status: **PARTIAL** - the design system, generators, component kit, shell surfaces and the automated accessibility gate are complete and passing; the twelve visual-approval screenshots require a running Plasma session, which this build host cannot provide.
- Phase version: 0.6.0

## What was built

- `desktop/design/tokens/tokens.json`: single source of truth - 4 px spacing grid, fixed radius set, elevation ladder, 120-250 ms motion with cubic-bezier easing, an eight-step type scale, light and dark palettes over 23 colour roles, and the 42 declared contrast pairs.
- Generators: `tokens_to_qml.py` (singleton), `tokens_to_css.py` (GTK 3 and GTK 4), `make_wallpapers.py` (three original designs x light/dark). Each has a `--check` mode for CI.
- `desktop/design/qml/`: `ZaodTheme` singleton plus `ZaodButton`, `ZaodCard`, `ZaodSwitch`, `ZaodMenu`, `ZaodToolbar`, `ZaodWindow` with focus rings, keyboard activation, `Accessible` metadata and token-only colours.
- `desktop/design/shell/`: floating centred `Taskbar`, searchable `StartMenu` with pinned grid and recents, `QuickSettings` (Wi-Fi, Bluetooth, night light, airplane, volume, brightness, battery, lock), `NotificationCenter` with calendar strip.
- `desktop/design/icons/`: nine original 24 px SVG glyphs (logo, app grid, search, settings, network, battery, folder, power, terminal).
- `desktop/design/gtk/`: generated GTK 3 and GTK 4 themes; `desktop/design/wallpapers/`: six generated SVGs.
- `desktop/design/tools/scan_assets.py`: repository-wide vendor-asset and licence scanner.
- `desktop/design/LICENSE.md`: asset licence plus the provenance statement.

## Acceptance table

| PRD acceptance item | Status here | Evidence |
| --- | --- | --- |
| Tokens in one file; QML and GTK generated | PASS | `--check` passes for all three generators |
| 4 px grid, radii, motion 120-250 ms enforced | PASS | `check_structure`, incl. negative tests in `test_design_tools.py` |
| Contrast computed and >= 4.5:1 text / 3:1 UI | PASS | 42 pairs, lowest 3.13:1 (light border), every text pair >= 4.5:1 |
| Light and dark both complete | PASS | theme parity check over 23 roles |
| Three original wallpapers, light and dark | PASS | six SVGs, deterministic, < 400 KB each |
| Fonts limited to Inter / JetBrains Mono / Noto with licences | PASS | whitelist plus OFL-1.1 declarations in tokens and LICENSE.md |
| No Microsoft asset or trademark anywhere | PASS | repo-wide `scan_assets.py` |
| Twelve named screenshots for owner visual approval | NOT RUN | needs a booted Plasma session (Codespaces + QEMU) |

## Commands executed here

```
python3 desktop/design/tools/tokens_to_qml.py            -> wrote qml/ZaodTheme.qml
python3 desktop/design/tools/tokens_to_css.py            -> wrote 8 files (GTK 3 and 4)
python3 desktop/design/tools/make_wallpapers.py          -> wrote 6 wallpapers
python3 desktop/design/tools/tokens_to_qml.py --check    -> up to date
python3 desktop/design/tools/tokens_to_css.py --check    -> all generated CSS is up to date
python3 desktop/design/tools/make_wallpapers.py --check  -> all wallpapers up to date
python3 tests/check_design_tokens.py --verbose           -> 352 checks, 0 failed, 42 pairs, lowest 3.13:1
python3 -m pytest tests -q                               -> 73 passed (35 lite mode, 38 design)
python3 desktop/design/tools/scan_assets.py              -> PASS
ruff check tests/ desktop/                               -> All checks passed
```

## Honest limitations

- No QML engine or Qt runtime exists on this host, so the components and shell surfaces have not been rendered or run. They are structurally validated (balanced syntax, imports, no hardcoded colours, token references, qmldir inventory) but must be exercised in a Plasma 6 session.
- Contrast is verified for the palette pairs the shell and applications actually use. Non-text graphical objects that use `accent` at low opacity for decoration are deliberately outside the rule.
- Icon coverage is a starter set of nine original glyphs. The session still installs `breeze-icon-theme` (LGPL) for full coverage, declared in `LICENSE.md`.
- The twelve screenshots required for owner visual approval remain outstanding.

## Owner test steps after the Codespaces build

```sh
make design            # regenerate and --check every artefact
python3 tests/check_design_tokens.py --verbose
qemu-system-x86_64 -m 2048 -enable-kvm ...    # boot the desktop
# then capture the twelve screens named in the brief: desktop light/dark,
# Start menu, quick settings, notifications, settings, files, terminal,
# installer, store, control centre, lock screen.
```

## Deviations

None from the PRD. The type scale adds a `body-strong` step at the same size as
`body` with a heavier weight, which the validator accepts as distinguishable and
which the shell uses for panel titles.
