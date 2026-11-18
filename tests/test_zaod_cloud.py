"""The Supabase side: sign-in, scoped rows and the local hub sync.

A fake Supabase is started on a real socket and answers the same routes the real
project does (GoTrue auth, PostgREST rows), so these tests exercise the actual
headers, the actual JSON shapes and the actual sync path. What matters most is
pinned twice: a personal row can only ever be asked for with the person's own
token, and the machine keeps working when the cloud is unreachable.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CLOUD = REPO / "services" / "zaod-cloud" / "cloud.py"
HUB = REPO / "services" / "zaod-hub" / "hub.py"
HUB_CLIENT = REPO / "apps" / "lib" / "zaodhub.py"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeSupabase(http.server.BaseHTTPRequestHandler):
    """Just enough Supabase: a password grant, an api key check and some rows."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def _json(self, payload, status=200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def _authorised(self) -> bool:
        return self.headers.get("apikey") == "anon-key"

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path)
        if not self._authorised():
            return self._json({"message": "bad api key"}, 401)
        if path.path == "/auth/v1/token":
            payload = self._body()
            if payload.get("email") != "ayesha@zaod.tech" or payload.get("password") != "right password":
                return self._json({"message": "Invalid login credentials"}, 400)
            return self._json(
                {
                    "access_token": "access-token-1",
                    "refresh_token": "refresh-token-1",
                    "user": {"id": "user-1", "email": "ayesha@zaod.tech"},
                }
            )
        if path.path == "/auth/v1/signup":
            return self._json({"user": {"id": "user-1", "email": self._body().get("email")}})
        if path.path == "/auth/v1/logout":
            return self._json({})
        if path.path.startswith("/rest/v1/"):
            table = path.path.rsplit("/", 1)[-1]
            rows = self._body()
            if not isinstance(rows, list):
                rows = [rows]
            if self.headers.get("Authorization") != "Bearer access-token-1":
                return self._json({"message": "no token"}, 401)
            store = self.server.rows  # type: ignore[attr-defined]
            for row in rows:
                key = (table, row.get("local_id") or row.get("app_id") or row.get("id") or row.get("username"))
                store[key] = row
            return self._json(rows, 201)
        return self._json({"message": "no such route"}, 404)

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path)
        if not self._authorised():
            return self._json({"message": "bad api key"}, 401)
        if path.path == "/auth/v1/user":
            if self.headers.get("Authorization") != "Bearer access-token-1":
                return self._json({"message": "no token"}, 401)
            return self._json({"id": "user-1", "email": "ayesha@zaod.tech"})
        if path.path.startswith("/rest/v1/"):
            if self.headers.get("Authorization") != "Bearer access-token-1":
                return self._json({"message": "no token"}, 401)
            table = path.path.rsplit("/", 1)[-1]
            store = self.server.rows  # type: ignore[attr-defined]
            return self._json([row for (name, _key), row in store.items() if name == table])
        return self._json({"message": "no such route"}, 404)

    def do_DELETE(self) -> None:
        self._json({})


