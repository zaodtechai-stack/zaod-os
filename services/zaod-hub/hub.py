#!/usr/bin/env python3
"""zaod-hub - the local backend and account service for the Zaod apps.

Every Zaod app has to keep something: Studio keeps projects, the store keeps what
a person installed, notes and tasks will follow. None of that should need an online
service, an account on somebody else's server or a setup wizard, so the backend
lives on the machine itself:

* HTTP over a Unix socket in XDG_RUNTIME_DIR, mode 0600, so nothing is exposed on
  the network and no port has to be opened;
* accounts are local: a username and a password hashed with scrypt, never stored
  in plain text;
* sessions are random bearer tokens, stored hashed, and every row is scoped to its
  own user, so one person cannot read another person's projects;
* the data is one SQLite file in ~/.local/share/zaod/hub.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import socketserver
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "0.1.0"
MAX_BODY = 4 * 1024 * 1024
SESSION_DAYS = 30
MIN_PASSWORD = 8
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
LOGIN_WINDOW = 300
LOGIN_MAX_FAILURES = 5


def data_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path(os.environ.get("HOME", "/root")) / ".local/share")
    return Path(base) / "zaod" / "hub"


def runtime_socket() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or str(Path(os.environ.get("HOME", "/root")) / ".cache")
    return Path(base) / "zaod-hub.sock"


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """scrypt on a random salt with an interactive cost."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return salt, digest


RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_recovery_code(groups: int = 4, size: int = 4) -> str:
    """A code a person can write on paper: no 0/O/1/I confusion."""
    return "-".join(
        "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(size)) for _ in range(groups)
    )


