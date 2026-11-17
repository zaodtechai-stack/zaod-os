#!/usr/bin/env python3
"""Zaod OS first-boot onboarding (OOBE).

Runs before the display manager on a machine that has no human account yet and
creates one: full name, account name, password and time zone. Everything it
decides lives in pure functions at the top of this file so the rules can be
tested without a root shell, a TTY or a real /etc/passwd.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import time

DONE_FILE = "/etc/zaod/oobe-done"
PASSWD_FILE = "/etc/passwd"
LIVE_MARKER = "/run/zaod-init/live"
GROUPS = "wheel,audio,video,render,input,netdev"
RESERVED = {"zaodlive", "root", "nobody", "daemon", "bin", "sync", "sys", "admin"}
USERNAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MIN_PASSWORD = 8


# ----------------------------------------------------------------- pure rules
def parse_accounts(passwd_text: str) -> list[dict]:
    """Parse /etc/passwd into the records the onboarding cares about."""
    accounts = []
    for line in passwd_text.splitlines():
        fields = line.split(":")
        if len(fields) < 7:
            continue
        name, _, uid, gid, gecos, home, shell = fields[:7]
        try:
            uid_number = int(uid)
        except ValueError:
            continue
        accounts.append(
            {
                "name": name,
                "uid": uid_number,
                "gid": int(gid) if gid.isdigit() else 0,
                "gecos": gecos,
                "home": home,
                "shell": shell,
            }
        )
    return accounts


def human_accounts(accounts: list[dict]) -> list[dict]:
    """Accounts a person can sign in to (uid >= 1000, minus the live account)."""
    return [a for a in accounts if a["uid"] >= 1000 and a["name"] not in RESERVED]


def needs_onboarding(accounts: list[dict]) -> bool:
    """True when the machine has nobody to sign in as yet."""
    return not human_accounts(accounts)


def suggest_username(full_name: str) -> str:
    """Build a Debian-legal account name out of a display name."""
    slug = full_name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        return ""
    if not slug[0].isalpha():
        slug = "u" + slug
    slug = slug[:32].rstrip("-")
    return slug


def validate_username(name: str, accounts: list[dict]) -> tuple[bool, str]:
    if not name:
        return False, "Enter an account name."
    if not USERNAME_RE.match(name):
        return (
            False,
            (
                "Lower-case letters, digits and '-' only; it must start with a letter "
                "and be at most 32 characters."
            ),
        )
    if name in RESERVED:
        return False, f"'{name}' is reserved by Zaod OS."
    if any(a["name"] == name for a in accounts):
        return False, f"'{name}' is already taken."
    return True, ""


def validate_password(password: str, username: str) -> tuple[bool, str]:
    if len(password) < MIN_PASSWORD:
        return False, f"Use at least {MIN_PASSWORD} characters."
    if username and username.lower() in password.lower():
        return False, "The password cannot contain the account name."
    if len(set(password)) == 1:
        return False, "That password is the same character repeated."
    if password.lower() in {"password", "zaodlive", "zaod", "12345678", "qwertyui"}:
        return False, "That password is on the short list everyone tries first."
    return True, ""


def useradd_argv(username: str, full_name: str) -> list[str]:
    return [
        "useradd",
        "--create-home",
        "--shell",
        "/bin/bash",
        "--groups",
        GROUPS,
        "--comment",
        full_name.strip(),
        username,
    ]


def timezone_choices(root: str = "/usr/share/zoneinfo") -> list[str]:
    """Region/City zones, in the order a person is likely to look for them."""
    zones = []
    try:
        regions = sorted(os.listdir(root))
    except OSError:
        return zones
    for region in regions:
        if not os.path.isdir(os.path.join(root, region)):
            continue
        if region in {"posix", "right", "SystemV", "Etc", "zone.tab"}:
            continue
        try:
            cities = sorted(os.listdir(os.path.join(root, region)))
        except OSError:
            continue
        zones.extend(f"{region}/{city}" for city in cities if region != "posix")
    return zones


def match_timezones(query: str, zones: list[str]) -> list[str]:
    """Case-insensitive substring match, so 'karachi' finds Asia/Karachi."""
    needle = query.strip().lower().replace(" ", "_")
    if not needle:
        return []
    return [zone for zone in zones if needle in zone.lower()][:8]


# ------------------------------------------------------------------- console
class Console:
    """Minimal line-oriented terminal: no curses, so a serial console works."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def clear(self):
        if self.stream.isatty():
            self.stream.write("\033[2J\033[H")
            self.stream.flush()

    def say(self, text=""):
        self.stream.write(text + "\n")
        self.stream.flush()

    def rule(self, title=""):
        self.say()
        self.say("=" * 68)
        if title:
            self.say(f"  {title}")
            self.say("=" * 68)

    def ask(self, label, default=""):
        suffix = f" [{default}]" if default else ""
        self.stream.write(f"{label}{suffix}: ")
        self.stream.flush()
        answer = sys.stdin.readline()
        if not answer:
            raise EOFError
        answer = answer.strip()
        return answer or default

    def ask_secret(self, label):
        if sys.stdin.isatty():
            return getpass.getpass(f"{label}: ")
        self.stream.write(f"{label}: ")
        self.stream.flush()
        answer = sys.stdin.readline()
        if not answer:
            raise EOFError
        return answer.rstrip("\n")


def run(argv: list[str], check=True) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, text=True, capture_output=True)


def apply_timezone(zone: str) -> None:
    if not zone:
        return
    source = f"/usr/share/zoneinfo/{zone}"
    if not os.path.exists(source):
        return
    try:
        run(["timedatectl", "set-timezone", zone])
    except (OSError, subprocess.CalledProcessError):
        target = "/etc/localtime"
        if os.path.lexists(target):
            os.unlink(target)
        os.symlink(source, target)


