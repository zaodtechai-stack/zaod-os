"""Wi-Fi and Bluetooth for the Zaod Control Center, through the system's own tools.

Nothing here is decorative. Wi-Fi goes through NetworkManager (``nmcli``) and
Bluetooth through BlueZ (``bluetoothctl``), and every function reports what the
tool actually said, so a wrong password shows as a wrong password and not as a
button that quietly did nothing.

Passwords are never placed on a command line (where ``ps`` can read them): a
connection profile is created with ``nmcli --ask`` and the secret is written to
the process's standard input.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field


class NetworkError(RuntimeError):
    """A network operation failed; the message is fit to show a person."""


@dataclass(frozen=True)
class AccessPoint:
    ssid: str
    signal: int
    security: str
    in_use: bool = False
    bssid: str = ""

    @property
    def secured(self) -> bool:
        return self.security not in ("", "--")

    @property
    def bars(self) -> int:
        """Signal as 0-4 bars, the way every network menu shows it."""
        if self.signal >= 75:
            return 4
        if self.signal >= 55:
            return 3
        if self.signal >= 35:
            return 2
        if self.signal >= 15:
            return 1
        return 0


@dataclass(frozen=True)
class BluetoothDevice:
    address: str
    name: str
    paired: bool = False
    connected: bool = False
    icon: str = ""
    rssi: int | None = None


@dataclass
class Runner:
    """Runs a tool and returns (returncode, stdout, stderr). Replaceable in tests."""

    timeout: int = 30
    extra_env: dict = field(default_factory=dict)

    def __call__(self, argv: list[str], stdin: str | None = None, timeout: int | None = None) -> tuple[int, str, str]:
        executable = shutil.which(argv[0])
        if executable is None:
            raise NetworkError(f"{argv[0]} is not installed on this system")
        try:
            result = subprocess.run(
                [executable, *argv[1:]],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise NetworkError(f"{argv[0]} did not answer in time") from error
        return result.returncode, result.stdout, result.stderr


def split_terse(line: str) -> list[str]:
    """Split one ``nmcli -t`` line on ``:``, honouring the ``\\:`` and ``\\\\`` escapes."""
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields


class WifiManager:
    """Scan, connect, disconnect and forget Wi-Fi networks."""

    def __init__(self, run: Runner | None = None) -> None:
        self.run = run or Runner()

    # ---- radio ---------------------------------------------------------------
    def radio_enabled(self) -> bool:
        code, out, err = self.run(["nmcli", "-t", "-f", "WIFI", "radio"])
        if code != 0:
            raise NetworkError(_first_line(err or out) or "NetworkManager is not running")
        return out.strip().lower() == "enabled"

    def hardware_blocked(self) -> bool:
        """True when a physical switch blocks the radio (software cannot undo it)."""
        try:
            code, out, _ = self.run(["rfkill", "list", "wifi"], timeout=5)
        except NetworkError:
            return False
        return code == 0 and "Hard blocked: yes" in out

    def has_adapter(self) -> bool:
        code, out, _ = self.run(["nmcli", "-t", "-f", "TYPE,STATE", "device"])
        if code != 0:
            return False
        return any(split_terse(line)[:1] == ["wifi"] for line in out.splitlines())

    def set_radio(self, enabled: bool) -> None:
        if enabled and self.hardware_blocked():
            raise NetworkError("Wi-Fi is switched off by a hardware key or switch")
        code, out, err = self.run(["nmcli", "radio", "wifi", "on" if enabled else "off"])
        if code != 0:
            raise NetworkError(_first_line(err or out) or "could not change the Wi-Fi radio")
        if enabled:
            # A soft block that nmcli did not clear (it happens after suspend).
            self.run(["rfkill", "unblock", "wifi"], timeout=5) if shutil.which("rfkill") else None

    # ---- scanning ------------------------------------------------------------
    def scan(self, rescan: bool = True) -> list[AccessPoint]:
        if not self.radio_enabled():
            raise NetworkError("Wi-Fi is turned off")
        if not self.has_adapter():
            raise NetworkError("no Wi-Fi adapter was found")
        if rescan:
            # A rescan can be refused while one is already running; the cached
            # list below is still the freshest there is, so that is not an error.
            self.run(["nmcli", "device", "wifi", "rescan"], timeout=15)
        code, out, err = self.run(
            ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,BSSID", "device", "wifi", "list"]
        )
        if code != 0:
            raise NetworkError(_first_line(err or out) or "could not list Wi-Fi networks")
        return parse_access_points(out)

    # ---- connecting ----------------------------------------------------------
    def saved_profiles(self) -> set[str]:
        code, out, _ = self.run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
        if code != 0:
            return set()
        names = set()
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) >= 2 and parts[1] in ("802-11-wireless", "wifi"):
                names.add(parts[0])
        return names

    def connect(self, ssid: str, password: str | None = None, hidden: bool = False) -> str:
        """Connect to ``ssid``. Returns a short success message or raises NetworkError."""
        if not ssid:
            raise NetworkError("choose a network first")
        if ssid in self.saved_profiles() and not password:
            code, out, err = self.run(["nmcli", "--wait", "30", "connection", "up", "id", ssid], timeout=45)
            if code == 0:
                return f"Connected to {ssid}"
            if "secrets" in (err or out).lower():
                raise NetworkError("the saved password was refused, enter it again")
            raise NetworkError(_explain(err or out, ssid))

        argv = ["nmcli", "--wait", "30", "--ask", "device", "wifi", "connect", ssid]
        if hidden:
            argv += ["hidden", "yes"]
        # --ask reads the secret from stdin: it never appears in `ps`.
        stdin = (password + "\n") if password else None
        if password is None:
            argv.remove("--ask")
        code, out, err = self.run(argv, stdin=stdin, timeout=60)
        if code == 0:
            return f"Connected to {ssid}"
        # A failed attempt must not leave a half-made profile behind: the next try
        # would reuse the wrong password silently.
        self.forget(ssid, quiet=True)
        raise NetworkError(_explain(err or out, ssid))

    def disconnect(self) -> str:
        code, out, _ = self.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"])
        device = ""
        for line in out.splitlines():
            parts = split_terse(line)
            if len(parts) >= 3 and parts[1] == "wifi" and parts[2].startswith("connected"):
                device = parts[0]
        if not device:
            raise NetworkError("not connected to a Wi-Fi network")
        code, out, err = self.run(["nmcli", "device", "disconnect", device])
        if code != 0:
            raise NetworkError(_first_line(err or out) or "could not disconnect")
        return "Disconnected"

    def forget(self, ssid: str, quiet: bool = False) -> str:
        code, out, err = self.run(["nmcli", "connection", "delete", "id", ssid])
        if code != 0 and not quiet:
            raise NetworkError(_first_line(err or out) or f"{ssid} is not a saved network")
        return f"Forgot {ssid}"

    # ---- state ---------------------------------------------------------------
    def active(self) -> tuple[str, str] | None:
        """(ssid, ip address) of the connected Wi-Fi network, if any."""
        code, out, _ = self.run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi", "list"])
        ssid = ""
        if code == 0:
            for line in out.splitlines():
                parts = split_terse(line)
                if len(parts) >= 2 and parts[0] == "yes":
                    ssid = parts[1]
                    break
        if not ssid:
            return None
        code, out, _ = self.run(["nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show"])
        address = ""
        if code == 0:
            for line in out.splitlines():
                parts = split_terse(line)
                if len(parts) >= 2 and parts[0].startswith("IP4.ADDRESS") and parts[1]:
                    address = parts[1].split("/")[0]
                    break
        return ssid, address


def parse_access_points(text: str) -> list[AccessPoint]:
    """Parse ``nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY,BSSID device wifi list``.

    The same network shows up once per access point, so entries are merged by SSID
    keeping the strongest signal, and hidden networks (empty SSID) are dropped.
    """
    best: dict[str, AccessPoint] = {}
    for line in text.splitlines():
        parts = split_terse(line)
        if len(parts) < 5:
            continue
        in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
        bssid = ":".join(parts[4:])
        if not ssid:
            continue
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        point = AccessPoint(ssid, strength, security, in_use.strip() == "*", bssid)
        previous = best.get(ssid)
        if previous is None or point.in_use or (not previous.in_use and point.signal > previous.signal):
            best[ssid] = point
    return sorted(best.values(), key=lambda p: (not p.in_use, -p.signal, p.ssid.lower()))


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _explain(text: str, ssid: str) -> str:
    """Turn nmcli's wording into something a person can act on."""
    lowered = text.lower()
    if "secrets were required" in lowered or "(7)" in lowered or "802.1x" in lowered:
        return "Wrong password. Check it and try again."
    if "no network with ssid" in lowered or "not found" in lowered:
        return f"{ssid} is out of range right now."
    if "timeout" in lowered or "timed out" in lowered:
        return "The network took too long to answer."
    if "ip configuration could not be reserved" in lowered or "dhcp" in lowered:
        return "Connected, but the router did not hand out an address."
    if "not authorized" in lowered or "insufficient privileges" in lowered:
        return "This account is not allowed to change network settings."
    if "unmanaged" in lowered or "not available" in lowered:
        return "The Wi-Fi adapter is not available."
    return _first_line(text) or "Could not connect."