def normalise_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class HubError(Exception):
    """A refusal the client may read, carrying the status it maps to."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Store:
    """SQLite plus the rules that keep one account out of another's data."""

    def __init__(self, db_path: Path, catalog_path: Path | None = None) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.catalog_path = catalog_path
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                salt BLOB NOT NULL,
                digest BLOB NOT NULL,
                recovery_salt BLOB,
                recovery_digest BLOB,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                document TEXT NOT NULL DEFAULT '{}',
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS installs (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                app_id TEXT NOT NULL,
                installed_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, app_id)
            );
            """
        )
        self.db.commit()
        self.failures: dict[str, list[float]] = {}

    def register(self, username: str, password: str) -> tuple[str, dict]:
        username = (username or "").strip().lower()
        if not USERNAME_RE.match(username):
            raise HubError(400, "Use 3-32 characters: a-z, 0-9, dot, dash or underscore")
        if len(password or "") < MIN_PASSWORD:
            raise HubError(400, f"The password needs at least {MIN_PASSWORD} characters")
        salt, digest = hash_password(password)
        recovery = new_recovery_code()
        recovery_salt, recovery_digest = hash_password(normalise_code(recovery))
        with self.lock:
            try:
                cursor = self.db.execute(
                    "INSERT INTO users (username, salt, digest, recovery_salt, recovery_digest, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (username, salt, digest, recovery_salt, recovery_digest, int(time.time())),
                )
                self.db.commit()
            except sqlite3.IntegrityError as exc:
                raise HubError(409, "That username is already taken on this computer") from exc
            user_id = int(cursor.lastrowid or 0)
        return self.issue_token(user_id), {
            "id": user_id,
            "username": username,
            "recovery_code": recovery,
        }

    def login(self, username: str, password: str) -> tuple[str, dict]:
        username = (username or "").strip().lower()
        self.check_rate_limit(username)
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            self.note_failure(username)
            raise HubError(401, "Wrong username or password")
        _, digest = hash_password(password or "", bytes(row["salt"]))
        if not secrets.compare_digest(digest, bytes(row["digest"])):
            self.note_failure(username)
            raise HubError(401, "Wrong username or password")
        self.failures.pop(username, None)
        return self.issue_token(int(row["id"])), {"id": int(row["id"]), "username": row["username"]}

    def issue_token(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.lock:
            self.db.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token_hash(token), user_id, now, now + SESSION_DAYS * 86400),
            )
            self.db.commit()
        return token

    def user_for_token(self, token: str | None) -> dict:
        if not token:
            raise HubError(401, "Sign in first")
        with self.lock:
            row = self.db.execute(
                "SELECT u.id, u.username, s.expires_at FROM sessions s JOIN users u ON u.id = s.user_id"
                " WHERE s.token_hash = ?",
                (token_hash(token),),
            ).fetchone()
        if row is None:
            raise HubError(401, "This session is no longer valid, sign in again")
        if int(row["expires_at"]) < int(time.time()):
            raise HubError(401, "This session expired, sign in again")
        return {"id": int(row["id"]), "username": row["username"]}

    def recover(self, username: str, code: str, new_password: str) -> tuple[str, dict]:
        """Reset a forgotten password with the code handed out at sign-up.

        The code is single use: on success it is replaced and the new one comes back
        with the fresh session, so a leaked code cannot be replayed later.
        """
        username = (username or "").strip().lower()
        self.check_rate_limit(username)
        if len(new_password or "") < MIN_PASSWORD:
            raise HubError(400, f"The new password needs at least {MIN_PASSWORD} characters")
        with self.lock:
            row = self.db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or row["recovery_digest"] is None:
            self.note_failure(username)
            raise HubError(401, "Wrong username or recovery code")
        _, digest = hash_password(normalise_code(code), bytes(row["recovery_salt"]))
        if not secrets.compare_digest(digest, bytes(row["recovery_digest"])):
            self.note_failure(username)
            raise HubError(401, "Wrong username or recovery code")
        self.failures.pop(username, None)
        salt, new_digest = hash_password(new_password)
        replacement = new_recovery_code()
        recovery_salt, recovery_digest = hash_password(normalise_code(replacement))
        with self.lock:
            self.db.execute(
                "UPDATE users SET salt = ?, digest = ?, recovery_salt = ?, recovery_digest = ? WHERE id = ?",
                (salt, new_digest, recovery_salt, recovery_digest, int(row["id"])),
            )
            # Every old session dies with the old password.
            self.db.execute("DELETE FROM sessions WHERE user_id = ?", (int(row["id"]),))
            self.db.commit()
        return self.issue_token(int(row["id"])), {
            "id": int(row["id"]),
            "username": row["username"],
            "recovery_code": replacement,
        }

    def change_password(self, user_id: int, current: str, new_password: str) -> None:
        if len(new_password or "") < MIN_PASSWORD:
            raise HubError(400, f"The new password needs at least {MIN_PASSWORD} characters")
        with self.lock:
            row = self.db.execute("SELECT salt, digest FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HubError(404, "No such account")
        _, digest = hash_password(current or "", bytes(row["salt"]))
        if not secrets.compare_digest(digest, bytes(row["digest"])):
            raise HubError(401, "The current password is wrong")
        salt, new_digest = hash_password(new_password)
        with self.lock:
            self.db.execute("UPDATE users SET salt = ?, digest = ? WHERE id = ?", (salt, new_digest, user_id))
            self.db.commit()

    def rotate_recovery_code(self, user_id: int) -> str:
        code = new_recovery_code()
        salt, digest = hash_password(normalise_code(code))
        with self.lock:
            self.db.execute(
                "UPDATE users SET recovery_salt = ?, recovery_digest = ? WHERE id = ?",
                (salt, digest, user_id),
            )
            self.db.commit()
        return code

    def export_account(self, user_id: int) -> dict:
        """Everything this account owns, so it can be moved or backed up."""
        with self.lock:
            user = self.db.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
            projects = self.db.execute(
                "SELECT id, name, document, updated_at FROM projects WHERE user_id = ?", (user_id,)
            ).fetchall()
        return {
            "format": 1,
            "username": user["username"] if user else "",
            "projects": [
                {"id": p["id"], "name": p["name"], "document": p["document"], "updated_at": int(p["updated_at"])}
                for p in projects
            ],
            "installed": self.installed(user_id),
        }

    def import_account(self, user_id: int, payload: dict) -> dict:
        """Restore an exported account; projects are added, never silently replaced."""
        if int(payload.get("format", 0)) != 1:
            raise HubError(400, "That is not a Zaod account export")
        added = 0
        with self.lock:
            for project in payload.get("projects", []):
                project_id = str(project.get("id") or secrets.token_hex(8))
                row = self.db.execute("SELECT user_id FROM projects WHERE id = ?", (project_id,)).fetchone()
                if row is not None and int(row["user_id"]) == user_id:
                    continue  # already restored into this account
                if row is not None:
                    # The same export brought into another account: keep the work and
                    # derive a stable id from owner plus source id, so importing twice
                    # is idempotent and two people never share one project row.
                    project_id = hashlib.sha256(f"{user_id}:{project_id}".encode()).hexdigest()[:16]
                    row = self.db.execute(
                        "SELECT user_id FROM projects WHERE id = ?", (project_id,)
                    ).fetchone()
                    if row is not None and int(row["user_id"]) == user_id:
                        continue
                self.db.execute(
                    "INSERT INTO projects (id, user_id, name, document, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        project_id,
                        user_id,
                        str(project.get("name") or "Restored project")[:120],
                        str(project.get("document") or "{}"),
                        int(project.get("updated_at") or time.time()),
                    ),
                )
                added += 1
            self.db.commit()
        for app_id in payload.get("installed", []):
            self.mark_installed(user_id, str(app_id), True)
        return {"projects_added": added, "installed": self.installed(user_id)}

    def logout(self, token: str) -> None:
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
            self.db.commit()

    def check_rate_limit(self, username: str) -> None:
        now = time.time()
        recent = [stamp for stamp in self.failures.get(username, []) if now - stamp < LOGIN_WINDOW]
        self.failures[username] = recent
        if len(recent) >= LOGIN_MAX_FAILURES:
            wait = int(LOGIN_WINDOW - (now - recent[0]))
            raise HubError(429, f"Too many wrong passwords, try again in {max(wait, 1)} seconds")

    def note_failure(self, username: str) -> None:
        self.failures.setdefault(username, []).append(time.time())

    def list_projects(self, user_id: int) -> list[dict]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, name, updated_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [{"id": r["id"], "name": r["name"], "updated_at": int(r["updated_at"])} for r in rows]

    def create_project(self, user_id: int, name: str, document: str) -> dict:
        name = (name or "Untitled project").strip()[:120] or "Untitled project"
        project_id = secrets.token_hex(8)
        now = int(time.time())
        with self.lock:
            self.db.execute(
                "INSERT INTO projects (id, user_id, name, document, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, user_id, name, document or "{}", now),
            )
            self.db.commit()
        return {"id": project_id, "name": name, "updated_at": now, "document": document or "{}"}

    def get_project(self, user_id: int, project_id: str) -> dict:
        with self.lock:
            row = self.db.execute(
                "SELECT id, name, document, updated_at FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
        if row is None:
            raise HubError(404, "No such project")
        return {
            "id": row["id"],
            "name": row["name"],
            "updated_at": int(row["updated_at"]),
            "document": row["document"],
        }

    def save_project(self, user_id: int, project_id: str, name: str | None, document: str | None) -> dict:
        current = self.get_project(user_id, project_id)
        with self.lock:
            self.db.execute(
                "UPDATE projects SET name = ?, document = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (
                    (name or current["name"])[:120],
                    document if document is not None else current["document"],
                    int(time.time()),
                    project_id,
                    user_id,
                ),
            )
            self.db.commit()
        return self.get_project(user_id, project_id)

    def delete_project(self, user_id: int, project_id: str) -> None:
        with self.lock:
            cursor = self.db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
            self.db.commit()
        if cursor.rowcount == 0:
            raise HubError(404, "No such project")

    def catalog(self) -> dict:
        if self.catalog_path and self.catalog_path.is_file():
            try:
                return json.loads(self.catalog_path.read_text())
            except ValueError:
                return {"packages": [], "note": "the catalog file could not be read"}
        return {"packages": [], "note": "no catalog on this system"}

    def installed(self, user_id: int) -> list[str]:
        with self.lock:
            rows = self.db.execute("SELECT app_id FROM installs WHERE user_id = ?", (user_id,)).fetchall()
        return [r["app_id"] for r in rows]

    def mark_installed(self, user_id: int, app_id: str, installed: bool = True) -> list[str]:
        if not app_id:
            raise HubError(400, "Which app?")
        with self.lock:
            if installed:
                self.db.execute(
                    "INSERT OR REPLACE INTO installs (user_id, app_id, installed_at) VALUES (?, ?, ?)",
                    (user_id, app_id, int(time.time())),
                )
            else:
                self.db.execute("DELETE FROM installs WHERE user_id = ? AND app_id = ?", (user_id, app_id))
            self.db.commit()
        return self.installed(user_id)


class Handler(BaseHTTPRequestHandler):
    """A small router: JSON in, JSON out, a bearer token on everything private."""

    server_version = f"zaod-hub/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        pass

    @property
    def store(self) -> Store:
        return self.server.store  # type: ignore[attr-defined]

    def token(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        return header[7:].strip() if header.lower().startswith("bearer ") else None

    def body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise HubError(413, "That request is too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise HubError(400, "Send JSON") from exc
        if not isinstance(payload, dict):
            raise HubError(400, "Send a JSON object")
        return payload

    def send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def dispatch(self, method: str) -> None:
        parts = [p for p in urlsplit(self.path).path.split("/") if p]
        try:
            if method == "GET" and parts == ["health"]:
                return self.send_json({"ok": True, "version": VERSION})
            if method == "POST" and parts == ["auth", "register"]:
                payload = self.body()
                token, user = self.store.register(payload.get("username", ""), payload.get("password", ""))
                return self.send_json({"token": token, "user": user}, 201)
            if method == "POST" and parts == ["auth", "login"]:
                payload = self.body()
                token, user = self.store.login(payload.get("username", ""), payload.get("password", ""))
                return self.send_json({"token": token, "user": user})
            if method == "POST" and parts == ["auth", "recover"]:
                payload = self.body()
                token, user = self.store.recover(
                    payload.get("username", ""), payload.get("code", ""), payload.get("password", "")
                )
                return self.send_json({"token": token, "user": user})
            if method == "POST" and parts == ["auth", "logout"]:
                self.store.logout(self.token() or "")
                return self.send_json({"ok": True})
            if method == "GET" and parts == ["auth", "me"]:
                return self.send_json({"user": self.store.user_for_token(self.token())})

            user = self.store.user_for_token(self.token())

            if method == "POST" and parts == ["auth", "password"]:
                payload = self.body()
                self.store.change_password(user["id"], payload.get("current", ""), payload.get("password", ""))
                return self.send_json({"ok": True})
            if method == "POST" and parts == ["auth", "recovery-code"]:
                return self.send_json({"recovery_code": self.store.rotate_recovery_code(user["id"])})
            if parts == ["auth", "export"]:
                return self.send_json({"account": self.store.export_account(user["id"])})
            if method == "POST" and parts == ["auth", "import"]:
                payload = self.body()
                return self.send_json(self.store.import_account(user["id"], payload.get("account", {})))
            if parts[:2] == ["studio", "projects"]:
                return self.studio(method, parts[2:], user)
            if parts == ["store", "catalog"]:
                return self.send_json({"catalog": self.store.catalog()})
            if parts == ["store", "installed"]:
                if method == "GET":
                    return self.send_json({"installed": self.store.installed(user["id"])})
                if method == "POST":
                    payload = self.body()
                    return self.send_json({
                        "installed": self.store.mark_installed(
                            user["id"], payload.get("app_id", ""), bool(payload.get("installed", True))
                        )
                    })
            raise HubError(404, "No such endpoint")
        except HubError as error:
            self.send_json({"error": error.message}, error.status)

    def studio(self, method: str, rest: list[str], user: dict) -> None:
        if not rest:
            if method == "GET":
                return self.send_json({"projects": self.store.list_projects(user["id"])})
            if method == "POST":
                payload = self.body()
                document = payload.get("document", {})
                if not isinstance(document, str):
                    document = json.dumps(document)
                project = self.store.create_project(user["id"], payload.get("name", ""), document)
                return self.send_json({"project": project}, 201)
            raise HubError(405, "Not allowed")
        project_id = rest[0]
        if method == "GET":
            return self.send_json({"project": self.store.get_project(user["id"], project_id)})
        if method == "PUT":
            payload = self.body()
            document = payload.get("document")
            if document is not None and not isinstance(document, str):
                document = json.dumps(document)
            project = self.store.save_project(user["id"], project_id, payload.get("name"), document)
            return self.send_json({"project": project})
        if method == "DELETE":
            self.store.delete_project(user["id"], project_id)
            return self.send_json({"ok": True})
        raise HubError(405, "Not allowed")

    def do_GET(self) -> None:
        self.dispatch("GET")

    def do_POST(self) -> None:
        self.dispatch("POST")

    def do_PUT(self) -> None:
        self.dispatch("PUT")

    def do_DELETE(self) -> None:
        self.dispatch("DELETE")


class UnixHub(ThreadingHTTPServer):
    """HTTP over a Unix socket: no port, nothing on the network."""

    address_family = socket.AF_UNIX
    daemon_threads = True

    def server_bind(self) -> None:
        if os.path.exists(self.server_address):
            os.unlink(self.server_address)
        socketserver.TCPServer.server_bind(self)
        os.chmod(self.server_address, 0o600)
        self.server_name = "zaod-hub"
        self.server_port = 0


def serve(socket_path: Path, db_path: Path, catalog_path: Path | None = None) -> UnixHub:
    server = UnixHub(str(socket_path), Handler)
    server.store = Store(db_path, catalog_path)  # type: ignore[attr-defined]
    return server


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    socket_path = Path(argv[0]) if argv else runtime_socket()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = Path(os.environ.get("ZAOD_HUB_CATALOG", "/usr/share/zaod/repo/index.json"))
    server = serve(socket_path, data_root() / "hub.db", catalog)
    print(f"zaod-hub {VERSION} listening on {socket_path}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
