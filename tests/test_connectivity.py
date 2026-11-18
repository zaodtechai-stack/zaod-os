"""Wi-Fi and Bluetooth behave as the real tools do: scan, wrong password, success.

A stand-in ``nmcli``/``bluetoothctl`` prints exactly what the real ones print
(including the escaped colons in terse mode and the "Secrets were required"
failure for a wrong password), and the tests drive WifiManager/BluetoothManager
against them. The one rule they enforce above all: a password is never on a
command line, where any user can read it with ``ps``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODULE = REPO / "apps" / "lib" / "connectivity.py"

NMCLI = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FAKE_NM_STATE"]
state = json.load(open(state_path))
argv = sys.argv[1:]
open(os.environ["FAKE_NM_LOG"], "a").write(json.dumps(argv) + "\n")

def save():
    json.dump(state, open(state_path, "w"))

args = [a for a in argv if a not in ("--wait", "30", "--ask")]
terse = "-t" in args

if args[:2] == ["-t", "-f"] and args[2] == "WIFI" and args[3] == "radio":
    print("enabled" if state["radio"] else "disabled"); sys.exit(0)
if args[:3] == ["radio", "wifi", "on"]:
    state["radio"] = True; save(); sys.exit(0)
if args[:3] == ["radio", "wifi", "off"]:
    state["radio"] = False; save(); sys.exit(0)
if "TYPE,STATE" in args and "device" in args:
    print("wifi:disconnected" if state.get("adapter", True) else "ethernet:connected"); sys.exit(0)
if "DEVICE,TYPE,STATE" in args:
    cur = state.get("connected")
    print("wlan0:wifi:" + ("connected" if cur else "disconnected")); sys.exit(0)
if args[:3] == ["device", "wifi", "rescan"]:
    sys.exit(0)
if "ACTIVE,SSID" in args:
    for ap in state["aps"]:
        print(("yes" if ap["ssid"] == state.get("connected") else "no") + ":" + ap["ssid"].replace(":", "\\:"))
    sys.exit(0)
if "IN-USE,SSID,SIGNAL,SECURITY,BSSID" in args:
    for ap in state["aps"]:
        mark = "*" if ap["ssid"] == state.get("connected") else " "
        bssid = ap["bssid"].replace(":", "\\:")
        print(f"{mark}:{ap['ssid'].replace(':', chr(92) + ':')}:{ap['signal']}:{ap['security']}:{bssid}")
    sys.exit(0)
if "IP4.ADDRESS" in args:
    if state.get("connected"):
        print("IP4.ADDRESS[1]:192.168.1.42/24")
    sys.exit(0)
if "NAME,TYPE" in args:
    for name in state.get("saved", []):
        print(name.replace(":", "\\:") + ":802-11-wireless")
    sys.exit(0)
if args[:3] == ["device", "wifi", "connect"]:
    ssid = args[3]
    aps = {a["ssid"]: a for a in state["aps"]}
    if ssid not in aps:
        sys.stderr.write(f"Error: No network with SSID '{ssid}' found.\n"); sys.exit(10)
    ap = aps[ssid]
    if ap["security"] not in ("", "--"):
        secret = sys.stdin.readline().rstrip("\n")
        if secret != ap["password"]:
            sys.stderr.write("Error: Connection activation failed: (7) Secrets were required, but not provided.\n")
            sys.exit(4)
    state["connected"] = ssid
    if ssid not in state["saved"]:
        state["saved"].append(ssid)
    save()
    print(f"Device 'wlan0' successfully activated with 'uuid'.")
    sys.exit(0)
if args[:3] == ["connection", "delete", "id"]:
    ssid = args[3]
    if ssid in state["saved"]:
        state["saved"].remove(ssid)
        if state.get("connected") == ssid:
            state["connected"] = None
        save(); print(f"Connection '{ssid}' successfully deleted."); sys.exit(0)
    sys.stderr.write(f"Error: unknown connection '{ssid}'.\n"); sys.exit(10)
if args[:2] == ["device", "disconnect"]:
    state["connected"] = None; save(); sys.exit(0)
sys.stderr.write("Error: unexpected arguments: " + " ".join(argv) + "\n"); sys.exit(2)
'''

BLUETOOTHCTL = r'''#!/usr/bin/env python3
import json, os, sys
state_path = os.environ["FAKE_BT_STATE"]
state = json.load(open(state_path))
argv = sys.argv[1:]
open(os.environ["FAKE_BT_LOG"], "a").write(json.dumps(argv) + "\n")
def save(): json.dump(state, open(state_path, "w"))
if argv and argv[0] == "--timeout":
    argv = argv[2:]
stdin_lines = [] if sys.stdin.isatty() else sys.stdin.read().splitlines()
if not argv and stdin_lines:
    out = []
    for line in stdin_lines:
        parts = line.split()
        if parts and parts[0] == "pair":
            dev = state["devices"].get(parts[1])
            if dev is None or not dev["discoverable"]:
                out.append("Failed to pair: org.bluez.Error.AuthenticationFailed"); continue
            dev["paired"] = True; out.append("Pairing successful")
        if parts and parts[0] == "connect" and state["devices"].get(parts[1], {}).get("paired"):
            state["devices"][parts[1]]["connected"] = True; out.append("Connection successful")
    save(); print("\n".join(out)); sys.exit(0)
cmd = argv[0] if argv else ""
if cmd == "list":
    print("Controller 00:11:22:33:44:55 laptop [default]" if state["adapter"] else ""); sys.exit(0)
if cmd == "show":
    print("Controller 00:11:22:33:44:55\n\tPowered: " + ("yes" if state["power"] else "no")); sys.exit(0)
if cmd == "power":
    state["power"] = argv[1] == "on"; save(); print(f"Changing power {argv[1]} succeeded"); sys.exit(0)
if cmd == "scan":
    sys.exit(0)
if cmd == "devices":
    for mac, d in state["devices"].items():
        print(f"Device {mac} {d['name']}")
    sys.exit(0)
if cmd == "info":
    d = state["devices"].get(argv[1])
    if not d: print(f"Device {argv[1]} not available"); sys.exit(1)
    print(f"Device {argv[1]} (public)\n\tName: {d['name']}\n\tAlias: {d['name']}\n\tIcon: {d.get('icon','')}\n"
          f"\tPaired: {'yes' if d['paired'] else 'no'}\n\tConnected: {'yes' if d['connected'] else 'no'}\n\tRSSI: -61")
    sys.exit(0)
if cmd == "connect":
    d = state["devices"].get(argv[1])
    if d and d["paired"] and d["discoverable"]:
        d["connected"] = True; save(); print("Connection successful"); sys.exit(0)
    print("Failed to connect: org.bluez.Error.Failed"); sys.exit(1)
if cmd == "disconnect":
    state["devices"][argv[1]]["connected"] = False; save(); print("Successful disconnected"); sys.exit(0)
if cmd == "remove":
    state["devices"].pop(argv[1], None); save(); print("Device has been removed"); sys.exit(0)
print("unexpected: " + " ".join(argv)); sys.exit(2)
'''


def load_module():
    spec = importlib.util.spec_from_file_location("connectivity_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def fakes(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("nmcli", NMCLI), ("bluetoothctl", BLUETOOTHCTL)):
        script = bin_dir / name
        script.write_text(body)
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    nm_state = tmp_path / "nm.json"
    nm_state.write_text(
        json.dumps(
            {
                "radio": True,
                "connected": None,
                "saved": [],
                "aps": [
                    {"ssid": "HomeNet", "signal": 82, "security": "WPA2", "bssid": "AA:BB:CC:DD:EE:01", "password": "correct horse"},
                    {"ssid": "HomeNet", "signal": 40, "security": "WPA2", "bssid": "AA:BB:CC:DD:EE:02", "password": "correct horse"},
                    {"ssid": "Cafe: Free", "signal": 58, "security": "", "bssid": "AA:BB:CC:DD:EE:03", "password": ""},
                    {"ssid": "Neighbour", "signal": 21, "security": "WPA2", "bssid": "AA:BB:CC:DD:EE:04", "password": "secret"},
                    {"ssid": "", "signal": 70, "security": "WPA2", "bssid": "AA:BB:CC:DD:EE:05", "password": ""},
                ],
            }
        )
    )
    bt_state = tmp_path / "bt.json"
    bt_state.write_text(
        json.dumps(
            {
                "adapter": True,
                "power": True,
                "devices": {
                    "11:22:33:44:55:66": {"name": "Zaod Buds", "paired": False, "connected": False, "icon": "audio-headphones", "discoverable": True},
                    "AA:AA:AA:AA:AA:AA": {"name": "Old Speaker", "paired": True, "connected": False, "icon": "audio-card", "discoverable": False},
                },
            }
        )
    )
    log = tmp_path / "nm.log"
    bt_log = tmp_path / "bt.log"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_NM_STATE", str(nm_state))
    monkeypatch.setenv("FAKE_NM_LOG", str(log))
    monkeypatch.setenv("FAKE_BT_STATE", str(bt_state))
    monkeypatch.setenv("FAKE_BT_LOG", str(bt_log))
    return {"nm": nm_state, "bt": bt_state, "nm_log": log, "bt_log": bt_log}


def test_scan_merges_access_points_and_decodes_escaped_colons(fakes):
    module = load_module()
    points = module.WifiManager().scan()
    names = [p.ssid for p in points]
    assert names == ["HomeNet", "Cafe: Free", "Neighbour"], "hidden SSIDs dropped, duplicates merged"
    home = points[0]
    assert home.signal == 82, "the strongest access point of a network wins"
    assert home.secured and home.bars == 4
    assert not points[1].secured and points[1].ssid == "Cafe: Free"


def test_wrong_password_is_reported_and_leaves_no_profile(fakes):
    module = load_module()
    manager = module.WifiManager()
    with pytest.raises(module.NetworkError, match="Wrong password"):
        manager.connect("HomeNet", "not the password")
    state = json.loads(fakes["nm"].read_text())
    assert state["connected"] is None
    assert "HomeNet" not in state["saved"], "a failed attempt must not keep the bad password"


def test_correct_password_connects_and_is_remembered(fakes):
    module = load_module()
    manager = module.WifiManager()
    assert manager.connect("HomeNet", "correct horse") == "Connected to HomeNet"
    assert manager.active() == ("HomeNet", "192.168.1.42")
    state = json.loads(fakes["nm"].read_text())
    assert state["connected"] == "HomeNet" and "HomeNet" in state["saved"]


def test_the_password_never_appears_on_a_command_line(fakes):
    module = load_module()
    module.WifiManager().connect("HomeNet", "correct horse")
    lines = fakes["nm_log"].read_text().splitlines()
    assert lines, "the fake nmcli was never called"
    for line in lines:
        assert "correct horse" not in line, f"password leaked into argv: {line}"
    connect_calls = [json.loads(line) for line in lines if '"connect"' in line]
    assert connect_calls and "--ask" in connect_calls[0]


def test_open_network_needs_no_password(fakes):
    module = load_module()
    assert module.WifiManager().connect("Cafe: Free") == "Connected to Cafe: Free"


def test_out_of_range_network_is_explained(fakes):
    module = load_module()
    with pytest.raises(module.NetworkError, match="out of range"):
        module.WifiManager().connect("Nowhere", "x")


def test_radio_off_blocks_scanning_with_a_clear_message(fakes):
    module = load_module()
    manager = module.WifiManager()
    manager.set_radio(False)
    assert manager.radio_enabled() is False
    with pytest.raises(module.NetworkError, match="turned off"):
        manager.scan()
    manager.set_radio(True)
    assert manager.radio_enabled() is True


def test_disconnect_and_forget(fakes):
    module = load_module()
    manager = module.WifiManager()
    manager.connect("HomeNet", "correct horse")
    assert manager.disconnect() == "Disconnected"
    assert manager.forget("HomeNet") == "Forgot HomeNet"
    with pytest.raises(module.NetworkError):
        manager.forget("HomeNet")


def test_bluetooth_scan_pair_connect_remove(fakes):
    module = load_module()
    manager = module.BluetoothManager()
    devices = manager.scan(seconds=1)
    buds = next(d for d in devices if d.name == "Zaod Buds")
    assert not buds.paired and buds.icon == "audio-headphones"
    assert manager.pair(buds.address).startswith("Paired with")
    state = json.loads(fakes["bt"].read_text())
    assert state["devices"][buds.address]["paired"] and state["devices"][buds.address]["connected"]
    assert manager.disconnect(buds.address) == "Disconnected"
    assert manager.remove(buds.address) == "Device removed"


def test_bluetooth_failures_have_human_messages(fakes):
    module = load_module()
    manager = module.BluetoothManager()
    with pytest.raises(module.NetworkError):
        manager.pair("AA:AA:AA:AA:AA:AA")  # a device that is not discoverable
    with pytest.raises(module.NetworkError, match="not a Bluetooth address"):
        manager.connect("../../etc/passwd")
    manager.set_power(False)
    with pytest.raises(module.NetworkError, match="turned off"):
        manager.scan(seconds=1)
