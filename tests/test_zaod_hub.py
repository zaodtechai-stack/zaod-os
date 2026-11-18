"""The local hub: accounts, sessions and per-user data, driven for real.

These tests start the actual service on a Unix socket in a temporary directory and
talk to it with the same client the apps use, so the routes, the token handling and
the scrypt hashing are all exercised rather than mocked.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HUB = REPO / "services" / "zaod-hub" / "hub.py"
CLIENT = REPO / "apps" / "lib" / "zaodhub.py"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _store_module(name: str):
    """The store payload, imported with the shared library on the path."""
    for path in (REPO / "apps" / "store" / "payload", REPO / "apps" / "lib"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return _module(name, REPO / "apps" / "store" / "payload" / "main.py")


@pytest.fixture(scope="module")
def hub_modules():
    return _module("zaod_hub_service", HUB), _module("zaod_hub_client", CLIENT)


@pytest.fixture()
def hub(hub_modules, tmp_path, monkeypatch):
    monkeypatch.setenv("ZAOD_HUB_SOCKET", str(tmp_path / "run" / "zaod-hub.sock"))
    service, client = hub_modules
    socket_path = tmp_path / "run" / "zaod-hub.sock"
    socket_path.parent.mkdir()
    catalog = tmp_path / "index.json"
    catalog.write_text(json.dumps({"packages": [{"id": "org.zaod.notes", "version": "1.0.0"}]}))
    server = service.serve(socket_path, tmp_path / "hub.db", catalog)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if socket_path.exists():
            break
        time.sleep(0.02)
    yield service, client, socket_path, tmp_path
    server.shutdown()
    server.server_close()


def signed_in(client, username="ayesha", password="correct horse"):
    api = client.Hub()
    answer = api.register(username, password)
    return api, answer


def test_health_answers(hub):
    service, client, _socket, _tmp = hub
    api = client.Hub()
    answer = api.health()
    assert answer["ok"] is True
    assert answer["version"] == service.VERSION


def test_register_then_me_returns_the_same_person(hub):
    _service, client, _socket, _tmp = hub
    api, answer = signed_in(client)
    assert answer["user"]["username"] == "ayesha"
    assert answer["token"]
    assert api.me()["username"] == "ayesha"


def test_password_is_never_stored_in_plain_text(hub):
    _service, client, _socket, tmp_path = hub
    signed_in(client, "bilal", "very secret password")
    database = sqlite3.connect(str(tmp_path / "hub.db"))
    row = database.execute("SELECT username, salt, digest FROM users WHERE username = 'bilal'").fetchone()
    database.close()
    assert row is not None
    assert b"very secret password" not in bytes(row[2])
    assert len(bytes(row[1])) == 16 and len(bytes(row[2])) == 32


def test_wrong_password_is_refused_and_the_right_one_works(hub):
    _service, client, _socket, _tmp = hub
    _api, _answer = signed_in(client, "dania", "right password")
    with pytest.raises(client.HubError) as refused:
        client.Hub().login("dania", "wrong password")
    assert refused.value.status == 401
    assert "wrong" in refused.value.message.lower()
    again = client.Hub()
    assert again.login("dania", "right password")["user"]["username"] == "dania"


def test_a_short_password_and_an_ugly_username_are_refused(hub):
    _service, client, _socket, _tmp = hub
    with pytest.raises(client.HubError) as short:
        client.Hub().register("ehan", "short")
    assert short.value.status == 400
    with pytest.raises(client.HubError) as ugly:
        client.Hub().register("Ehan Ahmed!", "long enough password")
    assert ugly.value.status == 400


def test_the_same_username_cannot_be_registered_twice(hub):
    _service, client, _socket, _tmp = hub
    signed_in(client, "farah", "a good password")
    with pytest.raises(client.HubError) as taken:
        client.Hub().register("farah", "another password")
    assert taken.value.status == 409


def test_repeated_wrong_passwords_are_rate_limited(hub):
    _service, client, _socket, _tmp = hub
    signed_in(client, "gul", "the real password")
    statuses = []
    for _ in range(6):
        with pytest.raises(client.HubError) as refused:
            client.Hub().login("gul", "nope nope nope")
        statuses.append(refused.value.status)
    assert statuses[0] == 401
    assert 429 in statuses


def test_private_routes_need_a_token(hub):
    _service, client, _socket, _tmp = hub
    with pytest.raises(client.HubError) as refused:
        client.Hub().projects()
    assert refused.value.status == 401


def test_logout_invalidates_the_token(hub):
    _service, client, _socket, _tmp = hub
    api, _answer = signed_in(client, "hamza", "a good password")
    token = api.token
    api.logout()
    stale = client.Hub()
    stale.token = token
    with pytest.raises(client.HubError) as refused:
        stale.me()
    assert refused.value.status == 401


def test_projects_are_scoped_to_their_owner(hub):
    _service, client, _socket, _tmp = hub
    mine, _ = signed_in(client, "iqra", "a good password")
    theirs, _ = signed_in(client, "junaid", "a good password")
    project = mine.create_project("Launch reel", {"clips": [1, 2]})
    assert [p["id"] for p in mine.projects()] == [project["id"]]
    assert theirs.projects() == []
    with pytest.raises(client.HubError) as refused:
        theirs.project(project["id"])
    assert refused.value.status == 404
    with pytest.raises(client.HubError) as refused_delete:
        theirs.delete_project(project["id"])
    assert refused_delete.value.status == 404


def test_a_project_round_trips_through_save(hub):
    _service, client, _socket, _tmp = hub
    api, _answer = signed_in(client, "kamran", "a good password")
    project = api.create_project("Draft", {"title": "first"})
    saved = api.save_project(project["id"], {"title": "second"}, name="Final cut")
    assert saved["name"] == "Final cut"
    assert json.loads(saved["document"]) == {"title": "second"}
    api.delete_project(project["id"])
    assert api.projects() == []


def test_the_catalog_and_the_install_list_are_per_user(hub):
    _service, client, _socket, _tmp = hub
    kim, _ = signed_in(client, "kim", "a good password")
    lee, _ = signed_in(client, "lee", "a good password")
    assert [p["id"] for p in kim.catalog()["packages"]] == ["org.zaod.notes"]
    assert kim.installed() == []
    assert kim.mark_installed("org.zaod.notes") == ["org.zaod.notes"]
    assert lee.installed() == []
    assert kim.mark_installed("org.zaod.notes", False) == []


def test_the_socket_is_private_to_its_owner(hub):
    _service, _client, socket_path, _tmp = hub
    mode = stat.S_IMODE(os.stat(socket_path).st_mode)
    assert mode == 0o600, oct(mode)


def test_the_session_file_is_private(hub_modules, tmp_path, monkeypatch):
    _service, client = hub_modules
    monkeypatch.setenv("ZAOD_HUB_STATE", str(tmp_path / "state" / "hub-session.json"))
    client.save_session("nadia", "token-value")
    path = client.state_path()
    assert json.loads(path.read_text())["username"] == "nadia"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    client.clear_session()
    assert client.load_session() == {}


def test_a_hub_that_is_not_running_reports_it_clearly(hub_modules, tmp_path):
    _service, client = hub_modules
    api = client.Hub(tmp_path / "missing" / "nothing.sock")
    with pytest.raises(client.HubUnavailable):
        api.health()


def test_the_store_records_an_install_for_the_signed_in_person(hub_modules, hub, tmp_path, monkeypatch):
    """The store keeps its launch entries, and mirrors them into the hub."""
    _service, client, _socket, _tmp = hub
    store = _store_module("store_with_hub")
    monkeypatch.setenv("ZAOD_HUB_STATE", str(tmp_path / "state" / "hub-session.json"))

    api, answer = signed_in(client, "omar", "a good password")
    client.save_session("omar", answer["token"])
    store.remember_in_hub("zaod-web-youtube", True)

    fresh = client.Hub()
    fresh.token = answer["token"]
    assert fresh.installed() == ["zaod-web-youtube"]
    assert api.installed() == ["zaod-web-youtube"]


def test_the_store_survives_having_no_hub(hub_modules, tmp_path, monkeypatch):
    _service, client = hub_modules
    store = _store_module("store_without_hub")
    monkeypatch.setenv("ZAOD_HUB_SOCKET", str(tmp_path / "nowhere" / "zaod-hub.sock"))
    monkeypatch.setenv("ZAOD_HUB_STATE", str(tmp_path / "state" / "hub-session.json"))
    client.save_session("unused", "stale-token")
    store.remember_in_hub("zaod-web-youtube", True)  # must not raise


def test_registering_hands_out_a_recovery_code_once(hub):
    _service, client, _socket, _tmp = hub
    _api, answer = signed_in(client, "rana", "the first password")
    code = answer["user"]["recovery_code"]
    assert code and len(code.split("-")) == 4
    assert answer["user"]["recovery_code"] != ""
    # A second sign-up for another person never repeats a code.
    _other, other = signed_in(client, "sana", "another password")
    assert other["user"]["recovery_code"] != code


def test_a_forgotten_password_is_recovered_with_the_code_and_rotated(hub):
    _service, client, _socket, _tmp = hub
    api, answer = signed_in(client, "tariq", "the first password")
    code = answer["user"]["recovery_code"]
    old_token = api.token
    fresh = client.Hub()
    recovered = fresh.recover("tariq", code.lower().replace("-", ""), "a brand new password")
    assert recovered["user"]["username"] == "tariq"
    assert recovered["user"]["recovery_code"] not in (code, "")

    # The new password works, and the old session is dead.
    again = client.Hub()
    assert again.login("tariq", "a brand new password")["user"]["username"] == "tariq"
    stale = client.Hub()
    stale.token = old_token
    with pytest.raises(client.HubError):
        stale.me()

    # The used code cannot be replayed.
    with pytest.raises(client.HubError):
        client.Hub().recover("tariq", code, "yet another password")


def test_projects_survive_a_password_recovery(hub):
    _service, client, _socket, _tmp = hub
    api, answer = signed_in(client, "uzma", "the first password")
    project = api.create_project("Kept through recovery", {"clips": [1]})
    fresh = client.Hub()
    fresh.recover("uzma", answer["user"]["recovery_code"], "another password")
    assert [p["id"] for p in fresh.projects()] == [project["id"]]


def test_changing_the_password_requires_the_current_one(hub):
    _service, client, _socket, _tmp = hub
    api, _answer = signed_in(client, "waqar", "the first password")
    with pytest.raises(client.HubError) as refused:
        api.change_password("guess", "another password")
    assert refused.value.status == 401
    api.change_password("the first password", "the second password")
    assert client.Hub().login("waqar", "the second password")["user"]["username"] == "waqar"


def test_an_account_export_restores_into_a_new_account(hub):
    _service, client, _socket, _tmp = hub
    api, _answer = signed_in(client, "yusuf", "the first password")
    first = api.create_project("Reel one", {"clips": [1, 2]})
    api.create_project("Reel two", {"clips": [3]})
    api.mark_installed("zaod-web-youtube")
    exported = api.export_account()
    assert exported["username"] == "yusuf"
    assert len(exported["projects"]) == 2

    moved, _ = signed_in(client, "yusuf2", "the first password")
    report = moved.import_account(exported)
    assert report["projects_added"] == 2
    assert [p["name"] for p in moved.projects()] == ["Reel one", "Reel two"]
    # The work came across; the id is re-keyed because a project row belongs to one
    # account, so two people can never share a project.
    restored = next(p for p in moved.projects() if p["name"] == "Reel one")
    assert restored["id"] != first["id"]
    assert json.loads(moved.project(restored["id"])["document"]) == {"clips": [1, 2]}
    assert report["installed"] == ["zaod-web-youtube"]

    # Importing twice does not duplicate anything.
    assert moved.import_account(exported)["projects_added"] == 0


def test_an_export_from_another_format_is_refused(hub):
    _service, client, _socket, _tmp = hub
    api, _answer = signed_in(client, "zara", "the first password")
    with pytest.raises(client.HubError) as refused:
        api.import_account({"format": 99, "projects": []})
    assert refused.value.status == 400
