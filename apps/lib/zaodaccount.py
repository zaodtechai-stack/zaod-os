"""The Zaod account: one sign-in that backs this computer up and follows you.

The local hub is still the truth on this machine. A Zaod account is the hosted
half: sign in with an email and password, and the projects and install list are
copied up so a second computer, or a reinstall, gets them back.

Two rules shape everything here:

* the password never goes into a command line, a log line or a file we write;
* a dead network is not an error the person has to understand - the windows stay
  usable and the dialog says what is happening in one plain sentence.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # in the image the modules sit side by side in /usr/lib/zaod
    import zaod_cloud as cloud_module
except ImportError:  # in the repo, before the build stages it
    import importlib.util

    _path = Path(__file__).resolve().parents[2] / "services" / "zaod-cloud" / "cloud.py"
    _spec = importlib.util.spec_from_file_location("zaod_cloud", _path)
    cloud_module = importlib.util.module_from_spec(_spec)
    sys.modules["zaod_cloud"] = cloud_module
    _spec.loader.exec_module(cloud_module)

CloudError = cloud_module.CloudError
CloudUnavailable = cloud_module.CloudUnavailable
Supabase = cloud_module.Supabase


class AccountError(RuntimeError):
    """Something the person can read and act on."""


class Account:
    """Sign-in, sign-out and sync, shared by the store and Studio."""

    def __init__(self, api=None, hub=None):
        self.api = api
        self._hub = hub

    # -- the cloud client -------------------------------------------------
    def client(self):
        if self.api is None:
            try:
                self.api = Supabase()
            except CloudUnavailable as error:
                raise AccountError(str(error)) from error
        return self.api

    def hub(self):
        if self._hub is None:
            import zaodhub

            self._hub = zaodhub.signed_in_hub()
        return self._hub

    # -- what the dialog needs to know ------------------------------------
    def state(self) -> dict:
        """Who is signed in, without touching the network."""
        session = cloud_module.load_session()
        return {
            "signed_in": bool(session.get("refresh_token") or session.get("access_token")),
            "email": session.get("email", ""),
            "username": (session.get("user") or {}).get("user_metadata", {}).get("username", ""),
            "local": bool(self.hub().token),
        }

    # -- the actions -------------------------------------------------------
    def sign_up(self, email: str, password: str) -> dict:
        email, password = self._checked(email, password, need_password=True)
        api = self.client()
        try:
            answer = api.sign_up(email, password)
        except CloudError as error:
            raise AccountError(self._friendly(error)) from error
        except CloudUnavailable as error:
            raise AccountError("No connection. Your work stays on this computer.") from error
        if not api.access_token:
            raise AccountError("That account needs its email confirmed before it can sign in.")
        return {"email": email, "answer": answer}

    def sign_in(self, email: str, password: str) -> dict:
        email, password = self._checked(email, password, need_password=True)
        api = self.client()
        try:
            api.sign_in(email, password)
        except CloudError as error:
            raise AccountError(self._friendly(error)) from error
        except CloudUnavailable as error:
            raise AccountError("No connection. Your work stays on this computer.") from error
        return {"email": email}

    def sign_out(self) -> None:
        try:
            self.client().sign_out()
        except (CloudError, CloudUnavailable):
            # A session that cannot reach the server is still cleared locally,
            # which is what the person asked for.
            cloud_module.clear_session()

    def sync(self) -> dict:
        """Send this computer's work up, then bring the rest back."""
        api = self.client()
        if not api.resume():
            raise AccountError("Sign in first, then your work can be backed up.")
        hub = self.hub()
        if not hub.token:
            raise AccountError("Set up this computer's account first, then sync.")
        try:
            sent = cloud_module.push(hub, api)
            came_back = cloud_module.pull(hub, api)
        except CloudUnavailable as error:
            raise AccountError("No connection. Nothing was lost; try again later.") from error
        except CloudError as error:
            raise AccountError(self._friendly(error)) from error
        return {"sent": sent, "came_back": came_back}

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _checked(email: str, password: str, need_password: bool) -> tuple[str, str]:
        email = (email or "").strip()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise AccountError("Type the email for this account.")
        if need_password and len(password or "") < 8:
            raise AccountError("The password needs at least 8 characters.")
        return email, password or ""

    @staticmethod
    def _friendly(error) -> str:
        text = str(getattr(error, "message", "") or error)
        low = text.lower()
        if "invalid login" in low or "invalid_grant" in low or "invalid credentials" in low:
            return "That email and password do not match an account."
        if "already registered" in low or "already been registered" in low or "user already" in low:
            return "An account with that email already exists. Sign in instead."
        if "rate" in low and "limit" in low:
            return "Too many tries. Wait a minute and try again."
        return text or "The account server refused that."


