"""Fixed, bounded bridges to installed engines; metadata does not execute them.

External dependencies load only after invocation. GENESIS-9 owns its existing
connections; Nacre writes only a separately marked demonstration table and its
own output files. No arbitrary command, Python or SQL write escape is exposed.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid

from .contracts import Capability, NacreError, canonical, fingerprint, type_of, validate

TABLE = "nacre11_demo_values"
OWNER = "GENESIS-11:Nacre-11:v1"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _configured_root(variable, required_file):
    value = os.environ.get(variable)
    if not value:
        raise NacreError("UNAVAILABLE", f"Optional integration is not configured; set {variable} to a compatible installation")
    root = Path(value).expanduser().resolve()
    if not (root / required_file).is_file():
        raise NacreError("UNAVAILABLE", f"{variable} does not identify a compatible integration installation")
    return root


def _genesis9_root():
    return _configured_root("NACRE_GENESIS9_ROOT", "genesis9/__init__.py")


def _genesis10_root():
    return _configured_root("NACRE_GENESIS10_ROOT", "genesis10/core.py")


def _load9():
    root = _genesis9_root()
    sys.dont_write_bytecode = True
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import genesis9  # Adds only its already installed project-local packages.
    if not Path(genesis9.__file__).resolve().is_relative_to(root):
        raise NacreError("UNAVAILABLE", "A different GENESIS-9 installation is already imported; restart after changing configuration")
    return genesis9


def _load10():
    _load9()
    root = _genesis10_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from genesis10.core import Ecosystem
    import genesis10.core
    if not Path(genesis10.core.__file__).resolve().is_relative_to(root):
        raise NacreError("UNAVAILABLE", "A different GENESIS-10 installation is already imported; restart after changing configuration")
    return Ecosystem(root)


def get_capabilities():
    definitions = [
        Capability("math.diff", {"expression": "String", "variable": "String"}, "Symbolic", retry_safe=True,
                   optional=("variable",), description="Exact symbolic derivative using the bounded GENESIS-9 SymPy worker", implementation="genesis9:mathematics.calculate:differentiate"),
        Capability("math.integrate", {"expression": "String", "variable": "String"}, "Symbolic", retry_safe=True,
                   optional=("variable",), description="Exact symbolic antiderivative", implementation="genesis9:mathematics.calculate:integrate"),
        Capability("math.solve", {"expression": "String", "variable": "String"}, "Symbolic", retry_safe=True,
                   optional=("variable",), description="Solve expression = 0 for one variable", implementation="genesis9:mathematics.calculate:solve"),
        Capability("math.simplify", {"expression": "String"}, "Symbolic", retry_safe=True,
                   description="Exact algebraic simplification", implementation="genesis9:mathematics.calculate:simplify"),
        Capability("math.numeric", {"expression": "String", "substitutions": "Record", "digits": "Integer"}, "Symbolic", retry_safe=True,
                   optional=("substitutions", "digits"), description="Exact expression plus explicitly labelled numerical approximation", implementation="genesis9:mathematics.calculate:evaluate"),
        Capability("math.matrix", {"matrix": "List", "operation": "String"}, "Symbolic", retry_safe=True,
                   optional=("operation",), description="Bounded rectangular matrices: determinant, inverse, rref, square", implementation="genesis9:mathematics.calculate:matrix"),
        Capability("db.query", {"source": "String", "sql": "String", "params": "Record", "limit": "Integer"}, "Table", "read", "database", True,
                   optional=("params", "limit"), description="One conservative parameterized SELECT; native decimal/timestamp metadata retained", implementation="genesis9:DatabaseManager.query+nacre:sqlite"),
        Capability("db.schema", {"source": "String"}, "Record", "read", "database", True,
                   description="Read-only native schema discovery", implementation="genesis9:DatabaseManager.inspect_schema+nacre:sqlite"),
        Capability("db.demo", {"source": "String", "value": "Integer", "fail": "Bool"}, "Record", "write", "database", False,
                   optional=("value", "fail"), description="Ownership-marked Nacre table in existing isolated genesis9_demo, or project SQLite; rollback/readback", implementation="nacre:owned-demo-v1"),
        Capability("joomla.products", {"limit": "Integer"}, "Table", "read", "joomla", True,
                   optional=("limit",), description="Dedicated existing Joomla/Phoca read-only application bridge", implementation="genesis9:JoomlaAdapter.list_products"),
        Capability("office.sheet", {"table": "Table", "filename": "String"}, "Artifact", "write", "office", False,
                   optional=("filename",), description="LibreOffice UNO XLSX/ODS creation and reopened cell verification in project outputs", implementation="genesis9:EngineManager.create_spreadsheet"),
        Capability("repo.select", {"query": "String"}, "Record", "read", "genesis10", True,
                   description="GENESIS-10 evidence-ranked selection with current source/proof checks", implementation="genesis10:Ecosystem.select"),
        Capability("repo.roundtrip", {}, "Record", "write", "genesis10", False,
                   description="Registered FOX-ENGINE/G9 lossless decision workflow and independent ledger/artifact verification", implementation="genesis10:fox-genesis9-roundtrip"),
    ]
    return {item.name: item for item in definitions}


def dependency_fingerprints():
    """Bind configured adapters only; never assume developer-specific locations."""
    from .identity import module_fingerprint
    result = {"nacre.adapters": module_fingerprint(__name__), "sqlite_version": sqlite3.sqlite_version}
    paths = []
    value = os.environ.get("NACRE_GENESIS9_ROOT")
    if value:
        root = Path(value).expanduser().resolve()
        result["NACRE_GENESIS9_ROOT"] = str(root)
        paths.extend(root / name for name in ("genesis9/__init__.py", "genesis9/mathematics.py", "genesis9/math_worker.py",
                     "genesis9/databases.py", "genesis9/joomla.py", "genesis9/engines.py", "scripts/joomla-readonly.php",
                     "config/engine-runtime.json", "config/database-runtime.json", "scripts/engines/classes/UnoDocument.class"))
        packages = root / "runtime/python-packages"
        for package in ("sympy", "sqlalchemy", "duckdb"):
            paths.append(packages / package / "__init__.py")
            paths.extend(packages.glob(package + "-*.dist-info/METADATA"))
    value = os.environ.get("NACRE_GENESIS10_ROOT")
    if value:
        root = Path(value).expanduser().resolve()
        result["NACRE_GENESIS10_ROOT"] = str(root)
        paths.extend(root / name for name in ("genesis10/core.py", "integrations/experiments.py"))
    result.update({str(path): _sha(path) if path.is_file() else "missing" for path in paths})
    from .numerical import dependency_fingerprints as numerical_dependencies
    result["numerical"] = numerical_dependencies()
    return result


def capability_availability():
    """Configuration/path discovery only, not an engine health or workload test."""
    configured = {}
    for variable, required in (("NACRE_GENESIS9_ROOT", "genesis9/__init__.py"), ("NACRE_GENESIS10_ROOT", "genesis10/core.py")):
        value = os.environ.get(variable)
        configured[variable] = bool(value and (Path(value).expanduser() / required).is_file())
    result = {}
    for name in get_capabilities():
        if name.startswith("db."):
            result[name] = {"available": True, "requires": [], "scope": "Portable SQLite source is available; remote database sources require NACRE_GENESIS9_ROOT and separate configuration",
                            "external_configured": configured["NACRE_GENESIS9_ROOT"]}
        else:
            required = ["NACRE_GENESIS9_ROOT"] + (["NACRE_GENESIS10_ROOT"] if name.startswith("repo.") else [])
            result[name] = {"available": all(configured[key] for key in required), "requires": required,
                            "scope": "Configured source path only; compatible dependencies and actual engine/service execution are not verified"}
    return result


def _workspace(context):
    root = Path(context.get("workspace", Path.cwd())).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _schema(rows, native=None):
    native = native or []
    names = [c["name"] for c in native] if native else list(dict.fromkeys(k for row in rows for k in row))
    result = []
    for name in names:
        samples = [row[name] for row in rows if name in row and row[name] is not None]
        kinds = {type_of(x) for x in samples}
        kind = next(iter(kinds)) if len(kinds) == 1 else ("Number" if kinds and kinds <= {"Integer", "Number"} else "Any")
        info = next((dict(c) for c in native if c["name"] == name), {})
        if "nullable" in info:
            info["declared_nullable"] = info["nullable"]
        result.append({**info, "name": name, "type": kind, "nullable": any(row.get(name) is None for row in rows) or not samples})
    return result


def _table(rows, source, *, native=None, **metadata):
    schema = _schema(rows, native)
    names = [c["name"] for c in schema]
    materialized = [{name: row.get(name) for name in names} for row in rows]
    result = {"$type": "Table", "schema": schema, "rows": materialized, "source": source,
              "snapshot": fingerprint(materialized), "count": len(materialized), **metadata}
    return validate(result, "Table", "adapter output")


def _symbolic(name, args):
    _load9()
    from genesis9.mathematics import calculate
    operation = {"math.diff": "differentiate", "math.integrate": "integrate", "math.solve": "solve",
                 "math.simplify": "simplify", "math.numeric": "evaluate"}.get(name)
    kwargs = dict(args)
    if name == "math.matrix":
        kind = kwargs.pop("operation", "determinant")
        operations = {"determinant": "matrix_determinant", "inverse": "matrix_inverse", "rref": "matrix_rref", "square": "matrix_multiply"}
        if kind not in operations:
            raise NacreError("ARGUMENT", "matrix operation must be determinant, inverse, rref or square")
        operation = operations[kind]
    # The Nacre math notation uses ^ for power, translated only inside this
    # explicit string boundary to the separately validated mathematical parser.
    if "expression" in kwargs:
        kwargs["expression"] = kwargs["expression"].replace("^", "**")
    result = calculate(operation=operation, **kwargs)
    return {"$type": "Symbolic", "expression": result["symbolic"], "engine": result["engine"],
            "exact": result["exact"], "version": result["version"], "approximation": result.get("approximation"),
            "approximation_digits": result.get("approximation_digits"), "operation": operation,
            "provenance": {"adapter": "GENESIS-9 validated mathematical worker", "input_sha256": fingerprint(args)}}


def _sqlite_path(context):
    outputs = _workspace(context) / "outputs"
    outputs.mkdir(exist_ok=True)
    return outputs / "nacre11-demo.sqlite3"


def _validate_sqlite_select(sql):
    """Conservative single SELECT plus SQLite's read-only connection controls."""
    statement = sql.strip()
    if len(statement) > 50000:
        raise NacreError("ARGUMENT", "SQLite query exceeds 50000 characters")
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if not re.match(r"SELECT\b", statement, re.I) or any(token in statement for token in (";", "--", "/*", "*/")):
        raise NacreError("ARGUMENT", "SQLite accepts one SELECT without comments; use bound parameters for values")


