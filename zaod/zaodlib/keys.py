"""Ed25519 key handling and signature helpers for packages and store indexes."""

from __future__ import annotations

import base64
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from . import ed25519, util
from .errors import SignatureError

PRIVATE_HEADER = "zaod-private-key-v1"
SIGNATURE_FORMAT = 1


def key_id(public: bytes) -> str:
    """Stable 16 hex character identifier derived from the public key."""
    return util.sha256_bytes(public)[:16]


@dataclass(frozen=True)
class KeyPair:
    seed: bytes
    public: bytes

    @property
    def key_id(self) -> str:
        return key_id(self.public)

    def sign(self, data: bytes) -> bytes:
        return ed25519.sign(self.seed, data, public=self.public)

    def export_private(self) -> str:
        return f"{PRIVATE_HEADER}\n{base64.b64encode(self.seed).decode()}\n"

    def export_public(self) -> str:
        return base64.b64encode(self.public).decode() + "\n"


def generate_keypair() -> KeyPair:
    seed = secrets.token_bytes(32)
    return KeyPair(seed=seed, public=ed25519.public_key(seed))


def load_private_key(path: Path) -> KeyPair:
    text = Path(path).read_text(encoding="utf-8").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != PRIVATE_HEADER:
        raise SignatureError(f"{path}: not a Zaod private key (missing '{PRIVATE_HEADER}' header)")
    try:
        seed = base64.b64decode(lines[1], validate=True)
    except (IndexError, ValueError) as exc:
        raise SignatureError(f"{path}: private key body is not valid base64") from exc
    if len(seed) != 32:
        raise SignatureError(f"{path}: private key must decode to 32 bytes, got {len(seed)}")
    return KeyPair(seed=seed, public=ed25519.public_key(seed))


def parse_public_key(path: Path) -> bytes:
    text = Path(path).read_text(encoding="utf-8").strip()
    try:
        public = base64.b64decode(text, validate=True)
    except ValueError as exc:
        raise SignatureError(f"{path}: public key is not valid base64") from exc
    if len(public) != 32:
        raise SignatureError(f"{path}: public key must decode to 32 bytes, got {len(public)}")
    return public


def trusted_keys(directory: Path) -> dict[str, bytes]:
    """Load ``<key_id>.pub`` files from the trusted keyring directory."""
    keys: dict[str, bytes] = {}
    directory = Path(directory)
    if not directory.is_dir():
        return keys
    for path in sorted(directory.glob("*.pub")):
        public = parse_public_key(path)
        computed = key_id(public)
        if path.stem != computed:
            raise SignatureError(f"{path.name}: file name does not match key id {computed}")
        keys[computed] = public
    return keys


def trust_public_key(directory: Path, public: bytes, *, force: bool = False) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key_id(public)}.pub"
    if path.exists() and not force:
        return path
    util.atomic_write_bytes(path, base64.b64encode(public) + b"\n", mode=0o644)
    return path


def signature_document(key: KeyPair, data: bytes) -> dict:
    return {
        "format": SIGNATURE_FORMAT,
        "key_id": key.key_id,
        "sig": base64.b64encode(key.sign(data)).decode(),
        "signed": "manifest+checksums",
    }


def parse_signature(document: dict | bytes | str) -> tuple[str, bytes]:
    if isinstance(document, (bytes, str)):
        try:
            document = json.loads(document)
        except json.JSONDecodeError as exc:
            raise SignatureError(f"SIGNATURE is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise SignatureError("SIGNATURE must be a JSON object")
    if document.get("format") != SIGNATURE_FORMAT:
        raise SignatureError(f"SIGNATURE format must be {SIGNATURE_FORMAT}, got {document.get('format')!r}")
    key = document.get("key_id")
    if not isinstance(key, str) or len(key) != 16:
        raise SignatureError("SIGNATURE.key_id must be a 16 character key id")
    try:
        signature = base64.b64decode(document.get("sig", ""), validate=True)
    except ValueError as exc:
        raise SignatureError("SIGNATURE.sig is not valid base64") from exc
    if len(signature) != 64:
        raise SignatureError(f"SIGNATURE.sig must be 64 bytes, got {len(signature)}")
    return key, signature


def verify_with_keyring(keyring: dict[str, bytes], key: str, data: bytes, signature: bytes) -> None:
    public = keyring.get(key)
    if public is None:
        raise SignatureError(f"signing key {key} is not trusted on this system")
    if not ed25519.verify(public, data, signature):
        raise SignatureError(f"signature by key {key} does not match the signed data")