def build_dialog(parent=None, account: Account | None = None):
    """The one account window, used by the store and by Studio."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
    )

    service = account or Account()

    dialog = QDialog(parent)
    dialog.setObjectName("accountDialog")
    dialog.setWindowTitle("Zaod account")
    dialog.setMinimumWidth(460)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(12)

    title = QLabel("Zaod account")
    title.setObjectName("title")
    layout.addWidget(title)

    who = QLabel()
    who.setObjectName("subtitle")
    who.setWordWrap(True)
    layout.addWidget(who)

    email = QLineEdit()
    email.setPlaceholderText("Email")
    email.setObjectName("accountEmail")
    email.setClearButtonEnabled(True)
    layout.addWidget(email)

    password = QLineEdit()
    password.setPlaceholderText("Password (8 characters or more)")
    password.setObjectName("accountPassword")
    password.setEchoMode(QLineEdit.EchoMode.Password)
    layout.addWidget(password)

    status = QLabel("")
    status.setObjectName("accountStatus")
    status.setWordWrap(True)
    layout.addWidget(status)

    row = QHBoxLayout()
    row.setSpacing(8)
    sign_in = QPushButton("Sign in")
    sign_in.setObjectName("accountSignIn")
    sign_in.setCursor(Qt.CursorShape.PointingHandCursor)
    create = QPushButton("Create account")
    create.setObjectName("accountCreate")
    create.setCursor(Qt.CursorShape.PointingHandCursor)
    sync = QPushButton("Sync now")
    sync.setObjectName("accountSync")
    sync.setCursor(Qt.CursorShape.PointingHandCursor)
    out = QPushButton("Sign out")
    out.setObjectName("accountSignOut")
    out.setCursor(Qt.CursorShape.PointingHandCursor)
    close = QPushButton("Close")
    close.setObjectName("accountClose")
    close.setCursor(Qt.CursorShape.PointingHandCursor)
    for button in (sign_in, create, sync, out):
        row.addWidget(button)
    row.addStretch(1)
    row.addWidget(close)
    layout.addLayout(row)

    def show_state() -> None:
        state = service.state()
        if state["signed_in"]:
            who.setText(
                f"Signed in as {state['email']}. Your projects and installed apps are backed up."
            )
        else:
            who.setText(
                "Sign in to back up this computer's projects and installed apps, "
                "and to get them back after a reinstall."
            )
        sync.setEnabled(state["signed_in"] and state["local"])
        out.setEnabled(state["signed_in"])
        email.setEnabled(not state["signed_in"])
        password.setEnabled(not state["signed_in"])
        sign_in.setEnabled(not state["signed_in"])
        create.setEnabled(not state["signed_in"])

    def mark(text: str, error: bool) -> None:
        """Keep the object name stable; the style hook is a property."""
        status.setText(text)
        status.setProperty("error", error)
        status.style().unpolish(status)
        status.style().polish(status)

    def run(action, done) -> None:
        mark("Working…", False)
        try:
            done(action())
        except AccountError as error:
            mark(str(error), True)

    def after_sign_in(result: dict) -> None:
        email.setText(result["email"])
        password.clear()
        status.setText("Signed in. Sync when you are ready.")
        show_state()

    def do_sync(report=None) -> None:
        report = report or service.sync()
        sent = report["sent"]
        back = report["came_back"]
        mark(
            f"Backed up {sent.get('projects', 0)} project(s) and "
            f"{sent.get('installed', 0)} install(s); brought back "
            f"{back.get('projects_added', 0)} project(s).",
            False,
        )

    sign_in.clicked.connect(lambda: run(lambda: service.sign_in(email.text(), password.text()), after_sign_in))
    create.clicked.connect(lambda: run(lambda: service.sign_up(email.text(), password.text()), after_sign_in))
    sync.clicked.connect(lambda: run(service.sync, do_sync))
    out.clicked.connect(
        lambda: run(service.sign_out, lambda _r: (mark("Signed out.", False), show_state()))
    )
    close.clicked.connect(dialog.accept)

    show_state()
    dialog.show_state = show_state  # test hook: refresh after an outside change
    dialog.service = service  # test hook: drive the same service the buttons use
    return dialog
