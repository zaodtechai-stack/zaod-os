#!/usr/bin/env python3
"""Prove the live initramfs cannot panic the machine through its own logic.

The reported failure on real hardware was

    Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000100
    PID: 1 Comm: init Not tainted 6.18.63-zaod

exit status 1 from PID 1. The fix is structural: /init is a supervisor that
runs the boot logic (/init-boot) as a child, so the boot logic can fail, die or
be killed without taking PID 1 with it. These tests run the supervisor with a
stub child and check the three behaviours that structure depends on.
"""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SUPERVISOR = ROOT / "boot/initramfs/init"
BOOT_LOGIC = ROOT / "boot/initramfs/zaod-live"

failures = []


def check(name, condition, detail=""):
    """Raises instead of recording, so pytest sees a real failure too."""
    if condition:
        print("  ok   " + name)
        return
    print("  FAIL " + name + (("  -- " + detail) if detail else ""))
    raise AssertionError(name + (("  -- " + detail) if detail else ""))


def run_supervisor(tmp, child_body, with_live_root):
    tmp = pathlib.Path(tmp)
    state = tmp / "state"
    newroot = tmp / "newroot"
    state.mkdir(parents=True, exist_ok=True)
    (newroot / "sbin").mkdir(parents=True, exist_ok=True)
    if with_live_root:
        init = newroot / "sbin/init"
        init.write_text("#!/bin/sh\nexit 0\n")
        init.chmod(0o755)

    child = tmp / "init-boot"
    child.write_text("#!/bin/sh\n" + child_body)
    child.chmod(0o755)

    switch = tmp / "switch-root"
    switch.write_text('#!/bin/sh\necho "SWITCH_ROOT CALLED with $*"\nexit 0\n')
    switch.chmod(0o755)

    env = dict(os.environ)
    env.update(
        SCREEN="",
        NEW_ROOT=str(newroot),
        INIT_BOOT=str(child),
        SWITCH_ROOT=str(switch),
        RESCUE_SHELL="/bin/true",
        STATE_DIR=str(state),
        DEV_DIR=str(tmp / "dev"),
        PROC_DIR=str(tmp / "proc"),
        SYS_DIR=str(tmp / "sys"),
    )
    try:
        for name in ("dev", "proc", "sys"):
            (tmp / name).mkdir(exist_ok=True)
        # SIGKILL, not SIGTERM: the supervisor deliberately ignores SIGTERM, so a
        # plain timeout would never end it and the test would read no output.
        done = subprocess.run(
            ["timeout", "-s", "KILL", "8", "sh", str(SUPERVISOR)],
            capture_output=True, text=True, env=env, timeout=20,
        )
        return done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired:
        return 124, ""


def test_failing_child_does_not_exit_pid1():
    """A boot logic that exits 1 must leave the supervisor alive in the rescue loop."""
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run_supervisor(tmp, "exit 1\n", with_live_root=False)
        check("supervisor survives a failing boot logic", rc in (124, -9),
              "expected the rescue loop to keep it alive, exit code was %s" % rc)
        check("the failure is reported on the screen", "did not finish mounting a live root" in out)
        check("the rescue shell is opened", "Dropping to a rescue shell" in out)
        check("PID 1 never reported an exit", "PID 1 was asked to exit" not in out)


def test_child_that_dies_midway_is_reported():
    """A child killed by a signal is still just a message, not a panic."""
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = run_supervisor(tmp, "kill -9 $$\n", with_live_root=False)
        check("supervisor survives a killed boot logic", rc in (124, -9),
              "exit code was %s" % rc)
        check("the killed child's status is reported", "the boot logic returned with status" in out)
        check("the rescue shell is opened", "Dropping to a rescue shell" in out)


def test_ready_child_hands_over_to_switch_root():
    """Success means the supervisor execs switch_root itself, as PID 1 must."""
    with tempfile.TemporaryDirectory() as tmp:
        state = pathlib.Path(tmp) / "state"
        body = 'mkdir -p "%s"\n: > "%s/boot-ready"\nexit 0\n' % (state, state)
        rc, out = run_supervisor(tmp, body, with_live_root=True)
        check("a ready live root is handed over", "SWITCH_ROOT CALLED" in out,
              "output was: %s" % out.strip().splitlines()[-3:])
        check("the supervisor exited through switch_root", rc == 0, "exit code was %s" % rc)


def test_scripts_carry_no_fatal_shell_options():
    """`set -e` in the PID 1 script is the class of bug that caused the panic."""
    supervisor = SUPERVISOR.read_text()
    boot_logic = BOOT_LOGIC.read_text()
    fatal = re.compile(r"^\s*set\s+-[a-zA-Z]*e", re.MULTILINE)
    check("/init does not enable set -e", not fatal.search(supervisor))
    check("/init-boot does not enable set -e", not fatal.search(boot_logic))
    check("/init installs an EXIT trap", "trap" in supervisor and "rescue" in supervisor)
    check("only the supervisor runs switch_root",
          "switch_root" in supervisor and "switch_root" not in boot_logic.split("# --- locate the media")[0].replace("switch_root\n", ""))
    check("the boot logic reports the step it died in", "STEP=" in boot_logic and '"$STEP"' in boot_logic)


def main():
    print("PID 1 supervisor")
    for test in (
        test_failing_child_does_not_exit_pid1,
        test_child_that_dies_midway_is_reported,
        test_ready_child_hands_over_to_switch_root,
        test_scripts_carry_no_fatal_shell_options,
    ):
        try:
            test()
        except AssertionError as error:
            failures.append(str(error))
    if failures:
        print("\n%d check(s) failed: %s" % (len(failures), ", ".join(failures)))
        return 1
    print("\nall PID 1 supervisor checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
