"""The account window, driven as a person would: typed fields and real clicks.

The owner's requirement is that the features actually work, so the button wiring
is proved on the real dialog rather than on the functions behind it. Two layers
are covered:

* the window itself, against a stand-in service, so every button, the disabled
  state and the error text are checked;
* the service against a real HTTP server that answers like Supabase, so a wrong
  password turns into one plain sentence instead of a stack trace.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets", reason="PySide6 is not installed here")

REPO = Path(__file__).resolve().parent.parent
SHARED = REPO / "apps" / "lib"
for path in (str(SHARED), str(REPO / "apps" / "store" / "payload"), str(REPO / "apps" / "studio" / "payload")):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("ZAOD_THEME", "dark")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture()
def account_module(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAOD_CLOUD_STATE", str(tmp_path / "cloud-session.json"))
    import importlib

    import zaodaccount

    importlib.reload(zaodaccount)
    return zaodaccount


from zaodaccount import AccountError


class StubAccount:
    """Stands in for the service so the window's own behaviour can be checked."""

    def __init__(self, signed_in: bool = False, fail: str = "", error_cls=AccountError):
        self.error_cls = error_cls
        self.signed_in = signed_in
        self.fail = fail
        self.calls: list[tuple] = []
        self.email = ""

    def state(self):
        return {"signed_in": self.signed_in, "email": self.email, "username": "", "local": True}

    def _maybe_fail(self):
        if self.fail:
            raise self.error_cls(self.fail)

    def sign_in(self, email, password):
        self.calls.append(("sign_in", email, password))
        self._maybe_fail()
        self.signed_in, self.email = True, email
        return {"email": email}

    def sign_up(self, email, password):
        self.calls.append(("sign_up", email, password))
        self._maybe_fail()
        self.signed_in, self.email = True, email
        return {"email": email}

    def sign_out(self):
        self.calls.append(("sign_out",))
        self.signed_in, self.email = False, ""

    def sync(self):
        self.calls.append(("sync",))
        self._maybe_fail()
        return {
            "sent": {"projects": 2, "installed": 1},
            "came_back": {"projects_added": 1, "installed": []},
        }


def dialog_for(module, account):
    dialog = module.build_dialog(None, account)
    return dialog


def click(dialog, name):
    from PySide6.QtWidgets import QPushButton

    button = dialog.findChild(QPushButton, name)
    assert button is not None, f"{name} is missing from the account window"
    button.click()


def field(dialog, name):
    from PySide6.QtWidgets import QLineEdit

    widget = dialog.findChild(QLineEdit, name)
    assert widget is not None
    return widget


def test_signing_in_types_a_password_and_lands_signed_in(qt_app, account_module):
    stub = StubAccount()
    dialog = dialog_for(account_module, stub)
    field(dialog, "accountEmail").setText("ayesha@zaod.tech")
    field(dialog, "accountPassword").setText("a good password")
    click(dialog, "accountSignIn")

    assert stub.calls == [("sign_in", "ayesha@zaod.tech", "a good password")]
    assert stub.signed_in is True
    assert field(dialog, "accountPassword").text() == ""
    assert field(dialog, "accountEmail").isEnabled() is False
    from PySide6.QtWidgets import QLabel

    who = dialog.findChild(QLabel, "accountStatus")
    assert "Signed in" in who.text()


def test_a_wrong_password_is_one_plain_sentence(qt_app, account_module):
    stub = StubAccount(
        fail="That email and password do not match an account.",
        error_cls=account_module.AccountError,
    )
    dialog = dialog_for(account_module, stub)
    field(dialog, "accountEmail").setText("ayesha@zaod.tech")
    field(dialog, "accountPassword").setText("wrong password")
    click(dialog, "accountSignIn")

    from PySide6.QtWidgets import QLabel

    status = dialog.findChild(QLabel, "accountStatus")
    assert status.text() == "That email and password do not match an account."
    assert stub.signed_in is False
    assert field(dialog, "accountPassword").isEnabled() is True


def test_sync_reports_what_moved(qt_app, account_module):
    stub = StubAccount(signed_in=True)
    dialog = dialog_for(account_module, stub)
    click(dialog, "accountSync")

    from PySide6.QtWidgets import QLabel

    text = dialog.findChild(QLabel, "accountStatus").text()
    assert stub.calls == [("sync",)]
    assert "Backed up 2 project(s)" in text
    assert "brought back 1 project(s)" in text


def test_sync_stays_off_until_someone_is_signed_in(qt_app, account_module):
    from PySide6.QtWidgets import QPushButton

    stub = StubAccount(signed_in=False)
    dialog = dialog_for(account_module, stub)
    assert dialog.findChild(QPushButton, "accountSync").isEnabled() is False
    assert dialog.findChild(QPushButton, "accountSignOut").isEnabled() is False