def _query(args, context):
    source, sql = args["source"], args["sql"]
    limit, params = args.get("limit", 100), args.get("params", {})
    if source != "sqlite":
        if source not in {"sqlserver", "postgresql", "mariadb"}:
            raise NacreError("ARGUMENT", "database source must be sqlite, sqlserver, postgresql or mariadb")
        _load9()
        from genesis9.databases import DatabaseManager
        result = DatabaseManager().query(source, sql, params=params, limit=limit)
        return _table(result["records"], "database:" + source + "/" + result["database"], native=result["field_types"],
                      read_only=True, truncated=result["truncated"], native_verification=result["verification"],
                      decimal_policy="Exact decimal strings, annotated with native precision and scale; no implicit numeric conversion")
    _validate_sqlite_select(sql)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise NacreError("ARGUMENT", "limit must be in 1..1000")
    path = _sqlite_path(context)
    if not path.is_file():
        raise NacreError("UNAVAILABLE", "Project SQLite database is absent; run db.demo(source=\"sqlite\") first")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        conn.execute("PRAGMA query_only=ON")
        cursor = conn.execute(sql, params)
        names = [col[0] for col in cursor.description]
        if len(names) != len(set(names)):
            raise NacreError("CONTRACT", "Duplicate SQL columns require aliases")
        rows = cursor.fetchmany(limit + 1)
        return _table([dict(zip(names, row)) for row in rows[:limit]], "database:sqlite/nacre11-demo",
                      read_only=True, truncated=len(rows) > limit, native=[{"name": n} for n in names])


