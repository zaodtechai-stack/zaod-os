#!/usr/bin/env python3
"""zaod-cloud - the hosted half of Zaod accounts, talking to Supabase.

The desktop keeps working with no network at all: ``zaod-hub`` owns the data on the
machine. This module is what backs that up and what makes an account usable on a
second computer. It speaks Supabase's own REST API (GoTrue for sign-in, PostgREST
for rows), so nothing here needs a Supabase client library or a Node toolchain.

Configuration, read from the environment or /etc/zaod/cloud.json:

    SUPABASE_URL        https://<project>.supabase.co
    SUPABASE_ANON_KEY   the publishable/anon key (never the service key)

Only the publishable key belongs on a desktop: every personal row is protected by
the row level security in schema.sql, so the key cannot reach another person's data.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 30
CONFIG_PATH = Path(os.environ.get("ZAOD_CLOUD_CONFIG", "/etc/zaod/cloud.json"))


class CloudError(RuntimeError):
    """The server answered, and said no."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class CloudUnavailable(RuntimeError):
    """No usable connection, so nothing was sent; the local hub stays the truth."""


def config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")
    if (not url or not key) and CONFIG_PATH.is_file():
        try:
            data = json.loads(CONFIG_PATH.read_text())
        except ValueError as exc:
            raise CloudUnavailable("the cloud configuration file is not valid JSON") from exc
        url = url or data.get("url")
        key = key or data.get("anon_key")
    if not url or not key:
        raise CloudUnavailable("no Supabase project is configured for this computer")
    return str(url).rstrip("/"), str(key)


def session_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ.get("HOME", "/root")) / ".local/state")
    return Path(os.environ.get("ZAOD_CLOUD_STATE") or (Path(base) / "zaod" / "cloud-session.json"))


def load_session() -> dict:
    path = session_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_session(data: dict) -> Path:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


def clear_session() -> None:
    try:
        session_path().unlink()
    except OSError:
        pass