@pytest.fixture()
def cloud(tmp_path, monkeypatch):
    module = _module("zaod_cloud", CLOUD)
    monkeypatch.setenv("ZAOD_CLOUD_STATE", str(tmp_path / "state" / "cloud-session.json"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabase)
    server.rows = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield module, url, server
    server.shutdown()
    server.server_close()


@pytest.fixture()
def local(tmp_path, monkeypatch):
    """A real local hub, so the sync has something true to move around."""
    service = _module("zaod_hub_service_cloud_test", HUB)
    client = _module("zaodhub", HUB_CLIENT)
    socket_path = tmp_path / "run" / "hub.sock"
    socket_path.parent.mkdir()
    monkeypatch.setenv("ZAOD_HUB_SOCKET", str(socket_path))
    monkeypatch.setenv("ZAOD_HUB_STATE", str(tmp_path / "state" / "hub-session.json"))
    server = service.serve(socket_path, tmp_path / "hub.db", None)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    for _ in range(100):
        if socket_path.exists():
            break
        import time

        time.sleep(0.02)
    api = client.Hub()
    api.register("ayesha", "a good password")
    yield client, api
    server.shutdown()
    server.server_close()


def test_signing_in_keeps_a_private_session(cloud, tmp_path):
    module, url, _server = cloud
    api = module.Supabase(url, "anon-key")
    answer = api.sign_in("ayesha@zaod.tech", "right password")
    assert answer["access_token"] == "access-token-1"
    saved = module.load_session()
    assert saved["email"] == "ayesha@zaod.tech"
    path = module.session_path()
    assert oct(path.stat().st_mode)[-3:] == "600"


def test_a_wrong_password_is_refused_with_the_server_message(cloud):
    module, url, _server = cloud
    with pytest.raises(module.CloudError) as refused:
        module.Supabase(url, "anon-key").sign_in("ayesha@zaod.tech", "nope")
    assert refused.value.status == 400
    assert "Invalid login credentials" in refused.value.message


def test_a_wrong_api_key_is_refused(cloud):
    module, url, _server = cloud
    with pytest.raises(module.CloudError) as refused:
        module.Supabase(url, "wrong-key").sign_in("ayesha@zaod.tech", "right password")
    assert refused.value.status == 401


def test_rows_cannot_be_read_without_the_persons_token(cloud):
    module, url, _server = cloud
    api = module.Supabase(url, "anon-key")
    with pytest.raises(module.CloudError) as refused:
        api.projects()
    assert refused.value.status == 401


def test_push_sends_the_account_scoped_to_its_own_user(cloud, local):
    module, url, server = cloud
    _client, hub = local
    hub.create_project("Launch reel", {"clips": [1, 2]})
    hub.mark_installed("zaod-web-youtube")

    api = module.Supabase(url, "anon-key")
    api.sign_in("ayesha@zaod.tech", "right password")
    report = module.push(hub, api)
    assert report == {"projects": 1, "installed": 1}

    projects = [row for (table, _), row in server.rows.items() if table == "studio_projects"]
    assert projects[0]["owner"] == "user-1"
    assert projects[0]["document"] == {"clips": [1, 2]}
    profiles = [row for (table, _), row in server.rows.items() if table == "profiles"]
    assert profiles[0] == {"id": "user-1", "username": "ayesha"}


def test_pull_brings_the_cloud_copy_into_the_hub(cloud, local, tmp_path, monkeypatch):
    module, url, _server = cloud
    _client, hub = local
    source = hub.create_project("From the other laptop", {"clips": [7]})
    hub.mark_installed("zaod-web-youtube")
    api = module.Supabase(url, "anon-key")
    api.sign_in("ayesha@zaod.tech", "right password")
    module.push(hub, api)
    hub.delete_project(source["id"])
    assert hub.projects() == []

    report = module.pull(hub, api)
    assert report["projects_added"] == 1
    restored = hub.projects()[0]
    assert restored["name"] == "From the other laptop"
    assert restored["id"] == source["id"]
    assert report["installed"] == ["zaod-web-youtube"]


def test_push_requires_a_signed_in_cloud(cloud, local):
    module, url, _server = cloud
    _client, hub = local
    with pytest.raises(module.CloudError) as refused:
        module.push(hub, module.Supabase(url, "anon-key"))
    assert refused.value.status == 401


def test_an_unreachable_cloud_does_not_break_the_local_hub(cloud, local, monkeypatch):
    module, _url, _server = cloud
    _client, hub = local
    offline = module.Supabase("http://127.0.0.1:1", "anon-key")
    offline.access_token = "a-token-that-cannot-reach-anything"
    with pytest.raises(module.CloudUnavailable):
        module.push(hub, offline)
    # The local account is untouched and still works.
    assert hub.me()["username"] == "ayesha"
    hub.create_project("Still local", {})
    assert len(hub.projects()) == 1


def test_the_published_catalogue_is_a_plain_query(cloud):
    module, url, server = cloud
    server.rows[("store_apps", "org.zaod.notes")] = {
        "app_id": "org.zaod.notes",
        "name": "Zaod Notes",
        "status": "published",
    }
    api = module.Supabase(url, "anon-key")
    api.sign_in("ayesha@zaod.tech", "right password")
    apps = api.published_apps()
    assert [app["app_id"] for app in apps] == ["org.zaod.notes"]


def test_no_configured_project_is_explained(monkeypatch, tmp_path):
    module = _module("zaod_cloud_unconfigured", CLOUD)
    for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(module, "CONFIG_PATH", tmp_path / "missing.json")
    with pytest.raises(module.CloudUnavailable, match="no Supabase project"):
        module.config()