def create_account(username: str, full_name: str, password: str) -> None:
    run(useradd_argv(username, full_name))
    # chpasswd's exit status is inspected below, so the run must not raise.
    changer = subprocess.run(
        ["chpasswd"],
        input=f"{username}:{password}\n",
        text=True,
        capture_output=True,
        check=False,
    )
    if changer.returncode != 0:
        raise RuntimeError(changer.stderr.strip() or "chpasswd failed")


def state_conf_text(username: str, session: str = "zaod") -> str:
    """SDDM's remembered-account file, so the login box opens on the new name."""
    return f"[Last]\nSession={session}\nUser={username}\n"


def remember_login(username: str) -> None:
    target = "/var/lib/sddm/state.conf"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(state_conf_text(username))
        import pwd

        try:
            entry = pwd.getpwnam("sddm")
        except KeyError:
            return
        os.chown(target, entry.pw_uid, entry.pw_gid)
    except OSError:
        pass


def mark_done(username: str, mode: str) -> None:
    os.makedirs(os.path.dirname(DONE_FILE), exist_ok=True)
    with open(DONE_FILE, "w", encoding="utf-8") as handle:
        handle.write(f"account={username}\nmode={mode}\nfinished={int(time.time())}\n")


def is_live() -> bool:
    return os.path.exists(LIVE_MARKER) or os.path.exists("/etc/sddm.conf.d/zaod-live.conf")


def wizard(console: Console, passwd_path: str = PASSWD_FILE, dry_run: bool = False) -> int:
    with open(passwd_path, encoding="utf-8") as passwd:
        accounts = parse_accounts(passwd.read())
    if not needs_onboarding(accounts):
        console.say("A Zaod OS account already exists; skipping onboarding.")
        return 0

    live = is_live()
    console.clear()
    console.rule("Welcome to Zaod OS")
    console.say("This machine has no account yet. Let's create yours.")
    console.say("Everything stays on this computer, and nothing is sent anywhere.")
    if live:
        console.say()
        console.say("You are running the live image, so this account lasts until you")
        console.say("power off. Press L to skip and use the demo account zaodlive.")

    while True:
        full_name = console.ask("Your name")
        if live and full_name.lower() in {"l", "skip"}:
            # The banner offers this, so it has to work: skipping leaves the demo
            # account as the only way in and lets the boot carry on to the login
            # screen instead of sitting on the wizard.
            console.say("Skipping setup for now. Sign in with the demo account:")
            console.say("  user: zaodlive    password: zaod")
            console.say("To create your own account, run: sudo systemctl restart zaod-oobe")
            return 0
        if not full_name:
            console.say("A name is needed so the account has a label.")
            continue
        suggestion = suggest_username(full_name)
        username = console.ask("Account name", suggestion)
        ok, reason = validate_username(username, accounts)
        if not ok:
            console.say(reason)
            continue
        break

    while True:
        password = console.ask_secret("Password")
        ok, reason = validate_password(password, username)
        if not ok:
            console.say(reason)
            continue
        again = console.ask_secret("Password again")
        if password != again:
            console.say("The two passwords do not match.")
            continue
        break

    zones = timezone_choices()
    zone = ""
    if zones:
        while True:
            query = console.ask("Time zone (type a city, blank to skip)")
            if not query:
                break
            matches = match_timezones(query, zones)
            if len(matches) == 1:
                zone = matches[0]
                console.say(f"Using {zone}.")
                break
            if matches:
                console.say("Which one?")
                for index, candidate in enumerate(matches, start=1):
                    console.say(f"  {index}. {candidate}")
                pick = console.ask("Number", "1")
                if pick.isdigit() and 1 <= int(pick) <= len(matches):
                    zone = matches[int(pick) - 1]
                    break
                continue
            console.say("No time zone matched that; try a region, like Karachi or Europe.")

    console.rule("Ready")
    console.say(f"  name:      {full_name}")
    console.say(f"  account:   {username}")
    console.say("  admin:     yes (wheel, sudo with this password)")
    if zone:
        console.say(f"  time zone: {zone}")
    console.say()
    answer = console.ask("Create this account? [Y/n]").lower()
    if answer not in {"", "y", "yes"}:
        console.say("Nothing was created. The setup will ask again next boot.")
        return 1

    if dry_run:
        console.say("Dry run: " + " ".join(useradd_argv(username, full_name)))
        console.say(f"Dry run: password would be set for {username}")
        return 0

    try:
        create_account(username, full_name, password)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        console.say(f"Could not create the account: {error}")
        return 1
    apply_timezone(zone)
    remember_login(username)
    mark_done(username, "live" if live else "installed")
    console.say()
    console.say(f"Account {username} is ready. Starting the desktop...")
    time.sleep(1)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Zaod OS first-boot onboarding")
    parser.add_argument("--check", action="store_true", help="report whether onboarding is needed")
    parser.add_argument("--passwd", default=PASSWD_FILE, help="alternate passwd file (testing)")
    parser.add_argument("--dry-run", action="store_true", help="walk the wizard without creating")
    args = parser.parse_args(argv)

    if args.check:
        with open(args.passwd, encoding="utf-8") as handle:
            accounts = parse_accounts(handle.read())
        print("onboarding" if needs_onboarding(accounts) else "ready")
        return 0

    try:
        return wizard(Console(), passwd_path=args.passwd, dry_run=args.dry_run)
    except (EOFError, KeyboardInterrupt):
        print("\nOnboarding cancelled; nothing was changed.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