class Supabase:
    """Sign in, then read and write only what this person is allowed to."""

    def __init__(self, url: str | None = None, key: str | None = None, access_token: str | None = None) -> None:
        self.url, self.key = (url, key) if url and key else config()
        self.access_token = access_token
        self.refresh_token: str | None = None
        self.user: dict = {}

    # -- transport ---------------------------------------------------------
    def _request(self, method: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        bearer = token or self.access_token
        headers = {"apikey": self.key, "Content-Type": "application/json", "Accept": "application/json"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        request = urllib.request.Request(f"{self.url}{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # the URL is this system's own project
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                detail = json.loads(raw)
            except ValueError:
                detail = {"message": raw.decode("utf-8", "replace")}
            message = str(detail.get("msg") or detail.get("message") or detail.get("error_description") or "")
            raise CloudError(error.code, message or f"the server refused that ({error.code})") from error
        except (urllib.error.URLError, OSError) as exc:
            raise CloudUnavailable(f"cannot reach the Zaod cloud: {exc}") from exc

    # -- accounts ----------------------------------------------------------
    def sign_up(self, email: str, password: str, username: str = "") -> dict:
        payload = {"email": email, "password": password}
        if username:
            payload["data"] = {"username": username.lower()}
        _status, answer = self._request("POST", "/auth/v1/signup", payload)
        self._remember(answer or {})
        return answer or {}

    def sign_in(self, email: str, password: str) -> dict:
        _status, answer = self._request(
            "POST",
            "/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
        )
        self._remember(answer or {})
        return answer or {}

    def refresh(self) -> dict:
        if not self.refresh_token:
            raise CloudError(401, "There is no cloud session to refresh, sign in again")
        _status, answer = self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": self.refresh_token},
        )
        self._remember(answer or {})
        return answer or {}

    def _remember(self, answer: dict) -> None:
        token = answer.get("access_token")
        if token:
            self.access_token = str(token)
        if answer.get("refresh_token"):
            self.refresh_token = str(answer["refresh_token"])
        if isinstance(answer.get("user"), dict):
            self.user = answer["user"]
        if self.access_token:
            save_session(
                {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "email": self.user.get("email", ""),
                    "user_id": self.user.get("id", ""),
                }
            )

    def resume(self) -> bool:
        """Pick the remembered session back up, refreshing it when it has expired."""
        saved = load_session()
        if not saved.get("access_token"):
            return False
        self.access_token = saved.get("access_token")
        self.refresh_token = saved.get("refresh_token")
        self.user = {"email": saved.get("email", ""), "id": saved.get("user_id", "")}
        try:
            self._request("GET", "/auth/v1/user")
            return True
        except CloudError:
            try:
                self.refresh()
                return True
            except (CloudError, CloudUnavailable):
                return False

    def sign_out(self) -> None:
        if self.access_token:
            try:
                self._request("POST", "/auth/v1/logout")
            except (CloudError, CloudUnavailable):
                pass
        self.access_token = None
        clear_session()

    def me(self) -> dict:
        _status, answer = self._request("GET", "/auth/v1/user")
        self.user = answer or {}
        return self.user

    # -- rows --------------------------------------------------------------
    def select(self, table: str, params: dict | None = None) -> list:
        query = urllib.parse.urlencode(params or {"select": "*"})
        _status, answer = self._request("GET", f"/rest/v1/{table}?{query}")
        return list(answer or [])

    def upsert(self, table: str, rows: list, on_conflict: str) -> list:
        _status, answer = self._request(
            "POST",
            f"/rest/v1/{table}?on_conflict={urllib.parse.quote(on_conflict)}",
            rows,
        )
        return list(answer or [])

    def delete(self, table: str, params: dict) -> None:
        query = urllib.parse.urlencode(params)
        self._request("DELETE", f"/rest/v1/{table}?{query}")

    # -- the app-facing shape ----------------------------------------------
    def projects(self) -> list:
        return self.select("studio_projects", {"select": "local_id,name,document,updated_at", "order": "updated_at.desc"})

    def installs(self) -> list:
        return self.select("install_records", {"select": "app_id"})

    def published_apps(self) -> list:
        return self.select("store_apps", {"select": "*", "status": "eq.published", "order": "downloads.desc"})


def push(hub, cloud: Supabase) -> dict:
    """Upload this computer's account: profile, projects and installs.

    Last write wins on the project's ``updated_at``, so syncing twice, or from two
    computers, never loses the newer edit.
    """
    if not cloud.access_token:
        raise CloudError(401, "Sign in to the cloud first")
    account = hub.export_account()
    user_id = cloud.user.get("id") or cloud.me().get("id")
    if not user_id:
        raise CloudError(401, "The cloud session has no user id")
    cloud.upsert(
        "profiles",
        [{"id": user_id, "username": account["username"]}],
        on_conflict="id",
    )
    rows = [
        {
            "owner": user_id,
            "local_id": project["id"],
            "name": project["name"],
            "document": json.loads(project["document"]) if project["document"] else {},
        }
        for project in account["projects"]
    ]
    if rows:
        cloud.upsert("studio_projects", rows, on_conflict="owner,local_id")
    installs = [{"owner": user_id, "app_id": app_id} for app_id in account["installed"]]
    if installs:
        cloud.upsert("install_records", installs, on_conflict="owner,app_id")
    return {"projects": len(rows), "installed": len(installs)}


def pull(hub, cloud: Supabase) -> dict:
    """Bring the cloud copy down into this computer's hub, adding what is missing."""
    if not cloud.access_token:
        raise CloudError(401, "Sign in to the cloud first")
    projects = [
        {"id": row["local_id"], "name": row.get("name"), "document": json.dumps(row.get("document") or {})}
        for row in cloud.projects()
    ]
    installed = [row["app_id"] for row in cloud.installs()]
    return hub.import_account({"format": 1, "projects": projects, "installed": installed})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zaod cloud account: sign in and sync")
    parser.add_argument("action", choices=["sign-in", "sign-out", "status", "push", "pull", "sync"])
    parser.add_argument("--email", help="the account email")
    parser.add_argument("--password", help="read from ZAOD_CLOUD_PASSWORD when omitted")
    args = parser.parse_args(argv)

    sys.path.insert(0, "/usr/lib/zaod")
    try:
        import zaodhub
    except ImportError:
        print("zaod-cloud: the local hub client is not installed", file=sys.stderr)
        return 1

    hub = zaodhub.signed_in_hub()
    cloud = Supabase()
    try:
        if args.action == "sign-in":
            password = args.password or os.environ.get("ZAOD_CLOUD_PASSWORD", "")
            if not args.email or not password:
                print("zaod-cloud: --email and a password are needed", file=sys.stderr)
                return 2
            cloud.sign_in(args.email, password)
            print("signed in")
            return 0
        if args.action == "sign-out":
            cloud.sign_out()
            print("signed out")
            return 0
        if not cloud.resume():
            print("zaod-cloud: not signed in", file=sys.stderr)
            return 1
        if args.action == "status":
            print(f"signed in as {cloud.user.get('email', 'unknown')}")
            return 0
        if args.action in ("push", "sync"):
            print(f"sent {push(hub, cloud)}")
        if args.action in ("pull", "sync"):
            print(f"brought back {pull(hub, cloud)}")
        return 0
    except (CloudError, CloudUnavailable) as error:
        print(f"zaod-cloud: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