_BT_ADDRESS = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$", re.IGNORECASE)


class BluetoothManager:
    """Power, scan, pair, connect and remove Bluetooth devices through BlueZ."""

    def __init__(self, run: Runner | None = None) -> None:
        self.run = run or Runner()

    def _ctl(self, *args: str, timeout: int = 15) -> str:
        code, out, err = self.run(["bluetoothctl", *args], timeout=timeout)
        text = out + err
        if code != 0 and not text.strip():
            raise NetworkError("Bluetooth is not available")
        return text

    def _check_address(self, address: str) -> None:
        if not _BT_ADDRESS.match(address):
            raise NetworkError("that is not a Bluetooth address")

    def available(self) -> bool:
        try:
            return "Controller" in self._ctl("list", timeout=6)
        except NetworkError:
            return False

    def powered(self) -> bool:
        return "Powered: yes" in self._ctl("show", timeout=8)

    def set_power(self, enabled: bool) -> None:
        if enabled:
            try:
                self.run(["rfkill", "unblock", "bluetooth"], timeout=5)
            except NetworkError:
                pass
        text = self._ctl("power", "on" if enabled else "off")
        if "succeeded" not in text.lower() and "changing" not in text.lower():
            if "blocked" in text.lower():
                raise NetworkError("Bluetooth is blocked by a hardware switch")
            raise NetworkError(_first_line(text) or "could not change Bluetooth power")

    def scan(self, seconds: int = 8) -> list[BluetoothDevice]:
        if not self.powered():
            raise NetworkError("Bluetooth is turned off")
        self.run(["bluetoothctl", "--timeout", str(seconds), "scan", "on"], timeout=seconds + 8)
        return self.devices()

    def devices(self) -> list[BluetoothDevice]:
        listing = self._ctl("devices", timeout=8)
        found: list[BluetoothDevice] = []
        for line in listing.splitlines():
            match = re.match(r"^Device\s+((?:[0-9A-F]{2}:){5}[0-9A-F]{2})\s+(.*)$", line.strip(), re.IGNORECASE)
            if not match:
                continue
            address, name = match.group(1).upper(), match.group(2).strip()
            found.append(self.info(address, fallback=name))
        found.sort(key=lambda d: (not d.connected, not d.paired, d.name.lower()))
        return found

    def info(self, address: str, fallback: str = "") -> BluetoothDevice:
        self._check_address(address)
        text = self._ctl("info", address, timeout=8)
        values = {}
        for line in text.splitlines():
            if ":" in line and not line.startswith("Device"):
                key, _, value = line.strip().partition(":")
                values[key.strip()] = value.strip()
        rssi = None
        if "RSSI" in values:
            match = re.search(r"-?\d+", values["RSSI"])
            rssi = int(match.group()) if match else None
        return BluetoothDevice(
            address=address,
            name=values.get("Alias") or values.get("Name") or fallback or address,
            paired=values.get("Paired") == "yes",
            connected=values.get("Connected") == "yes",
            icon=values.get("Icon", ""),
            rssi=rssi,
        )

    def pair(self, address: str) -> str:
        """Pair (Just Works), trust and connect, the way a settings app does."""
        self._check_address(address)
        # An agent has to be registered or pairing waits for a confirmation nobody
        # can give: NoInputNoOutput is the "Just Works" capability.
        script = f"agent NoInputNoOutput\ndefault-agent\npair {address}\ntrust {address}\nconnect {address}\n"
        _code, out, err = self.run(["bluetoothctl", "--timeout", "40"], stdin=script, timeout=50)
        text = out + err
        lowered = text.lower()
        # A pairing failure is final even if a later line in the same script
        # (trust, connect) happened to print something that sounds like success.
        if "failed to pair" in lowered:
            if "alreadyexists" in lowered or "already exists" in lowered:
                return f"Paired with {self.info(address).name}"
            if "authenticationfailed" in lowered or "authentication failed" in lowered or "authentication canceled" in lowered:
                raise NetworkError("The device refused to pair. Put it in pairing mode and try again.")
            if "page timeout" in lowered or "timed out" in lowered or "notready" in lowered:
                raise NetworkError("The device did not answer. Is it switched on and close by?")
            raise NetworkError(_bt_error(text))
        if "pairing successful" in lowered or "already exists" in lowered:
            return f"Paired with {self.info(address).name}"
        if "not available" in lowered or "no default controller" in lowered:
            raise NetworkError("Bluetooth is not available")
        raise NetworkError(_first_line(text) or "Pairing failed")

    def connect(self, address: str) -> str:
        self._check_address(address)
        text = self._ctl("connect", address, timeout=25)
        if "connection successful" in text.lower():
            return f"Connected to {self.info(address).name}"
        raise NetworkError(_bt_error(text))

    def disconnect(self, address: str) -> str:
        self._check_address(address)
        text = self._ctl("disconnect", address, timeout=15)
        if "successful" in text.lower():
            return "Disconnected"
        raise NetworkError(_bt_error(text))

    def remove(self, address: str) -> str:
        self._check_address(address)
        text = self._ctl("remove", address, timeout=10)
        if "removed" in text.lower():
            return "Device removed"
        raise NetworkError(_bt_error(text))


def _bt_error(text: str) -> str:
    lowered = text.lower()
    if "not available" in lowered:
        return "The device is out of range or switched off."
    if "page timeout" in lowered or "timed out" in lowered:
        return "The device did not answer. Is it switched on and close by?"
    if "not paired" in lowered:
        return "Pair the device first."
    return _first_line(text) or "That did not work."
