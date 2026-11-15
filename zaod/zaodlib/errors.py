"""Exception hierarchy shared by the Zaod platform tools."""

from __future__ import annotations


class ZaodError(Exception):
    """Base class for every user-facing Zaod error."""

    exit_code = 1

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class UsageError(ZaodError):
    """The command line or its arguments are wrong."""

    exit_code = 2


class ManifestError(ZaodError):
    """The package manifest is malformed or fails a schema rule."""

    exit_code = 3


class SignatureError(ZaodError):
    """A signature is missing, unknown, or does not verify."""

    exit_code = 4


class HashError(ZaodError):
    """A payload file is missing, extra, or does not match CHECKSUMS."""

    exit_code = 5


class CompatibilityError(ZaodError):
    """The package targets another architecture or a newer Zaod OS."""

    exit_code = 6


class StateError(ZaodError):
    """The installed-state database, a lock, or a path is inconsistent."""

    exit_code = 7


class PackageError(ZaodError):
    """The package archive itself cannot be read or written."""

    exit_code = 8


class RepoError(ZaodError):
    """A store repository is unreachable or its index is untrusted."""

    exit_code = 9


class SandboxError(ZaodError):
    """The sandbox could not be started."""

    exit_code = 10