def _schema_discovery(args, context):
    source = args["source"]
    if source != "sqlite":
        if source not in {"sqlserver", "postgresql", "mariadb"}:
            raise NacreError("ARGUMENT", "Unknown database source")
        _load9()
        from genesis9.databases import DatabaseManager
        return DatabaseManager().inspect_schema(source)
    path = _sqlite_path(context)
    if not path.is_file():
        raise NacreError("UNAVAILABLE", "Project SQLite database is absent")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as conn:
        tables = []
        for (table,) in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' ORDER BY name"):
            if table != TABLE:
                continue
            cols = conn.execute("PRAGMA table_info(" + TABLE + ")").fetchall()
            tables.append({"name": table, "columns": [{"name": c[1], "type": c[2], "nullable": not bool(c[3]), "primary_key": bool(c[5])} for c in cols]})
    return {"source_system": "sqlite", "tables": tables, "read_only": True}


@contextmanager
def _demo_connection(source, context):
    if source == "sqlite":
        conn = sqlite3.connect(_sqlite_path(context), timeout=5)
        try:
            yield conn, lambda sql, p=None: conn.execute(sql, p or {})
        finally:
            conn.close()
        return
    _load9()
    from genesis9.databases import DatabaseManager
    from sqlalchemy import text
    manager = DatabaseManager()
    engine = manager._engine(source, writer=True)
    try:
        with engine.connect() as conn:
            manager._guard(conn, source)
            yield conn, lambda sql, p=None: conn.execute(text(sql), p or {})
    finally:
        engine.dispose()


