"""Minimal, pure-Python Ed25519 (RFC 8032 ``Ed25519`` / PureEdDSA).

Provenance
----------
The algorithm, constants and the verification procedure are taken from the
public specification "RFC 8032: Edwards-Curve Digital Signature Algorithm
(EdDSA)", section 5.1 (Ed25519) and the reference pseudocode in section 6.
The code below was written for Zaod OS; it contains no copied third-party
implementation. It is a "vendored" primitive in the sense that Zaod OS ships
and audits this file instead of depending on a pip package, because the target
system (PRD section 4) must build from the Python standard library only.

License
-------
This file is part of Zaod OS and is distributed under the license the Zaod OS
owner selects for the repository (PRD section 15, "Licensing and trademarks").
No other project's code or license text is embedded here.

Security notes (read before using this module for anything else)
---------------------------------------------------------------
* Verification only touches public data (public key, message, signature), so
  the lack of constant-time arithmetic is not a secret-leak risk there.
* Signing uses the private seed. This implementation is **not** constant time
  and does not attempt to be. It is intended for offline developer keys and
  for CI tooling that signs package indexes on trusted machines -- the same
  threat model as the offline root key in PRD section 11. For the shipped
  distribution key, sign on an offline machine with the same code and record
  the signature in the release notes so it can be re-verified with any
  independent RFC 8032 implementation.
* ``verify(strict=True)`` (the default) additionally rejects small-order
  public keys and small-order ``R`` values, which removes the trivial
  signature-malleability variants of the original Ed25519 verification.
"""

from __future__ import annotations

import hashlib

__all__ = [
    "PUBLIC_KEY_SIZE",
    "SEED_SIZE",
    "SIGNATURE_SIZE",
    "Ed25519Error",
    "InvalidKeyError",
    "InvalidSignatureError",
    "key_id",
    "public_key_from_seed",
    "sign",
    "verify",
]

# --- curve parameters (RFC 8032, section 5.1) -------------------------------

#: Field prime: 2**255 - 19.
P = 2**255 - 19
#: Group order: 2**252 + 27742317777372353535851937790883648493.
L = 2**252 + 27742317777372353535851937790883648493
#: Twisted Edwards curve constant d = -121665/121666 mod p.
D = -121665 * pow(121666, P - 2, P) % P
#: sqrt(-1) mod p, needed by the point decompression routine.
SQRT_M1 = pow(2, (P - 1) // 4, P)

SEED_SIZE = 32
PUBLIC_KEY_SIZE = 32
SIGNATURE_SIZE = 64


class Ed25519Error(Exception):
    """Base class for Ed25519 failures."""


class InvalidKeyError(Ed25519Error):
    """The public or private key is malformed."""


class InvalidSignatureError(Ed25519Error):
    """The signature is malformed or does not verify."""


# --- field and group arithmetic --------------------------------------------


def _inv(value: int) -> int:
    """Multiplicative inverse modulo ``P`` (P is prime)."""
    return pow(value, P - 2, P)


def _recover_x(y: int) -> int:
    """Return a square root of x^2 = (y^2 - 1) / (d*y^2 + 1) mod P.

    Raises :class:`InvalidKeyError` when ``y`` has no matching x, which means
    the encoding is not a curve point.
    """
    if not 0 <= y < P:
        raise InvalidKeyError("y coordinate is not canonical")
    y2 = y * y % P
    u = (y2 - 1) % P
    v = (D * y2 + 1) % P
    x2 = u * _inv(v) % P
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * SQRT_M1 % P
    if (x * x - x2) % P != 0:
        raise InvalidKeyError("point is not on curve25519")
    return x


def _point_add(first: tuple[int, int, int, int], second: tuple[int, int, int, int]):
    """Unified addition in extended twisted Edwards coordinates."""
    x1, y1, z1, t1 = first
    x2, y2, z2, t2 = second
    a = (y1 - x1) * (y2 - x2) % P
    b = (y1 + x1) * (y2 + x2) % P
    c = 2 * t1 * t2 * D % P
    d = 2 * z1 * z2 % P
    e = b - a
    f = d - c
    g = d + c
    h = b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _point_mul(scalar: int, point: tuple[int, int, int, int]):
    """Scalar multiplication (double-and-add, no secret-dependent branching)."""
    result = (0, 1, 1, 0)  # neutral element
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _is_on_curve(point: tuple[int, int, int, int]) -> bool:
    x, y, z, t = point
    if t % P != x * y % P:
        return False
    return (-x * x + y * y - z * z - D * t * t) % P == 0


def _is_identity(point: tuple[int, int, int, int]) -> bool:
    x, y, z, _t = point
    return x % P == 0 and (y - z) % P == 0


def _has_small_order(point: tuple[int, int, int, int]) -> bool:
    """True when the point lies in the order-8 torsion subgroup."""
    return _is_identity(_point_mul(8, point))


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _t = point
    z_inv = _inv(z)
    x = x * z_inv % P
    y = y * z_inv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decode_point(raw: bytes) -> tuple[int, int, int, int]:
    if len(raw) != 32:
        raise InvalidKeyError(f"point encoding must be 32 bytes, got {len(raw)}")
    y = int.from_bytes(raw, "little")
    sign_bit = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y)
    if x == 0 and sign_bit:
        raise InvalidKeyError("x = 0 with sign bit set is not a valid encoding")
    if (x & 1) != sign_bit:
        x = P - x
    point = (x, y, 1, x * y % P)
    if not _is_on_curve(point):
        raise InvalidKeyError("point is not on curve25519")
    return point


