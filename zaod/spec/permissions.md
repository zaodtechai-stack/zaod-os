# Zaod permission model

Every manifest declares its permissions explicitly, and the launcher maps them
onto a bubblewrap sandbox. Nothing is granted by default.

| Permission | Value | Effect inside the sandbox |
| --- | --- | --- |
| `network` | `true` | Adds `--share-net`. Without it the app runs with no network at all. |
| `filesystem` | `home`, `documents`, `downloads`, `music`, `pictures`, `videos`, `desktop`, `removable` | Bind mount of that user directory only. No entry means the app cannot see it. |
| `devices` | `dri`, `audio`, `input`, `usb`, `kvm` | Bind mount of the matching device node directory. |
| `env` | string map | Extra environment variables set with `--setenv`. |

Always applied, regardless of permissions:

- `--unshare-all`, `--die-with-parent`, `--new-session`, `--clearenv`
- read-only `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, fonts and TLS certificates
- the package itself read-only at `/app`
- `$HOME` and the XDG directories redirected to `/data`, a bind mount of
  `~/.zaod/data/<id>` (created on first run)
- a fresh `/tmp` and `/run`

`zaod run <id>` prints the resulting permission list on stderr before starting,
and `zaod install` shows the same list in the install summary. `zaod info` and
the store show it before an app is installed, so a user always sees network and
file access in plain language.