def _demo(args, context):
    source = args["source"]
    if source not in {"sqlite", "sqlserver", "postgresql"}:
        raise NacreError("ARGUMENT", "Demo writes allow project SQLite or isolated SQL Server/PostgreSQL genesis9_demo only; MariaDB remains read-only")
    value = args.get("value", 42)
    if not -(2**31) <= value < 2**31:
        raise NacreError("ARGUMENT", "Demo value must fit a signed 32-bit integer")
    # Isolated ownership marker precedes any mutation of an existing table.
    with _demo_connection(source, context) as (conn, execute):
        if source == "sqlserver":
            exists = execute("SELECT COUNT(*) FROM sys.tables WHERE name=:name", {"name": TABLE}).scalar_one()
        elif source == "postgresql":
            exists = execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name=:name", {"name": TABLE}).scalar_one()
        else:
            exists = execute("SELECT COUNT(*) FROM sqlite_schema WHERE type='table' AND name=:name", {"name": TABLE}).fetchone()[0]
        if not exists:
            execute("CREATE TABLE " + TABLE + " (id INTEGER PRIMARY KEY, value INTEGER NOT NULL, label VARCHAR(100) NOT NULL)")
            execute("INSERT INTO " + TABLE + " (id,value,label) VALUES (0,11,:owner)", {"owner": OWNER})
            if source == "postgresql":
                execute("GRANT SELECT ON " + TABLE + " TO genesis9_reader")
            conn.commit()
        marker = execute("SELECT value,label FROM " + TABLE + " WHERE id=0").fetchone()
        if marker is None or tuple(marker) != (11, OWNER):
            raise NacreError("OWNERSHIP", "Existing demonstration table lacks the GENESIS-11 ownership marker")
        conn.commit()
        # A normal operation commits; the fault-injection operation proves rollback
        # and returns both observations without pretending the write succeeded.
        previous = execute("SELECT value FROM " + TABLE + " WHERE id=1").fetchone()
        conn.commit()
        try:
            existing = execute("SELECT COUNT(*) FROM " + TABLE + " WHERE id=1").fetchone()[0]
            if existing:
                execute("UPDATE " + TABLE + " SET value=:value,label=:label WHERE id=1", {"value": value, "label": "nacre-demo"})
            else:
                execute("INSERT INTO " + TABLE + " (id,value,label) VALUES (1,:value,:label)", {"value": value, "label": "nacre-demo"})
            if args.get("fail", False):
                raise RuntimeError("INJECTED_FAILURE")
            conn.commit()
            committed = True
        except RuntimeError as exc:
            if str(exc) != "INJECTED_FAILURE":
                raise
            conn.rollback()
            committed = False
        except BaseException:
            conn.rollback()
            raise
    with _demo_connection(source, context) as (conn, execute):
        observed = execute("SELECT value FROM " + TABLE + " WHERE id=1").fetchone()
        observed = None if observed is None else observed[0]
        expected = value if committed else (None if previous is None else previous[0])
        if observed != expected:
            raise NacreError("VERIFY", "Independent committed/rolled-back value check failed")
    return {"source": source, "database": "nacre11-demo.sqlite3" if source == "sqlite" else "genesis9_demo",
            "table": TABLE, "committed": committed, "rolled_back": not committed, "observed": observed,
            "expected": expected, "verified": True, "ownership": OWNER,
            "transaction_scope": "One marked Nacre table; independent connection checks final state; no cross-engine atomicity"}


def _joomla(args):
    _load9()
    from genesis9.joomla import JoomlaAdapter
    result = JoomlaAdapter().list_products(args.get("limit", 5))
    fields = ("id", "title", "sku", "price", "stock", "catid", "date_update", "source_system")
    # The application bridge exposes the native object; this capability is an
    # explicit public catalogue projection, omitting download/internal fields.
    rows = [{name: row.get(name) for name in fields} for row in result["records"]]
    source_schema = result.get("schema", {})
    native = []
    for name in fields:
        col = {"name": name, "native_type": source_schema.get(name, "adapter-provided String" if name == "source_system" else "unknown")}
        decimal = re.fullmatch(r"(?:decimal|numeric)\((\d+),(\d+)\)", str(col["native_type"]), re.I)
        if decimal:
            col.update(precision=int(decimal[1]), scale=int(decimal[2]), encoding="exact decimal String")
        native.append(col)
    return _table(rows, "application:joomla/phocacart/products", native=native, read_only=True, truncated=result.get("truncated", False),
                  identity={"origin": "joomla", "kind": "phocacart.product", "key": "id", "ownership": "external-read-only"},
                  native_sha256=result["sha256"], adapter="GENESIS-9 dedicated application DatabaseInterface bridge")


