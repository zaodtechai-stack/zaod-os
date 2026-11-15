"""Strict Semantic Versioning 2.0.0 parsing and comparison.

The `.zaod` v1 format uses SemVer exclusively for package and OS versions
(see ``docs/zaod-format-v1.md``). A version that is not valid SemVer is a
manifest error, because ordering must be total and unambiguous for the
downgrade check in ``zaod install``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import SemverError

__all__ = ["MAX_VERSION", "Version", "compare", "parse", "satisfies"]

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

#: Guard against absurd numbers such as ``9`` repeated 5000 times in a manifest.
MAX_VERSION = 10**9


@dataclass(frozen=True, order=False)
class Version:
    """A parsed SemVer 2.0.0 version.

    ``build`` metadata is parsed and preserved but ignored for ordering, as
    required by the specification (section 10).
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = field(default_factory=tuple)
    build: tuple[str, ...] = field(default_factory=tuple)
    raw: str = ""

    def __str__(self) -> str:
        return self.raw

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    @property
    def release_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def precedence_key(self) -> tuple:
        """Sort key implementing SemVer 11.3/11.4 precedence."""
        if not self.prerelease:
            # A version without a prerelease outranks every prerelease of the
            # same major.minor.patch. ``(1,)`` sorts after ``(0, ...)``.
            prerelease_key: tuple = (1,)
        else:
            parts: list[tuple] = [(0,)]
            for identifier in self.prerelease:
                if identifier.isdigit():
                    parts.append((0, int(identifier), ""))
                else:
                    parts.append((1, 0, identifier))
            prerelease_key = (0, tuple(parts))
        return (self.major, self.minor, self.patch, prerelease_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.precedence_key() == other.precedence_key()

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.precedence_key() < other.precedence_key()

    def __le__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.precedence_key() <= other.precedence_key()

    def __gt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.precedence_key() > other.precedence_key()

    def __ge__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.precedence_key() >= other.precedence_key()

    def __hash__(self) -> int:
        return hash(self.precedence_key())


def parse(text: str) -> Version:
    """Parse ``text`` as SemVer 2.0.0, raising :class:`SemverError` if invalid."""
    if not isinstance(text, str):
        raise SemverError(f"version must be a string, got {type(text).__name__}")
    if len(text) > 128:
        raise SemverError(f"version string is too long ({len(text)} characters)")
    match = _SEMVER_RE.match(text)
    if match is None:
        raise SemverError(
            f"invalid semantic version {text!r}: expected MAJOR.MINOR.PATCH "
            "with optional -prerelease and +build (e.g. 1.4.0, 0.7.0-beta.2)"
        )
    for component in ("major", "minor", "patch"):
        if int(match.group(component)) > MAX_VERSION:
            raise SemverError(f"invalid semantic version {text!r}: {component} is too large")
    prerelease = tuple((match.group("prerelease") or "").split(".")) if match.group("prerelease") else ()
    build = tuple((match.group("build") or "").split(".")) if match.group("build") else ()
    return Version(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=prerelease,
        build=build,
        raw=text,
    )


def compare(left: str, right: str) -> int:
    """Return -1, 0 or 1 comparing two version strings by SemVer precedence."""
    lhs, rhs = parse(left), parse(right)
    if lhs < rhs:
        return -1
    return 0 if lhs == rhs else 1


def satisfies(version: str, constraint: str) -> bool:
    """Evaluate a small, explicit constraint language.

    Supported forms (clauses are ANDed when separated by ``,``):

    ``*``            any version
    ``>=1.2.0``      inclusive lower bound  (also ``>``, ``<=``, ``<``)
    ``=1.2.3``       exact precedence match (build metadata ignored)
    ``1.2.3``        shorthand for ``=1.2.3``
    ``^1.2.0``       compatible: >=1.2.0 and <2.0.0
    ``~1.2.0``       patch level: >=1.2.0 and <1.3.0

    Prerelease versions only satisfy a constraint whose operand is itself a
    prerelease (npm-style behaviour). This keeps a ``>=1.0.0`` requirement from
    silently accepting ``2.0.0-beta.1``, which is what makes the downgrade and
    runtime-dependency checks predictable.
    """
    target = parse(version)
    if not constraint or constraint.strip() == "*":
        return True
    for raw_clause in constraint.split(","):
        clause = raw_clause.strip()
        if not clause or clause == "*":
            continue
        operator = "="
        for candidate in (">=", "<=", "==", "^", "~", ">", "<", "="):
            if clause.startswith(candidate):
                operator = candidate
                break
        operand_text = clause[len(operator) :].strip()
        if not operand_text:
            raise SemverError(f"invalid constraint {constraint!r}: missing version after {operator!r}")
        operand = parse(operand_text)
        if target.is_prerelease and not operand.is_prerelease:
            return False
        if not _clause_holds(target, operator, operand):
            return False
    return True


def _clause_holds(target: Version, operator: str, operand: Version) -> bool:
    if operator in ("=", "=="):
        return target == operand
    if operator == ">":
        return target > operand
    if operator == ">=":
        return target >= operand
    if operator == "<":
        return target < operand
    if operator == "<=":
        return target <= operand
    if operator == "^":
        upper = Version(operand.major + 1, 0, 0, raw="")
        if operand.major == 0:
            if operand.minor == 0:
                upper = Version(0, 0, operand.patch + 1, raw="")
            else:
                upper = Version(0, operand.minor + 1, 0, raw="")
        return operand <= target < upper
    if operator == "~":
        upper = Version(operand.major, operand.minor + 1, 0, raw="")
        return operand <= target < upper
    raise SemverError(f"unsupported operator {operator!r}")
