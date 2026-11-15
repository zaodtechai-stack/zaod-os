"""Exception hierarchy for the Zaod package manager.

Every error the CLI reports to a user derives from :class:`ZaodError` so that
``zaod`` can print a single, non-traceback error line and exit non-zero.
"""

from __future__ import annotations


class ZaodError(Exception):
    """Base class for every error raised by :mod:`zaod`."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UsageError(ZaodError):
    """The caller passed a bad argument or an unsupported command."""

    exit_code = 2


class ManifestError(ZaodError):
    """MANIFEST.json is missing, unparsable or violates the v1 schema."""


class SemverError(ZaodError):
    """A version string is not valid Semantic Versioning 2.0.0."""


class ChecksumError(ZaodError):
    """CHECKSUMS is malformed or does not match the archive payload."""


class SignatureError(ZaodError):
    """A signature is missing, malformed, from an unknown key or invalid."""


class ArchiveError(ZaodError):
    """A `.zaod` archive is corrupt or uses an unsupported encoding."""


class UnsafeArchiveError(ArchiveError):
    """An archive tries to escape the destination (traversal, links, bombs)."""


class CompressorError(ZaodError):
    """The configured compressor is unavailable or failed."""


class PackageError(ZaodError):
    """Package-level policy rejection (arch, OS, downgrade, collision)."""


class InstallError(ZaodError):
    """The install/remove/update transaction failed."""


class RepoError(ZaodError):
    """A repository is unknown, unreachable or serves an invalid index."""


class SandboxError(ZaodError):
    """bubblewrap is unavailable or the requested permissions are invalid."""


class PrivilegeError(ZaodError):
    """An operation needs root (or the privilege helper refused a plan)."""

    exit_code = 3
