"""Compiler bounds and journal failure behavior, independent of live engines."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nacre.contracts import Capability, NacreError
from nacre.language import compile_source
from nacre.runtime import Runtime, _atomic_json


class RuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.caps = {"test.write": Capability("test.write", {"value": "Number"}, "Number", effect="write", resource="owned-test")}

    def invoke(self, name, args, context):
        self.calls.append((name, args.copy()))
        return args["value"]

    def assert_compile_error(self, source, code):
        with self.assertRaises(NacreError) as caught:
            compile_source(source, self.caps)
        self.assertEqual(caught.exception.code, code)

    def test_nonfinite_literal_rejected_before_effects(self):
        self.assert_compile_error('task effect: Number <- test.write(value=1); let invalid: Number = 1e309;', "VALUE")
        self.assertEqual(self.calls, [])

    def test_oversized_integer_literal_is_structured(self):
        self.assert_compile_error('let invalid: Integer = ' + '9' * 5000 + ';', "LIMIT")

    def test_reserved_binding_rejected(self):
        self.assert_compile_error('let true: Integer = 1;', "NAME")

    def test_reserved_alias_rejected(self):
        self.assert_compile_error('use not = "test";', "NAME")

    def test_left_associative_tree_is_bounded(self):
        self.assert_compile_error('let invalid: Integer = ' + ' + '.join(['1'] * 1200) + ';', "LIMIT")

    def test_changed_contract_rejected_before_effects(self):
        plan = compile_source('task effect: Number <- test.write(value=7);', self.caps)
        changed = {"test.write": replace(self.caps["test.write"], resource="different-resource")}
        with self.assertRaises(NacreError) as caught:
            Runtime(changed, self.invoke, Path.cwd()).run(plan)
        self.assertEqual(caught.exception.code, "CONTRACT")
        self.assertEqual(self.calls, [])

    def test_unwritable_checkpoint_rejected_before_effects(self):
        plan = compile_source('task effect: Number <- test.write(value=7);', self.caps)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            blocker = root / "existing-file"
            blocker.write_text("owned test obstruction", encoding="utf-8")
            with self.assertRaises(NacreError) as caught:
                Runtime(self.caps, self.invoke, root).run(plan, checkpoint=blocker / "journal.json")
        self.assertEqual(caught.exception.code, "CHECKPOINT")
        self.assertEqual(self.calls, [])

    def test_final_checkpoint_failure_preserves_effect_result(self):
        plan = compile_source('task effect: Number <- test.write(value=7); emit effect;', self.caps)
        def disk_failure(path, value):
            if value["status"] == "passed":
                raise NacreError("CHECKPOINT", "simulated unavailable storage")
            return _atomic_json(path, value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("nacre.runtime._atomic_json", side_effect=disk_failure):
                result = Runtime(self.caps, self.invoke, root).run(plan, checkpoint=root / "journal.json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["checkpoint_error"]["code"], "CHECKPOINT")
        self.assertEqual(result["results"]["effect"], 7)
        self.assertEqual(len(self.calls), 1)

    def test_midrun_checkpoint_failure_stops_dependent_effect(self):
        plan = compile_source('task first: Number <- test.write(value=7); task second: Number <- test.write(value=first);', self.caps)
        def disk_failure(path, value):
            if value["status"] == "running" and value["nodes"]:
                raise NacreError("CHECKPOINT", "simulated storage failure after first effect")
            return _atomic_json(path, value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("nacre.runtime._atomic_json", side_effect=disk_failure):
                result = Runtime(self.caps, self.invoke, root, workers=1).run(plan, checkpoint=root / "journal.json")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "CHECKPOINT")
        self.assertEqual(result["results"], {"first": 7})
        self.assertEqual(result["pending"], ["second"])
        self.assertEqual(len(self.calls), 1)


if __name__ == "__main__":
    unittest.main()