def test_signing_out_puts_the_form_back(qt_app, account_module):
    stub = StubAccount(signed_in=True)
    stub.email = "ayesha@zaod.tech"
    dialog = dialog_for(account_module, stub)
    click(dialog, "accountSignOut")

    assert stub.calls == [("sign_out",)]
    assert field(dialog, "accountEmail").isEnabled() is True
    assert field(dialog, "accountPassword").isEnabled() is True


def test_the_store_opens_the_same_window(qt_app, account_module, monkeypatch):
    import importlib.util

    from PySide6.QtWidgets import QPushButton

    spec = importlib.util.spec_from_file_location(
        "store_account_wiring", REPO / "apps" / "store" / "payload" / "main.py"
    )
    store = importlib.util.module_from_spec(spec)
    sys.modules["store_account_wiring"] = store
    spec.loader.exec_module(store)

    opened = {"count": 0}

    class FakeDialog:
        def exec(self):
            opened["count"] += 1
            return 0

    monkeypatch.setattr(account_module, "build_dialog", lambda *a, **k: FakeDialog())
    window = store.build_window()
    button = window.findChild(QPushButton, "accountButton")
    assert button is not None, "the store lost its Account button"
    button.click()
    assert opened["count"] == 1


def test_the_studio_opens_the_same_window(qt_app, account_module, monkeypatch):
    import importlib.util

    from PySide6.QtWidgets import QPushButton

    spec = importlib.util.spec_from_file_location(
        "studio_account_wiring", REPO / "apps" / "studio" / "payload" / "main.py"
    )
    studio = importlib.util.module_from_spec(spec)
    sys.modules["studio_account_wiring"] = studio
    spec.loader.exec_module(studio)

    opened = {"count": 0}

    class FakeDialog:
        def exec(self):
            opened["count"] += 1
            return 0

    monkeypatch.setattr(account_module, "build_dialog", lambda *a, **k: FakeDialog())
    window = studio.build_window()
    button = window.findChild(QPushButton, "accountButton")
    assert button is not None, "Studio lost its Account button"
    button.click()
    assert opened["count"] == 1


class FakeCloud(BaseHTTPRequestHandler):
    """Answers /auth/v1 the way Supabase does, including its error shapes."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/token?grant_type=password"):
            if body.get("password") != "a good password":
                self.answer(400, {"error": "invalid_grant", "error_description": "Invalid login credentials"})
                return
            self.answer(200, self.session(body["email"]))
            return
        if self.path.endswith("/signup"):
            self.answer(200, self.session(body["email"]))
            return
        if self.path.endswith("/logout"):
            self.answer(204, None)
            return
        self.answer(404, {"message": "no route"})

    @staticmethod
    def session(email: str) -> dict:
        return {
            "access_token": "an-access-token",
            "refresh_token": "a-refresh-token",
            "expires_in": 3600,
            "user": {"id": "user-1", "email": email, "user_metadata": {"username": "ayesha"}},
        }

    def answer(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode())


@pytest.fixture()
def fake_cloud_url():
    server = HTTPServer(("127.0.0.1", 0), FakeCloud)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_service_turns_a_refused_password_into_a_sentence(account_module, fake_cloud_url, tmp_path):
    account = account_module.Account(api=account_module.Supabase(fake_cloud_url, "anon-key"))
    with pytest.raises(account_module.AccountError) as error:
        account.sign_in("ayesha@zaod.tech", "the wrong password")
    assert str(error.value) == "That email and password do not match an account."

    answer = account.sign_in("ayesha@zaod.tech", "a good password")
    assert answer["email"] == "ayesha@zaod.tech"
    assert account.state()["signed_in"] is True
    assert (tmp_path / "cloud-session.json").exists()
    assert (tmp_path / "cloud-session.json").stat().st_mode & 0o777 == 0o600


def test_a_short_password_is_refused_before_any_network_call(account_module):
    account = account_module.Account(api=object())
    with pytest.raises(account_module.AccountError, match="at least 8"):
        account.sign_in("ayesha@zaod.tech", "short")
    with pytest.raises(account_module.AccountError, match="email"):
        account.sign_in("not-an-email", "a good password")


def test_no_zaod_document_is_installed_where_the_strip_deletes_it():
    """The wallpaper credits vanished from the shipped image while verify went green.

    ``strip_inside`` empties /usr/share/doc to save space, and the credits were
    installed there before it ran, so the image shipped the wallpapers without
    their attribution. Any Zaod file we rely on has to live outside that path.
    """
    build = (REPO / "scripts" / "build-rootfs.sh").read_text()
    offending = [
        line.strip()
        for line in build.splitlines()
        if "/usr/share/doc/zaod" in line and not line.strip().startswith("#")
    ]
    assert offending == [], f"these would be stripped from the image: {offending}"
    assert "/usr/share/zaod/licenses/wallpaper-credits.md" in build
    verify = (REPO / "scripts" / "verify-rootfs-desktop.sh").read_text()
    assert "have /usr/share/zaod/licenses/wallpaper-credits.md" in verify
