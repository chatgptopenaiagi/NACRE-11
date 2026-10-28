"""Adapter boundary tests: no credentials, live services, or engine launches."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from threading import Event
import unittest
from unittest.mock import patch

from nacre import adapters
from nacre.contracts import NacreError


class AdapterBoundaryTests(unittest.TestCase):
    def test_discovery_does_not_launch_or_import_engine(self):
        with patch.object(adapters, "_load9", side_effect=AssertionError("engine imported")):
            capabilities = adapters.get_capabilities()
        self.assertIn("joomla.products", capabilities)
        self.assertEqual(capabilities["office.sheet"].effect, "write")
        self.assertFalse(capabilities["db.demo"].retry_safe)
        self.assertEqual(capabilities["db.query"].output, "Table")

    def test_argument_contracts_fail_before_engine_invocation(self):
        cases = [("math.diff", {}), ("math.diff", {"expression": 42}),
                 ("math.diff", {"expression": "x", "shell": "ignored"}),
                 ("absent.command", {})]
        with patch.object(adapters, "_load9", side_effect=AssertionError("engine imported")):
            for name, arguments in cases:
                with self.subTest(name=name, arguments=arguments), self.assertRaises(NacreError):
                    adapters.invoke(name, arguments)

    def test_cancellation_prevents_external_work(self):
        event = Event()
        event.set()
        with patch.object(adapters, "_load9", side_effect=AssertionError("engine imported")):
            with self.assertRaises(NacreError) as failure:
                adapters.invoke("math.diff", {"expression": "x"}, {"cancel_event": event})
        self.assertEqual(failure.exception.code, "CANCELLED")

    def test_tagged_output_contract_is_enforced(self):
        with patch.object(adapters, "_symbolic", return_value={"expression": "x", "engine": "fake"}):
            with self.assertRaises(NacreError) as failure:
                adapters.invoke("math.diff", {"expression": "x"})
        self.assertEqual(failure.exception.code, "TYPE")

    def test_table_retains_exact_decimal_native_precision(self):
        value = adapters._table([{"amount": "12345678901234567890.12345678"}], "database:fixture", native=[{"name": "amount", "python_type": "Decimal", "precision": 38, "scale": 8, "nullable": True}])
        self.assertEqual(value["rows"][0]["amount"], "12345678901234567890.12345678")
        self.assertEqual(value["schema"][0]["type"], "String")
        self.assertEqual(value["schema"][0]["scale"], 8)
        self.assertTrue(value["schema"][0]["declared_nullable"])
        self.assertEqual(value["source"], "database:fixture")

    def test_table_rejects_duplicate_native_columns(self):
        with self.assertRaises(NacreError) as failure:
            adapters._table([{"x": 1}], "fixture", native=[{"name": "x"}, {"name": "x"}])
        self.assertEqual(failure.exception.code, "CONTRACT")

    def test_mariadb_demo_write_is_rejected_without_opening_database(self):
        with patch.object(adapters, "_load9", side_effect=AssertionError("engine imported")):
            with self.assertRaises(NacreError) as failure:
                adapters.invoke("db.demo", {"source": "mariadb"})
        self.assertEqual(failure.exception.code, "ARGUMENT")

    def test_sqlite_commit_rollback_and_repeated_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            context = {"workspace": Path(directory)}
            committed = adapters.invoke("db.demo", {"source": "sqlite", "value": 42}, context)
            failed = adapters.invoke("db.demo", {"source": "sqlite", "value": 99, "fail": True}, context)
            repeated = adapters.invoke("db.demo", {"source": "sqlite", "value": 42}, context)
            schema = adapters.invoke("db.schema", {"source": "sqlite"}, context)
            self.assertTrue(committed["committed"])
            self.assertTrue(failed["rolled_back"])
            self.assertEqual(failed["observed"], 42)
            self.assertEqual(repeated["observed"], 42)
            self.assertTrue(all(r["verified"] for r in (committed, failed, repeated)))
            self.assertEqual(schema["tables"][0]["name"], adapters.TABLE)
            # A new independent connection proves handles were cleaned up.
            with closing(sqlite3.connect(Path(directory) / "outputs/nacre11-demo.sqlite3", timeout=0.1)) as conn:
                conn.execute("BEGIN EXCLUSIVE")
                conn.rollback()

    def test_sqlite_refuses_to_mutate_unowned_same_named_table(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "outputs"
            output.mkdir()
            path = output / "nacre11-demo.sqlite3"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE " + adapters.TABLE + "(id INTEGER PRIMARY KEY,value INTEGER,label TEXT)")
                conn.execute("INSERT INTO " + adapters.TABLE + " VALUES(0,11,'OTHER-PROJECT')")
                conn.commit()
            with self.assertRaises(NacreError) as failure:
                adapters.invoke("db.demo", {"source": "sqlite", "value": 123}, {"workspace": Path(directory)})
            self.assertEqual(failure.exception.code, "OWNERSHIP")
            with closing(sqlite3.connect(path)) as conn:
                rows = conn.execute("SELECT * FROM " + adapters.TABLE).fetchall()
            self.assertEqual(rows, [(0, 11, "OTHER-PROJECT")])


if __name__ == "__main__":
    unittest.main()
