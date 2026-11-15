"""Package signing and the local trust store.

Signed document (v1)::

    b"zaod-format-v1\\n" + MANIFEST.json bytes + b"\\n" + CHECKSUMS bytes

MANIFEST.json is deliberately excluded from CHECKSUMS, so binding the two
documents here is what stops an attacker from swapping in a different manifest
for a signed payload.

Trusted public keys live in ``<root>/etc/zaod/keys/<key_id>.pub`` as 64
lowercase hex characters (32 raw bytes). ``key_id`` is
``sha256(public_key).hexdigest()[:16]``, the same identifier the crypto module
and the store index use.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .crypto import ed25519
from .errors import SignatureError

SIGN_DOMAIN = b"zaod-format-v1\n"
TRUST_DIR = "etc/zaod/keys"
SIGNATURE_HEX_LENGTH = 128


def signing_document(manifest_bytes: bytes, checksums_bytes: bytes) -> bytes:
    """The exact byte string covered by a package signature."""
    return SIGN_DOMAIN + manifest_bytes + b"\n" + checksums_bytes


@dataclass(frozen=True)
class Key:
    """A public key loaded from the trust store."""

    key_id: str
    public_key: bytes
    source: str

    @property
    def fingerprint(self) -> str:
        """Grouped key id, for humans: ``a1b2:c3d4:e5f6:0718``."""
        return ":".join(self.key_id[index : index + 4] for index in range(0, 16, 4))


def load_public_key(path: str | os.PathLike[str]) -> Key:
    source = Path(path)
    raw = source.read_text(encoding="ascii").strip()
    try:
        public_key = bytes.fromhex(raw)
    except ValueError as exc:
        raise SignatureError(f"{source}: public key is not hex") from exc
    if len(public_key) != ed25519.PUBLIC_KEY_SIZE:
        raise SignatureError(f"{source}: public key must be 32 bytes, got {len(public_key)}")
    return Key(key_id=ed25519.key_id(public_key), public_key=public_key, source=str(source))


class TrustStore:
    """Public keys this machine accepts packages from."""

    def __init__(self, root: str | os.PathLike[str] = "/") -> None:
        self.root = Path(root)
        self.directory = self.root / TRUST_DIR

    def paths(self) -> list:
        if not self.directory.is_dir():
            return []
        return sorted(self.directory.glob("*.pub"))

    def keys(self) -> list:
        return [load_public_key(path) for path in self.paths()]

    def get(self, key_id: str) -> Key | None:
        if not key_id or len(key_id) != 16:
            raise SignatureError(f"key id must be 16 hex characters, got {key_id!r}")
        candidate = self.directory / f"{key_id}.pub"
        if candidate.is_file():
            key = load_public_key(candidate)
            if key.key_id != key_id:
                raise SignatureError(f"{candidate} is named {key_id} but holds key {key.key_id}")
            return key
        for key in self.keys():
            if key.key_id == key_id:
                return key
        return None

    def require(self, key_id: str) -> Key:
        """Return the key or raise, naming the keys that are trusted."""
        key = self.get(key_id)
        if key is None:
            known = ", ".join(item.key_id for item in self.keys()) or "none"
            raise SignatureError(f"unknown key {key_id} (trusted keys: {known})")
        return key

    def add(self, public_key: bytes) -> Key:
        if len(public_key) != ed25519.PUBLIC_KEY_SIZE:
            raise SignatureError(f"public key must be 32 bytes, got {len(public_key)}")
        key_id = ed25519.key_id(public_key)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{key_id}.pub"
        target.write_text(public_key.hex() + "\n", encoding="ascii")
        os.chmod(target, 0o644)
        return Key(key_id=key_id, public_key=public_key, source=str(target))

    def remove(self, key_id: str) -> None:
        target = self.directory / f"{key_id}.pub"
        if not target.is_file():
            raise SignatureError(f"no trusted key {key_id}")
        target.unlink()


def generate_keypair(seed: bytes | None = None) -> tuple:
    """Return ``(private_key, public_key)``; the private key is a 32-byte seed."""
    material = seed if seed is not None else os.urandom(ed25519.SEED_SIZE)
    if len(material) != ed25519.SEED_SIZE:
        raise SignatureError("seed must be 32 bytes")
    return material, ed25519.public_key_from_seed(material)


def sign_package(manifest_bytes: bytes, checksums_bytes: bytes, private_key: bytes) -> bytes:
    """Produce the 64-byte signature for a package."""
    return ed25519.sign(private_key, signing_document(manifest_bytes, checksums_bytes))


def verify_package_signature(
    *,
    manifest_bytes: bytes,
    checksums_bytes: bytes,
    signature: bytes,
    public_key: bytes,
) -> None:
    """Raise :class:`SignatureError` unless the signature is valid."""
    message = signing_document(manifest_bytes, checksums_bytes)
    try:
        ed25519.verify(public_key, message, signature)
    except Exception as exc:
        raise SignatureError(f"signature does not verify: {exc}") from exc


def verify_with_store(
    *,
    manifest_bytes: bytes,
    checksums_bytes: bytes,
    signature: bytes,
    trust: TrustStore,
    key_id: str | None = None,
) -> Key:
    """Verify a signature against the trust store and return the signing key.

    With ``key_id`` only that key is tried. Without it every trusted key is
    tried, which is how a package that carries no key hint is accepted: the set
    of trusted keys is small and key ids are not secret.
    """
    if signature is None:
        raise SignatureError("package is not signed")
    candidates = [trust.require(key_id)] if key_id else trust.keys()
    if not candidates:
        raise SignatureError(f"no trusted keys in {trust.directory}")
    for key in candidates:
        try:
            verify_package_signature(
                manifest_bytes=manifest_bytes,
                checksums_bytes=checksums_bytes,
                signature=signature,
                public_key=key.public_key,
            )
            return key
        except SignatureError:
            continue
    known = ", ".join(key.key_id for key in candidates)
    raise SignatureError(f"no trusted key verifies this package (tried: {known})")


def key_id_for(public_key: bytes) -> str:
    return ed25519.key_id(public_key)
