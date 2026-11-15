"""Ed25519 signatures (RFC 8032) in pure Python standard library code.

The Zaod package manager must work on a system with no third-party Python
modules available, so it vendors this compact implementation instead of
depending on ``cryptography`` or ``pynacl``. The implementation follows
RFC 8032 section 5 and is validated against the RFC test vectors in
``zaod/tests/test_ed25519.py``.
"""

from __future__ import annotations

import hashlib

P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)

IDENTITY = (0, 1, 1, 0)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _recover_x(y: int, sign: int):
    if y >= P:
        return None
    x2 = (y * y - 1) * _inv(D * y * y + 1) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * I % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


def _recover_y(y: int, sign: int):
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % P)


G_Y = 4 * _inv(5) % P
G_X = _recover_x(G_Y, 0)
G = (G_X, G_Y, 1, G_X * G_Y % P)


def _point_add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    A = (y1 - x1) * (y2 - x2) % P
    B = (y1 + x1) * (y2 + x2) % P
    C = 2 * t1 * t2 * D % P
    Dd = 2 * z1 * z2 % P
    E, F, Gg, H = B - A, Dd - C, Dd + C, B + A
    return (E * F % P, Gg * H % P, F * Gg % P, E * H % P)


def _point_double(point):
    x1, y1, z1, _ = point
    A = x1 * x1 % P
    B = y1 * y1 % P
    C = 2 * z1 * z1 % P
    H = A + B
    E = H - (x1 + y1) * (x1 + y1) % P
    Gg = A - B
    F = C + Gg
    return (E * F % P, Gg * H % P, F * Gg % P, E * H % P)


def _scalar_mult(point, scalar: int):
    result = IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_double(addend)
        scalar >>= 1
    return result


def _encode_point(point) -> bytes:
    x, y, z, _ = point
    zinv = _inv(z)
    x = x * zinv % P
    y = y * zinv % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decode_point(data: bytes):
    if len(data) != 32:
        return None
    value = int.from_bytes(data, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    return _recover_y(y, sign)


def _point_equal(a, b) -> bool:
    return _encode_point(a) == _encode_point(b)


def _expand_seed(seed: bytes):
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    digest = _sha512(seed)
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 255) - 8  # clear bit 255 and the low three bits (RFC 8032 clamp)
    scalar |= 1 << 254
    return scalar, digest[32:]


def public_key(seed: bytes) -> bytes:
    """Return the 32-byte public key for a 32-byte private seed."""
    scalar, _ = _expand_seed(seed)
    return _encode_point(_scalar_mult(G, scalar))


def sign(seed: bytes, message: bytes, public: bytes | None = None) -> bytes:
    """Return a 64-byte detached signature over ``message``."""
    scalar, prefix = _expand_seed(seed)
    if public is None:
        public = _encode_point(_scalar_mult(G, scalar))
    if len(public) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    r = int.from_bytes(_sha512(prefix + message), "little") % L
    R = _encode_point(_scalar_mult(G, r))
    h = int.from_bytes(_sha512(R + public + message), "little") % L
    S = (r + h * scalar) % L
    return R + int.to_bytes(S, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Return True only for a valid signature by ``public`` over ``message``."""
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a = _decode_point(public)
    if point_a is None:
        return False
    point_r = _decode_point(signature[:32])
    if point_r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    h = int.from_bytes(_sha512(signature[:32] + public + message), "little") % L
    return _point_equal(_scalar_mult(G, s), _point_add(point_r, _scalar_mult(point_a, h)))
