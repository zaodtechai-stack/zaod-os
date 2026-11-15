# Zaod OS user guide

Zaod OS is a desktop system that runs signed application packages. It installs and
updates without a network connection, and it never sends anything about you unless you
switch that on yourself.

## Installing

1. Write the ISO to a USB stick with your image writer (GNOME Disks, or any tool that
   copies an image to a block device byte for byte). A 4 GB stick is enough.
2. Boot the stick in UEFI mode. Legacy BIOS boots too, but UEFI is the supported path.
3. The installer runs offline: no mirror, no account, no licence key.
4. Pick an application set: Minimal (Files and Terminal), Essentials (the default), or
   Essentials with Firefox.
5. Set your user account, then install. The installed system boots straight into setup.

Installation uses the whole disk; dual boot is not offered yet.

## First boot

Setup takes about a minute and has three steps: a welcome page, appearance (theme and
accent colour), and privacy. Both privacy switches are **off** by default:

- **Diagnostics**: nothing is collected unless you tick it.
- **Location**: apps cannot see your approximate location unless you allow it.

Update handling is chosen here too: security updates only (default), all updates
automatically, or manual. All of these stay changeable in Control Center.

The answers are stored in `~/.config/zaod/oobe.json`. Running `zaod-setup --force`
opens setup again; it never overwrites your files.

## Desktop

- The top bar shows the clock, network state and system status.
- Click the status area to open Control Center: Network, Appearance, Display, Sound,
  Power, Updates, Privacy and About.
- Super opens the launcher; Super+L locks the screen.

## Applications

Files, Terminal, Text Editor, Calculator, Notes, Clock, Tasks, Converter, Image Viewer,
System Monitor, Control Center, Store and Firefox ESR (with Google as the default search
engine) are installed as signed `.zaod` packages. Each package declares its permissions,
and the description shows them before you install.

Zaod Studio is optional: install it from the Store if you want to build your own apps.

## Store and updates

The Store lists the local repository first, so it works with no network at all. When a
network is available it can also read a remote index; indexes and packages are verified
with Ed25519 signatures before anything is unpacked.

- `zaod update` updates installed apps from the repositories.
- `zaod bundle apply updates.zaodbundle` applies a release update bundle.
- `zaod list`, `zaod info <app>`, `zaod search <word>` for inspection.
- `zaod gc` removes superseded versions and old caches.

An update bundle is a transaction: if any package fails, every package already installed
in that run is restored, so you never end up half updated.

## Privacy

- No telemetry, no account, no advertising identifiers.
- Nothing is collected while diagnostics stay off; the switch is in Control Center.
- Application permissions (network, files, devices) are enforced by the sandbox, and the
  Store shows them before installation.

## If something goes wrong

| Symptom | What to do |
| --- | --- |
| An app does not start | `zaod run <app-id>` in a terminal shows the sandbox error |
| An app looks broken after an update | `zaod bundle rollback /var/lib/zaod/updates/<stamp>-<version>` |
| Disk filled by old versions | `zaod gc` |
| Package refused as unsigned | Only trust packages from keys you added with `zaod key trust` |
| Installer cannot find the repository | Boot the same stick again; the image carries its own repository |

## Getting help

`zaod --help` lists every command, and each command has its own `--help`. The developer
guide (`docs/dev/`) covers the package format, the sandbox and building apps.