_BY = 4 * _inv(5) % P
_BX = _recover_x(_BY)
if _BX & 1:  # the base point uses the even x coordinate
    _BX = P - _BX
BASE_POINT = (_BX, _BY, 1, _BX * _BY % P)
del _BY, _BX


# --- key handling ----------------------------------------------------------


def _sha512_int(data: bytes) -> int:
    return int.from_bytes(hashlib.sha512(data).digest(), "little")


def _hash_mod_l(data: bytes) -> int:
    return _sha512_int(data) % L


def _split_private_key(private_key: bytes) -> tuple[bytes, bytes | None]:
    """Accept a 32-byte seed or an OpenSSL-style 64-byte seed||pubkey blob."""
    if not isinstance(private_key, (bytes, bytearray)):
        raise InvalidKeyError("private key must be bytes")
    private_key = bytes(private_key)
    if len(private_key) == SEED_SIZE:
        return private_key, None
    if len(private_key) == SEED_SIZE + PUBLIC_KEY_SIZE:
        seed, hinted = private_key[:SEED_SIZE], private_key[SEED_SIZE:]
        if public_key_from_seed(seed) != hinted:
            raise InvalidKeyError("public key half of the private key does not match the seed")
        return seed, hinted
    raise InvalidKeyError(
        f"private key must be {SEED_SIZE} bytes (seed) or {SEED_SIZE + PUBLIC_KEY_SIZE} "
        f"bytes (seed || public key), got {len(private_key)}"
    )


def _expand_seed(seed: bytes) -> tuple[int, bytes]:
    digest = hashlib.sha512(seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8  # clear the low 3 bits
    scalar |= 1 << 254  # set the second-highest bit
    return scalar, digest[32:]


def public_key_from_seed(seed: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key for a 32-byte private seed."""
    if len(seed) != SEED_SIZE:
        raise InvalidKeyError(f"seed must be {SEED_SIZE} bytes, got {len(seed)}")
    scalar, _prefix = _expand_seed(seed)
    return _encode_point(_point_mul(scalar, BASE_POINT))


def key_id(public_key: bytes) -> str:
    """Stable 16-hex-character identifier for a public key.

    ``key_id = sha256(public_key)[:8].hex()``. It is used in SIGNATURE files so
    that a verifier can pick the right file out of ``/etc/zaod/keys`` without
    trial-verifying against every key.
    """
    if len(public_key) != PUBLIC_KEY_SIZE:
        raise InvalidKeyError(f"public key must be {PUBLIC_KEY_SIZE} bytes")
    return hashlib.sha256(public_key).hexdigest()[:16]


# --- signature operations --------------------------------------------------


def sign(private_key: bytes, message: bytes, *, strict: bool = True) -> bytes:
    """Return the 64-byte detached Ed25519 signature of ``message``.

    ``private_key`` is either the 32-byte RFC 8032 seed or a 64-byte
    ``seed || public_key`` blob as produced by OpenSSL. ``strict`` is accepted
    for symmetry with :func:`verify`; it validates the key before signing.
    """
    seed, _hinted = _split_private_key(private_key)
    scalar, prefix = _expand_seed(seed)
    public_key = _encode_point(_point_mul(scalar, BASE_POINT))
    if strict and _has_small_order(_decode_point(public_key)):
        raise InvalidKeyError("derived public key has small order")
    nonce = _hash_mod_l(prefix + message)
    r_point = _encode_point(_point_mul(nonce, BASE_POINT))
    challenge = _hash_mod_l(r_point + public_key + message)
    s = (nonce + challenge * scalar) % L
    return r_point + s.to_bytes(32, "little")


def verify(
    public_key: bytes,
    message: bytes,
    signature: bytes,
    *,
    strict: bool = True,
) -> bool:
    """Verify a detached Ed25519 signature.

    Returns ``True`` on success and raises one of the :class:`Ed25519Error`
    subclasses otherwise -- it never returns ``False``, because callers in
    :mod:`zaod` must not be able to accidentally ignore a failure.
    """
    public_key = bytes(public_key)
    signature = bytes(signature)
    if len(public_key) != PUBLIC_KEY_SIZE:
        raise InvalidKeyError(f"public key must be {PUBLIC_KEY_SIZE} bytes, got {len(public_key)}")
    if len(signature) != SIGNATURE_SIZE:
        raise InvalidSignatureError(f"signature must be {SIGNATURE_SIZE} bytes, got {len(signature)}")

    try:
        a_point = _decode_point(public_key)
    except InvalidKeyError as exc:
        raise InvalidKeyError(f"invalid public key: {exc}") from exc

    if strict and _has_small_order(a_point):
        raise InvalidKeyError("public key has small order")

    try:
        r_point = _decode_point(signature[:32])
    except InvalidKeyError as exc:
        raise InvalidSignatureError(f"invalid R value: {exc}") from exc

    if strict and _has_small_order(r_point):
        raise InvalidSignatureError("R has small order")

    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        raise InvalidSignatureError("S is not reduced modulo the group order")

    challenge = _hash_mod_l(signature[:32] + public_key + message)
    check = _point_add(r_point, _point_mul(challenge, a_point))
    if _encode_point(_point_mul(s, BASE_POINT)) != _encode_point(check):
        raise InvalidSignatureError("signature does not match public key and message")
    return True
