import unittest

from zaodlib import schema

SAMPLE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "size"],
    "properties": {
        "name": {"type": "string", "pattern": "^[a-z]+$", "minLength": 2},
        "size": {"type": "integer", "minimum": 1},
        "tags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "mode": {"enum": ["fast", "safe"]},
    },
}


class SchemaTests(unittest.TestCase):
    def test_valid_document(self):
        self.assertEqual(schema.validate({"name": "abc", "size": 3}, SAMPLE), [])

    def test_missing_required_field(self):
        errors = schema.validate({"name": "abc"}, SAMPLE)
        self.assertEqual(errors, ["manifest.size: required field is missing"])

    def test_unknown_field_rejected(self):
        errors = schema.validate({"name": "abc", "size": 1, "extra": True}, SAMPLE)
        self.assertIn("manifest.extra: unknown field is not allowed", errors)

    def test_pattern_and_length(self):
        errors = schema.validate({"name": "A", "size": 1}, SAMPLE)
        self.assertTrue(any("pattern" in error for error in errors))

    def test_integer_type_is_strict(self):
        errors = schema.validate({"name": "abc", "size": True}, SAMPLE)
        self.assertEqual(errors, ["manifest.size: expected integer, got boolean"])

    def test_enum_and_items(self):
        errors = schema.validate({"name": "abc", "size": 2, "mode": "quick"}, SAMPLE)
        self.assertTrue(any("must be one of" in error for error in errors))
        errors = schema.validate({"name": "abc", "size": 2, "tags": ["a", "a"]}, SAMPLE)
        self.assertIn("manifest.tags: items must be unique", errors)

    def test_nested_paths_are_precise(self):
        nested = {"type": "object", "properties": {"inner": {"type": "object", "required": ["value"]}}}
        errors = schema.validate({"inner": {}}, nested)
        self.assertEqual(errors, ["manifest.inner.value: required field is missing"])

    def test_any_of(self):
        rule = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
        self.assertEqual(schema.validate("text", rule), [])
        self.assertTrue(schema.validate(1.5, rule))


if __name__ == "__main__":
    unittest.main()
