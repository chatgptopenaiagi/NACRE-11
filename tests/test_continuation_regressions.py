"""Language boundary regressions found during the 2026-10-28 continuation."""
from pathlib import Path
from threading import Event
import unittest

from nacre import builtin
from nacre.contracts import NacreError, validate
from nacre.language import compile_source
from nacre.runtime import Runtime


class ContinuationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.caps = builtin.get_capabilities()

    def run_source(self, source, **options):
        plan = compile_source(source, self.caps)
        return Runtime(self.caps, builtin.invoke, Path.cwd()).run(plan, **options)

    def test_quoted_tokens_cannot_replace_grammar(self):
        sources = [
            'let x: Number = 1 "+" 2;',
            'let x: Integer "=" 42;',
            'let x: Integer = 42 ";"',
            'let x: List = [1 "," 2];',
            'let x: Number = (1 ")";',
            'let x: Record = {a:1}; emit x "." a;',
            'task x: Number <- core.sum(values=[1]) "retry" 1;',
        ]
        for source in sources:
            with self.subTest(source=source):
                with self.assertRaises(NacreError) as caught:
                    compile_source(source, self.caps)
                self.assertEqual(caught.exception.code, "SYNTAX")

    def test_delimiter_strings_are_values_and_record_keys(self):
        source = 'let x: List = ["]", ",", ")", ";", "+"]; let y: Record = {"}":42}; emit x; emit y["}"];'
        result = self.run_source(source)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["emitted"], [["]", ",", ")", ";", "+"], 42])

    def test_records_cannot_impersonate_primitive_or_container_types(self):
        for tag in ("Any", "Null", "Bool", "Integer", "Number", "String", "List", "Record"):
            with self.subTest(tag=tag):
                with self.assertRaises(NacreError) as caught:
                    validate({"$type": tag}, "Any")
                self.assertEqual(caught.exception.code, "TYPE")

    def test_malformed_domain_tags_are_structured(self):
        for tag in ([], {}, None, True, 42, "Unknown"):
            with self.subTest(tag=tag):
                with self.assertRaises(NacreError) as caught:
                    validate({"$type": tag}, "Any")
                self.assertEqual(caught.exception.code, "TYPE")

    def test_table_nullable_metadata_must_be_boolean(self):
        for nullable in ("false", 1, [], None):
            value = {"$type": "Table", "source": "isolated",
                     "schema": [{"name": "x", "type": "Integer", "nullable": nullable}],
                     "rows": [{"x": None}]}
            with self.subTest(nullable=nullable):
                with self.assertRaises(NacreError) as caught:
                    validate(value, "Table")
                self.assertEqual(caught.exception.code, "CONTRACT")

    def test_malformed_table_column_type_is_structured(self):
        value = {"$type": "Table", "source": "isolated",
                 "schema": [{"name": "x", "type": []}], "rows": []}
        with self.assertRaises(NacreError) as caught:
            validate(value, "Table")
        self.assertEqual(caught.exception.code, "CONTRACT")

    def test_artifact_digest_requires_hexadecimal(self):
        with self.assertRaises(NacreError) as caught:
            validate({"$type": "Artifact", "path": "unused", "sha256": "z" * 64}, "Artifact")
        self.assertEqual(caught.exception.code, "CONTRACT")

    def test_valid_nullable_and_domain_values_remain_portable(self):
        value = {"$type": "Table", "source": "isolated",
                 "schema": [{"name": "x", "type": "Integer", "nullable": True}],
                 "rows": [{"x": None}]}
        self.assertIs(validate(value, "Table"), value)
        artifact = {"$type": "Artifact", "path": "unused", "sha256": "a0" * 32}
        self.assertIs(validate(artifact, "Artifact"), artifact)

    def test_arithmetic_diagnostics_in_verify_and_emit(self):
        for source in ("verify\n  1 / 0 == 0;", "emit\n  1 / 0;"):
            with self.subTest(source=source):
                result = self.run_source(source)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["error"]["code"], "ARITHMETIC")
                self.assertEqual(result["error"]["line"], 2)

    def test_nested_expression_error_preserves_operand_line(self):
        result = self.run_source("let value: Number = 1 +\n  1 / 0;")
        self.assertEqual(result["error"]["code"], "ARITHMETIC")
        self.assertEqual(result["error"]["line"], 2)
        self.assertEqual(result["error"]["node"], "value")

    def test_pre_cancelled_empty_plan_does_not_emit(self):
        event = Event()
        event.set()
        result = self.run_source("verify true; emit 42;", cancel_event=event)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["emitted"], [])
        self.assertEqual(result["verifications"], [])


if __name__ == "__main__":
    unittest.main()
