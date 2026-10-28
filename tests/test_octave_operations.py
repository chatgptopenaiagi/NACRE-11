"""Fixed-worker validation and optional real GNU Octave calculations."""
import importlib.util
import unittest
from unittest.mock import Mock

from nacre.contracts import NacreError
from nacre.octave_operations import run, _product


class BoundaryTests(unittest.TestCase):
    def test_reference_product_rejects_truncating_inner_dimensions(self):
        for a, b in [([[1, 2]], [[3]]), ([[1]], [[2], [3]]), ([[1], [2, 3]], [[4]])]:
            with self.subTest(a=a, b=b), self.assertRaisesRegex(NacreError, "dimensions"):
                _product(a, b)

    def test_worker_receipt_and_version_are_required(self):
        import json
        from pathlib import Path
        class Worker:
            runtime_version = "11.3.0"
            def __init__(self, receipt, version="11.3.0"):
                self.receipt, self.version = receipt, version
            def run_script(self, worker, args, **kwargs):
                Path(args[1]).write_text(json.dumps({"schema_version": 1, "operation": "polynomial", "octave_version": self.version,
                                                    "result": {"rows": 1, "columns": 1, "values": [2]}}))
                return self.receipt
        for receipt in ({}, {"returncode": 0}, {"exit_code": 0}, {"exit_code": False, "timed_out": False},
                        {"exit_code": 1, "timed_out": False}, {"exit_code": 0, "timed_out": True}):
            with self.subTest(receipt=receipt), self.assertRaisesRegex(NacreError, "exit status"):
                run(Worker(receipt), "polynomial", {"coefficients": [2], "points": [0]})
        with self.assertRaisesRegex(NacreError, "runtime version"):
            run(Worker({"exit_code": 0, "timed_out": False}, "different"), "polynomial", {"coefficients": [2], "points": [0]})

    def test_qr_rejects_wrong_economy_shapes_before_reconstruction(self):
        import json
        from pathlib import Path
        class Worker:
            runtime_version = "11.3.0"
            def run_script(self, worker, args, **kwargs):
                # A truncated one-column Q/R would previously reconstruct A
                # through zip truncation and conceal unsupported dimensions.
                Path(args[1]).write_text(json.dumps({"schema_version": 1, "operation": "qr", "octave_version": self.runtime_version,
                    "q": {"rows": 2, "columns": 1, "values": [1, 0]},
                    "r": {"rows": 2, "columns": 2, "values": [1, 2, 99, 99]}}))
                return {"exit_code": 0, "timed_out": False}
        with self.assertRaisesRegex(NacreError, "economy"):
            run(Worker(), "qr", {"a": [[1, 2], [0, 0]]})

    def test_invalid_inputs_fail_before_process(self):
        cases = [
            ("inverse", {"a": [[1, 2]]}), ("inverse", {"a": [[True]]}),
            ("inverse", {"a": [[2**53 + 1]]}), ("inverse", {"a": [[float("nan")]]}),
            ("inverse", {"a": [[1], [1, 2]]}), ("inverse", {"a": [[1j]]}),
            ("inverse", {"a": [[1]], "code": "system('bad')"}),
            ("eigen", {"a": [[0, -1], [1, 0]]}),
            ("polynomial", {"coefficients": [1], "points": []}),
            ("regression", {"x": [[1, 2]], "y": [[1]]}),
            ("fft", {"values": [1] * 65}), ("eval", {"expression": "1+1"}),
        ]
        for operation, parameters in cases:
            engine = Mock()
            with self.subTest(operation=operation, parameters=parameters), self.assertRaises(NacreError):
                run(engine, operation, parameters)
            engine.run_script.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("octave_courier"), "Optional Octave Courier is absent")
class RealOctaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from octave_courier import Octave, OctaveNotFound
        try:
            cls.engine = Octave(timeout=30)
        except OctaveNotFound as exc:
            raise unittest.SkipTest(str(exc))

    def check(self, operation, parameters):
        result = run(self.engine, operation, parameters)
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(len(result["execution"]["script_sha256"]), 64)
        return result

    def test_inverse(self):
        result = self.check("inverse", {"a": [[4, 1], [1, 3]]})
        self.assertAlmostEqual(result["result"][0][0], 3 / 11)

    def test_qr_rectangular(self):
        self.check("qr", {"a": [[1, 2], [3, 4], [5, 7]]})
        self.check("qr", {"a": [[1, 2, 3], [4, 5, 7]]})

    def test_eigen_symmetric_and_singleton(self):
        self.check("eigen", {"a": [[2, 1], [1, 2]]})
        self.assertEqual(self.check("eigen", {"a": [[3]]})["values"], [3])

    def test_polynomial(self):
        result = self.check("polynomial", {"coefficients": [2, -3, 1], "points": [-2, 0, 1, 2]})
        self.assertEqual(result["result"], [[15, 1, 0, 3]])

    def test_regression(self):
        result = self.check("regression", {"x": [[1, 0], [1, 1], [1, 2], [1, 3]], "y": [[1], [3], [5], [7]]})
        self.assertAlmostEqual(result["coefficients"][0][0], 1)
        self.assertAlmostEqual(result["coefficients"][1][0], 2)

    def test_fft_represents_complex_as_two_real_lists(self):
        self.check("fft", {"values": [0, 1, 0, -1]})
        self.check("fft", {"values": [3]})

    def test_ill_conditioning_rejected(self):
        from octave_courier import OctaveExecutionError
        for operation, params in [("inverse", {"a": [[1, 1], [1, 1]]}),
                                  ("inverse", {"a": [[1, 0], [0, 1e-12]]}),
                                  ("regression", {"x": [[1, 1], [2, 2]], "y": [[1], [2]]})]:
            with self.subTest(operation=operation), self.assertRaises(OctaveExecutionError):
                run(self.engine, operation, params)

    def test_falsified_worker_result_is_rejected(self):
        import json
        from pathlib import Path
        class WrongResult:
            runtime_version = "fake"
            def run_script(self, worker, args, **kwargs):
                Path(args[1]).write_text(json.dumps({"schema_version": 1, "operation": "polynomial", "octave_version": "fake", "result": {"rows": 1, "columns": 1, "values": [999]}}))
                return {"exit_code": 0, "timed_out": False}
        with self.assertRaisesRegex(NacreError, "tolerance"):
            run(WrongResult(), "polynomial", {"coefficients": [2], "points": [0]})
