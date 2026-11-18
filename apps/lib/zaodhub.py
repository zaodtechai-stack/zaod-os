"""The client every Zaod app uses to talk to the local hub.

The hub is an HTTP service on a Unix socket, so this file has no dependencies
beyond the standard library and no port to guess. If the hub is not running the
caller gets :class:`HubUnavailable` and can fall back to working offline, which is
what the Studio does: local files first, the hub for accounts and sharing.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
from pathlib import Path

TIMEOUT = 10


class HubError(RuntimeError):
    """What the hub answered instead of doing the work."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class HubUnavailable(RuntimeError):
    """The hub is not running, or not reachable, so nothing was sent."""


def socket_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or str(Path(os.environ.get("HOME", "/root")) / ".cache")
    return Path(os.environ.get("ZAOD_HUB_SOCKET") or (Path(base) / "zaod-hub.sock"))


def state_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ.get("HOME", "/root")) / ".local/state")
    return Path(os.environ.get("ZAOD_HUB_STATE") or (Path(base) / "zaod" / "hub-session.json"))


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, timeout: float = TIMEOUT) -> None:
        super().__init__("localhost", timeout=timeout)
        self.unix_path = str(path)

    def connect(self) -> None:
        raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        raw.settimeout(self.timeout)
        try:
            raw.connect(self.unix_path)
        except OSError as exc:
            raw.close()
            raise HubUnavailable(f"cannot reach the Zaod hub at {self.unix_path}: {exc}") from exc
        self.sock = raw


class Hub:
    """One small client: call a route, get JSON, or a readable error."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else socket_path()
        self.token: str | None = None

    def request(self, method: str, route: str, payload: dict | None = None) -> dict:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        connection = _UnixConnection(self.path)
        try:
            connection.request(method, route, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
        except HubUnavailable:
            raise
        except OSError as exc:
            raise HubUnavailable(str(exc)) from exc
        finally:
            connection.close()
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            data = {}
        if response.status >= 400:
            raise HubError(response.status, str(data.get("error") or f"the hub refused that ({response.status})"))
        return data

    # -- accounts ----------------------------------------------------------
    def health(self) -> dict:
        return self.request("GET", "/health")

    def register(self, username: str, password: str) -> dict:
        answer = self.request("POST", "/auth/register", {"username": username, "password": password})
        self.token = answer.get("token")
        return answer

    def login(self, username: str, password: str) -> dict:
        answer = self.request("POST", "/auth/login", {"username": username, "password": password})
        self.token = answer.get("token")
        return answer

    def recover(self, username: str, code: str, password: str) -> dict:
        """Come back from a forgotten password with the recovery code."""
        answer = self.request("POST", "/auth/recover", {"username": username, "code": code, "password": password})
        self.token = answer.get("token")
        return answer

    def change_password(self, current: str, password: str) -> None:
        self.request("POST", "/auth/password", {"current": current, "password": password})

    def new_recovery_code(self) -> str:
        return self.request("POST", "/auth/recovery-code")["recovery_code"]

    def export_account(self) -> dict:
        return self.request("GET", "/auth/export")["account"]

    def import_account(self, account: dict) -> dict:
        return self.request("POST", "/auth/import", {"account": account})

    def me(self) -> dict:
        return self.request("GET", "/auth/me")["user"]

    def logout(self) -> None:
        try:
            self.request("POST", "/auth/logout")
        finally:
            self.token = None

    # -- studio ------------------------------------------------------------
    def projects(self) -> list[dict]:
        return self.request("GET", "/studio/projects")["projects"]

    def create_project(self, name: str, document: dict | str | None = None) -> dict:
        return self.request("POST", "/studio/projects", {"name": name, "document": document or {}})["project"]

    def project(self, project_id: str) -> dict:
        return self.request("GET", f"/studio/projects/{project_id}")["project"]

    def save_project(self, project_id: str, document: dict | str | None = None, name: str | None = None) -> dict:
        payload: dict = {}
        if document is not None:
            payload["document"] = document
        if name:
            payload["name"] = name
        return self.request("PUT", f"/studio/projects/{project_id}", payload)["project"]

    def delete_project(self, project_id: str) -> None:
        self.request("DELETE", f"/studio/projects/{project_id}")

    # -- store -------------------------------------------------------------
    def catalog(self) -> dict:
        return self.request("GET", "/store/catalog")["catalog"]

    def installed(self) -> list[str]:
        return self.request("GET", "/store/installed")["installed"]

    def mark_installed(self, app_id: str, installed: bool = True) -> list[str]:
        return self.request("POST", "/store/installed", {"app_id": app_id, "installed": installed})["installed"]


# -- the remembered session -------------------------------------------------

def load_session() -> dict:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_session(username: str, token: str) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"username": username, "token": token}))
    path.chmod(0o600)


def clear_session() -> None:
    try:
        state_path().unlink()
    except OSError:
        pass


def signed_in_hub() -> Hub:
    """A hub client holding the remembered token, or an empty one when nobody is in."""
    hub = Hub()
    hub.token = load_session().get("token") or None
    return hub