def _sheet(args, context):
    _load9()
    from genesis9.engines import EngineManager
    root = _workspace(context)
    output = root / "outputs"
    output.mkdir(exist_ok=True)
    filename = args.get("filename", "nacre-sheet.xlsx")
    if not isinstance(filename, str) or Path(filename).name != filename or Path(filename).suffix.lower() not in {".xlsx", ".ods"}:
        raise NacreError("ARGUMENT", "Office filename must be a simple XLSX or ODS filename")
    stem, suffix = Path(filename).stem, Path(filename).suffix.lower()
    unique = stem + "-" + uuid.uuid4().hex[:12] + suffix
    engine = EngineManager(_genesis9_root())
    # Reuse the real engine config/classes while placing every new document,
    # temporary input and isolated UNO profile under this project.
    engine.root, engine.outputs = root, output
    result = engine.create_spreadsheet(args["table"]["rows"], unique)
    path = Path(result["path"])
    if not result.get("verified") or _sha(path) != result["sha256"]:
        raise NacreError("VERIFY", "Office output failed reopened content or SHA-256 checks")
    return {"$type": "Artifact", "path": str(path), "sha256": result["sha256"], "bytes": result["bytes"],
            "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if suffix == ".xlsx" else "application/vnd.oasis.opendocument.spreadsheet",
            "engine": "LibreOffice UNO", "verified": True, "source_snapshot": fingerprint(args["table"]["rows"]),
            "source": args["table"]["source"], "contract": result["contract"], "readback": result,
            "ownership": "Nacre-11 created artifact; source objects unchanged"}


def _repo(name, args):
    ecosystem = _load10()
    if name == "repo.select":
        return ecosystem.select(args["query"])
    receipt = ecosystem.execute("fox-genesis9-roundtrip")
    verification = ecosystem.verify(receipt["execution_id"])
    if not receipt.get("verified") or not verification.get("verified"):
        raise NacreError("VERIFY", "GENESIS-10 FOX roundtrip or independent receipt verification failed")
    return {"workflow": "fox-genesis9-roundtrip", "execution_id": receipt["execution_id"],
            "verified": True, "result": receipt["result"], "verification": verification,
            "receipt_path": receipt["receipt_path"], "receipt_sha256": receipt["receipt_sha256"],
            "source_bindings": {str(_genesis10_root() / "integrations/experiments.py"): _sha(_genesis10_root() / "integrations/experiments.py")},
            "scope": "Existing registered FOX-ENGINE decision through GENESIS-9 typed interchange, not arbitrary repository function execution"}


def invoke(name, args, context=None):
    context = context or {}
    definitions = get_capabilities()
    if name not in definitions:
        raise NacreError("CAPABILITY", "Unknown installed capability: " + name)
    definition = definitions[name]
    if not isinstance(args, dict) or set(args) - set(definition.inputs):
        raise NacreError("ARGUMENT", "Unknown or invalid capability arguments")
    for key, kind in definition.inputs.items():
        if key not in args:
            if key not in definition.optional:
                raise NacreError("ARGUMENT", "Missing capability argument: " + key)
        else:
            validate(args[key], kind, name + "." + key)
    event = context.get("cancel_event")
    if event is not None and event.is_set():
        raise NacreError("CANCELLED", "Execution cancelled before adapter invocation")
    try:
        if name.startswith("math."):
            result = _symbolic(name, args)
        elif name == "db.query":
            result = _query(args, context)
        elif name == "db.schema":
            result = _schema_discovery(args, context)
        elif name == "db.demo":
            result = _demo(args, context)
        elif name == "joomla.products":
            result = _joomla(args)
        elif name == "office.sheet":
            result = _sheet(args, context)
        elif name.startswith("repo."):
            result = _repo(name, args)
        else:
            raise NacreError("CAPABILITY", "Capability has no implementation")
        return validate(result, definition.output, name + " output")
    except NacreError:
        raise
    except Exception as exc:
        # Never interpolate database errors/URLs or private configuration into
        # language diagnostics. Protocol-specific details stay with their owner.
        transient = type(exc).__name__ in {"TimeoutExpired", "TimeoutError", "OperationalError", "ConnectionError"}
        raise NacreError("ADAPTER", name + " failed (" + type(exc).__name__ + ")", retryable=transient and definition.retry_safe) from exc
