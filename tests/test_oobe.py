#!/usr/bin/env python3
"""Prove the first-boot onboarding cannot hand out a broken account.

The wizard runs once, on a machine with nobody to sign in as, and whatever it
writes becomes the only way in. Every rule it applies is a pure function, so the
rules are tested here instead of being discovered on someone's first boot.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE = ROOT / "desktop/oobe/oobe.py"

spec = importlib.util.spec_from_file_location("zaod_oobe", MODULE)
oobe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oobe)

SYSTEM_PASSWD = """\
root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
zaodlive:x:1000:1000::/home/zaodlive:/bin/bash
"""


def test_live_image_still_needs_an_account():
    accounts = oobe.parse_accounts(SYSTEM_PASSWD)
    assert oobe.needs_onboarding(accounts) is True
    assert [a["name"] for a in oobe.human_accounts(accounts)] == []


def test_created_account_ends_onboarding():
    accounts = oobe.parse_accounts(SYSTEM_PASSWD + "hassan:x:1001:1001:Hassan:/home/hassan:/bin/bash\n")
    assert oobe.needs_onboarding(accounts) is False
    assert [a["name"] for a in oobe.human_accounts(accounts)] == ["hassan"]


def test_reserved_and_taken_names_are_refused():
    accounts = oobe.parse_accounts(SYSTEM_PASSWD + "hassan:x:1001:1001::/home/hassan:/bin/bash\n")
    for name in ("zaodlive", "root", "Zaod", "1hassan", "has san", "", "a" * 33):
        ok, reason = oobe.validate_username(name, accounts)
        assert ok is False, name
        assert reason


def test_good_names_are_accepted():
    accounts = oobe.parse_accounts(SYSTEM_PASSWD)
    for name in ("hassan", "hassan-ali", "ali2", "zainab"):
        ok, reason = oobe.validate_username(name, accounts)
        assert ok is True, (name, reason)


def test_username_suggestion_is_legal():
    assert oobe.suggest_username("Hassan Ali") == "hassan-ali"
    assert oobe.suggest_username("  ZAOD  Tech ") == "zaod-tech"
    assert oobe.suggest_username("3D Printing") == "u3d-printing"
    assert oobe.suggest_username("!!!") == ""
    assert len(oobe.suggest_username("a" * 80)) <= 32


def test_password_rules():
    assert oobe.validate_password("short", "hassan")[0] is False
    assert oobe.validate_password("Hassan123", "hassan")[0] is False
    assert oobe.validate_password("aaaaaaaaaa", "hassan")[0] is False
    assert oobe.validate_password("password", "hassan")[0] is False
    assert oobe.validate_password("zaodlive", "hassan")[0] is False
    assert oobe.validate_password("correct-horse", "hassan")[0] is True


def test_useradd_gets_a_home_sudo_and_a_label():
    argv = oobe.useradd_argv("hassan", "Hassan Ali")
    assert argv[0] == "useradd"
    assert "--create-home" in argv
    assert argv[argv.index("--comment") + 1] == "Hassan Ali"
    assert argv[argv.index("--groups") + 1] == oobe.GROUPS
    assert "wheel" in oobe.GROUPS.split(",")
    assert argv[-1] == "hassan"


def test_timezone_matching_finds_a_city():
    zones = ["Asia/Karachi", "Asia/Kolkata", "Europe/London", "Etc/UTC"]
    assert oobe.match_timezones("karachi", zones) == ["Asia/Karachi"]
    assert oobe.match_timezones("asia", zones) == ["Asia/Karachi", "Asia/Kolkata"]
    assert oobe.match_timezones("atlantis", zones) == []
    assert oobe.match_timezones("", zones) == []


def test_remembered_login_points_at_the_new_account():
    text = oobe.state_conf_text("hassan")
    assert text == "[Last]\nSession=plasmawayland\nUser=hassan\n"


def test_check_mode_reports_onboarding_then_ready(tmp_path, capsys):
    live = tmp_path / "passwd"
    live.write_text(SYSTEM_PASSWD, encoding="utf-8")
    assert oobe.main(["--check", "--passwd", str(live)]) == 0
    assert capsys.readouterr().out.strip() == "onboarding"

    live.write_text(SYSTEM_PASSWD + "hassan:x:1001:1001::/home/hassan:/bin/bash\n", encoding="utf-8")
    assert oobe.main(["--check", "--passwd", str(live)]) == 0
    assert capsys.readouterr().out.strip() == "ready"


def test_live_skip_creates_no_account(tmp_path, monkeypatch):
    """The live banner offers "Press L to skip"; that must not create a user 'l'."""
    import io
    import sys as _sys

    passwd = tmp_path / "passwd"
    passwd.write_text(SYSTEM_PASSWD)
    out = io.StringIO()
    monkeypatch.setattr(oobe, "is_live", lambda: True)
    monkeypatch.setattr(_sys, "stdin", io.StringIO("l\n"))
    code = oobe.wizard(oobe.Console(out), passwd_path=str(passwd))
    assert code == 0
    assert passwd.read_text() == SYSTEM_PASSWD
    printed = out.getvalue()
    assert "zaodlive" in printed and "systemctl restart zaod-oobe" in printed


def test_installed_media_do_not_offer_the_demo_account(tmp_path, monkeypatch):
    """On installed media there is no demo account, so 'l' stays a name."""
    import io
    import sys as _sys

    passwd = tmp_path / "passwd"
    passwd.write_text(SYSTEM_PASSWD.replace("zaodlive:x:1000:1000::/home/zaodlive:/bin/bash\n", ""))
    out = io.StringIO()
    monkeypatch.setattr(oobe, "is_live", lambda: False)
    monkeypatch.setattr(_sys, "stdin", io.StringIO("l\n"))
    # 'l' is a name here, so the wizard moves on to the account name and then runs
    # out of input instead of returning the "skipped" path.
    try:
        oobe.wizard(oobe.Console(out), passwd_path=str(passwd))
    except EOFError:
        pass
    printed = out.getvalue()
    assert "Account name" in printed
    assert "zaodlive" not in printed
