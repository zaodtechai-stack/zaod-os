"""Zaod OS package manager library.

The public surface is deliberately small:

``manifest``
    Load and validate ``MANIFEST.json`` into a frozen :class:`manifest.Manifest`.
``archive``
    Build and unpack ``.zaod`` packages safely.
``signature``
    Ed25519 signing and verification against the local trust store.
``installer``
    Transactional install, update and removal below an injectable root.
``db``
    The installed-package database.
``cli``
    The ``zaod`` command.

Everything here is standard library only (plus the ``zstd`` CLI when it is
available) so the package manager works on a machine where Debian packages have
been removed, which is the whole point of Zaod OS.
"""

from __future__ import annotations

__all__ = [
    "FORMAT_VERSION",
    "__version__",
]

__version__ = "1.0.0"

#: On-disk ``.zaod`` format version implemented by this tree.
FORMAT_VERSION = 1
