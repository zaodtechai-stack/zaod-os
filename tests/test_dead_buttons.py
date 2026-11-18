"""The buttons and keys the deep search found dead stay alive.

Three real defects came out of clicking through the whole OS: the Print key ran a
program the image did not contain, the panel's Lock button ran "labwc -k" (labwc
has no lock mode, so the click did nothing) and starting an installed app from the
store leaked a raw ImportError traceback instead of a message. These tests fail on
any of those coming back.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


# ---- the Print key -----------------------------------------------------------

def test_screenshot_helper_ships_and_is_installed():
    helper = REPO / "desktop" / "shell" / "zaod-screenshot"
    assert helper.is_file(), "the Print key is bound to zaod-screenshot and it must exist"
    assert os.access(helper, os.X_OK), "zaod-screenshot must be executable"
    apply = (REPO / "desktop" / "scripts" / "apply-desktop.sh").read_text()
    assert "zaod-screenshot" in apply, "zaod-screenshot is never copied into the image"
    assert "/usr/local/bin/zaod-screenshot" in apply, "the Print key calls /usr/local/bin/zaod-screenshot"


def test_print_key_and_lock_key_are_bound():
    rc = (REPO / "desktop" / "shell" / "labwc" / "rc.xml").read_text()
    assert "/usr/local/bin/zaod-screenshot" in rc, "Print must call the helper by full path"
    assert 'key="W-l"' in rc and "swaylock" in rc, "Super+L must lock the screen"
    assert 'key="W-S-s"' in rc, "Super+Shift+S should take a region screenshot"


def _fake_tools(tmp_path, extra=()):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tools = {
        "grim": '#!/bin/sh\nout=""\nfor a in "$@"; do out="$a"; done\nprintf "PNG" > "$out"\n',
        "wl-copy": '#!/bin/sh\ncat > "$FAKE_CLIP"\n',
    }
    for name, body in tools.items():
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    for name, body in extra:
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def test_print_key_saves_a_picture_and_copies_it(tmp_path):
    bin_dir = _fake_tools(tmp_path)
    clip = tmp_path / "clipboard"
    env = {
        "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "FAKE_CLIP": str(clip),
    }
    result = subprocess.run(
        [str(REPO / "desktop" / "shell" / "zaod-screenshot")],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    saved = Path(result.stdout.strip())
    assert saved.is_file(), "the screenshot file was not written"
    assert saved.parent == tmp_path / "Pictures" / "Screenshots"
    assert saved.read_bytes() == b"PNG"
    assert clip.is_file() and clip.read_bytes() == b"PNG", "the picture was not put on the clipboard"


def test_cancelling_a_region_shot_is_not_an_error(tmp_path):
    # slurp exits non-zero when the person presses Esc; that must be silent
    bin_dir = _fake_tools(tmp_path, extra=[("slurp", "#!/bin/sh\nexit 1\n")])
    env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(tmp_path)}
    result = subprocess.run(
        [str(REPO / "desktop" / "shell" / "zaod-screenshot"), "--region"],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not list((tmp_path / "Pictures").rglob("*.png")) if (tmp_path / "Pictures").exists() else True


def test_a_zero_byte_capture_is_reported_as_a_failure(tmp_path):
    bin_dir = _fake_tools(tmp_path, extra=[("grim", "#!/bin/sh\nout=\"\"\nfor a in \"$@\"; do out=\"$a\"; done\n: > \"$out\"\n")])
    env = {"PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(tmp_path)}
    result = subprocess.run(
        [str(REPO / "desktop" / "shell" / "zaod-screenshot")],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    assert result.returncode == 1
    assert "could not capture" in result.stderr


# ---- the Lock button ---------------------------------------------------------

def test_panel_lock_uses_a_real_lock_screen():
    panel = (REPO / "desktop" / "shell" / "panel.py").read_text()
    assert '"labwc", "-k"' not in panel, "labwc has no lock mode; that button did nothing"
    assert "/usr/bin/swaylock" in panel, "Lock must start the lock screen the image ships"
    assert "swaylock" in (REPO / "rootfs" / "packages.list").read_text(), \
        "swaylock must be installed into the image or Lock cannot work"


def test_panel_power_buttons_report_a_command_that_cannot_start():
    panel = (REPO / "desktop" / "shell" / "panel.py").read_text()
    # every power-row button goes through act(), which tells the person when the
    # command is missing instead of failing silently
    assert "def act(self" in panel
    assert "is not available on this system" in panel
    for command in ('"reboot"', '"poweroff"'):
        assert command in panel
    assert 'lambda _b, c=command: run(*c)' not in panel, "power buttons must not swallow the failure"


# ---- the store ---------------------------------------------------------------

def test_store_launch_failure_is_a_message_not_a_traceback():
    source = (REPO / "apps" / "store" / "payload" / "main.py").read_text()
    assert "This build cannot start apps from the store" in source, \
        "a missing Gio must be reported, not raised"
    assert "could not start" in source, "a failed launch must be reported to the person"


# ---- the live image must reach the desktop -----------------------------------

def test_live_boot_never_waits_on_the_text_wizard():
    """A live boot sat on "Your name:" and the whole desktop looked dead.

    zaod-oobe.service owns tty1 and runs Before=display-manager.service, so an
    interactive wizard on live media keeps SDDM, the panel and every app off the
    screen. The live image has the demo account, so it must skip the wizard.
    """
    unit = (REPO / "desktop" / "systemd" / "zaod-oobe.service").read_text()
    assert "Before=display-manager.service" in unit
    assert "ConditionPathExists=!/etc/sddm.conf.d/zaod-live.conf" in unit, \
        "live media must not run the blocking text wizard"
    assert "ConditionPathExists=!/etc/zaod/oobe-done" in unit


def test_live_image_ships_the_demo_account_it_skips_the_wizard_for():
    """Skipping the wizard is only safe if the demo account can sign in."""
    users = []
    for path in (REPO / "rootfs").rglob("*"):
        if path.name in {"passwd", "user-setup.sh"}:
            users.append(path)
    live = (REPO / "desktop" / "sddm" / "sddm.conf.d" / "zaod-live.conf").read_text()
    assert "zaodlive" in live, "the live config must name the demo account"
    # the account itself is created by the live image build
    scripts = " ".join(
        p.read_text(errors="ignore") for p in (REPO / "scripts").glob("*.sh")
    ) + " ".join(
        p.read_text(errors="ignore") for p in (REPO / "rootfs").rglob("*.sh")
        if p.is_file()
    )
    assert "zaodlive" in scripts, "something must create the zaodlive account"


def test_panel_autostart_restarts_it_once_and_keeps_a_log():
    """The panel is the desktop; one crash must not leave a bare wallpaper."""
    auto = (REPO / "desktop" / "shell" / "labwc" / "autostart").read_text()
    assert "panel.log" in auto, "a dead panel must leave evidence"
    assert "restarting once" in auto, "the panel should be restarted once"


def test_live_media_signs_in_by_itself():
    """A live boot must land on the desktop, not on a password box.

    The owner's words: "desktop to open hui but aage kuch nahi hota, koi app open
    he nahi hota". A login prompt on media whose password was never given looks
    exactly like a desktop that opens nothing, so the live session signs in.
    """
    live = (REPO / "desktop" / "sddm" / "sddm.conf.d" / "zaod-live.conf").read_text()
    assert "[Autologin]" in live
    assert "User=zaodlive" in live
    assert "Session=zaod" in live

    # the installed system must still ask for a password
    installed = (REPO / "desktop" / "sddm" / "sddm.conf.d" / "zaod.conf").read_text()
    # an [Autologin] block without User= never signs anyone in, which is what the
    # installed image keeps; a User= line would be a real hole
    assert "User=" not in installed
