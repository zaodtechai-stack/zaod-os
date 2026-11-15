"""A small, dependency-free JSON Schema validator.

Zaod validates manifests without third-party modules, so this module
implements the subset of JSON Schema the manifest and store index need and
reports every problem with a precise JSON pointer style location.
"""

from __future__ import annotations

import re

TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _type_name(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def validate(instance, schema: dict, location: str = "manifest") -> list[str]:
    """Return a list of human-readable validation errors (empty means valid)."""
    errors: list[str] = []

    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(TYPE_CHECKS[name](instance) for name in allowed if name in TYPE_CHECKS):
            errors.append(f"{location}: expected {' or '.join(allowed)}, got {_type_name(instance)}")
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{location}: must be {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        allowed = ", ".join(repr(item) for item in schema["enum"])
        errors.append(f"{location}: must be one of {allowed}, got {instance!r}")

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, instance):
            errors.append(f"{location}: {instance!r} does not match required pattern {pattern}")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            errors.append(f"{location}: must be at least {min_length} characters")
        max_length = schema.get("maxLength")
        if max_length is not None and len(instance) > max_length:
            errors.append(f"{location}: must be at most {max_length} characters")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{location}: must be >= {minimum}, got {instance}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            errors.append(f"{location}: must be <= {maximum}, got {instance}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{location}.{key}: required field is missing")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{location}.{key}"))
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    errors.append(f"{location}.{key}: unknown field is not allowed")
                elif isinstance(extra, dict):
                    errors.extend(validate(value, extra, f"{location}.{key}"))

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                errors.extend(validate(value, items, f"{location}[{index}]"))
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            errors.append(f"{location}: must contain at least {min_items} items")
        max_items = schema.get("maxItems")
        if max_items is not None and len(instance) > max_items:
            errors.append(f"{location}: must contain at most {max_items} items")
        if schema.get("uniqueItems") and len({repr(item) for item in instance}) != len(instance):
            errors.append(f"{location}: items must be unique")

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if not branches:
            continue
        matches = sum(1 for branch in branches if not validate(instance, branch, location))
        if keyword == "anyOf" and matches == 0:
            errors.append(f"{location}: does not match any allowed form")
        elif keyword == "oneOf" and matches != 1:
            errors.append(f"{location}: must match exactly one allowed form, matched {matches}")

    for branch in schema.get("allOf", []):
        errors.extend(validate(instance, branch, location))

    negated = schema.get("not")
    if isinstance(negated, dict) and not validate(instance, negated, location):
        errors.append(f"{location}: value matches a forbidden form")

    return errors
