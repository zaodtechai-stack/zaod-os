# First-boot onboarding (OOBE)

Zaod OS never ships a working password it never told anyone. On a machine with
no account to sign in as, the boot stops on a console wizard that creates one,
and only then does the display manager start.

## When it runs

`zaod-oobe.service` is enabled on every build and skipped unless it is needed:

```
ConditionPathExists=!/etc/zaod/oobe-done
```

`desktop/oobe/oobe.py --check` is the same decision expressed as data: it reads
`/etc/passwd` and reports `onboarding` when no account with uid >= 1000 other
than the reserved names (`zaodlive`, `root`, ...) exists, and `ready` otherwise.
The unit owns `tty1` from before `display-manager.service` until the wizard
exits, so the login screen never paints over a half-finished account.

## What it asks for

| Step | Rule |
| --- | --- |
| Name | free text, used as the GECOS label and to suggest the account name |
| Account name | lower-case letter first, then letters, digits and `-`, max 32; not reserved, not taken |
| Password | at least 8 characters, must not contain the account name, not one repeated character, not one of the handful everyone tries first |
| Password again | must match |
| Time zone | typed as a city (`karachi` finds `Asia/Karachi`); blank skips |
| Confirm | shows everything before anything is written |

It then runs `useradd --create-home --shell /bin/bash --groups
wheel,audio,video,render,input,netdev`, sets the password with `chpasswd`, applies
the time zone with `timedatectl` (falling back to the `/etc/localtime` symlink),
writes the name into SDDM's `state.conf` so the login box opens on the new
account, and finally creates `/etc/zaod/oobe-done`.

The account is a full administrator: `wheel` plus the shipped sudoers rule, so
`sudo` works with the password just chosen. Ctrl+C, EOF or answering `n` leaves
the machine untouched and the wizard returns on the next boot.

## Live media

On live media the wizard runs on every boot, because the session writes to a
tmpfs layer and an account created there cannot outlive the power-off. The live
image still carries the demo account `zaodlive` / `zaod`, and the wizard says so
and lets the person skip with `L`. Both paths end at the same login screen, which
is the same flow as an installed system.

## Testing

```sh
python3 -m pytest tests/test_oobe.py -q                     # rules and flows
python3 desktop/oobe/oobe.py --check                        # is onboarding needed?
printf 'Hassan Ali\nhassan\nstrong-password-1\nstrong-password-1\nkarachi\ny\n' \
  | python3 desktop/oobe/oobe.py --dry-run --passwd /tmp/passwd   # walk it, write nothing
```

`--dry-run` prints the `useradd` command it would run and stops, so the flow can
be reviewed on a machine that must not be changed.

## Skipping on live media

The live image runs the wizard on every boot, because the account it creates
lives in the tmpfs overlay and vanishes at power off. The banner therefore
offers an escape: typing `l` (or `skip`) at the name prompt leaves the machine
alone, prints the demo credentials `zaodlive` / `zaod`, and lets the boot carry
on to the login screen. Nothing is written, so the next boot asks again. To
create the account anyway, run `sudo systemctl restart zaod-oobe`.

On installed media there is no demo account to fall back to, so `l` is an
ordinary name there and the wizard does not offer the skip.

