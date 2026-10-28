# Interoperability boundaries

Nacre exposes a finite catalogue of implemented capability contracts. `nacre capabilities` lists descriptors and availability metadata without starting engines. Availability means that a portable route or configured bridge has been recognised; it is not a live service check or proof that every described operation currently works.

## Portable routes

The minimal core uses the Python standard library. Local expression arithmetic, immutable values, table transformations, statistics, output artifacts and controlled scheduling/recovery demonstrations need no external service.

SQLite is part of the portable Python runtime. `db.demo(source="sqlite")` creates or updates only the ownership-marked `nacre11_demo_values` table inside the workspace's `outputs/nacre11-demo.sqlite3`. `db.query` performs a bounded read-only SELECT; `db.schema` discovers the supported local schema. Database setup is explicit, and SQLite access does not load a GENESIS bridge.

## Optional GENESIS compatibility bridges

Version 0.2.0 also provides independent numerical bridges described in [Numerical capabilities](NUMERICAL-CAPABILITIES.md). `octave.*` uses public Octave Courier0.1 APIs and a separately installed GNU Octave runtime; `symbolic.polynomial` uses a separately installed SymPy package. Neither requires GENESIS-9. The optional `NACRE_GENESIS10_ROOT` setting lets `engine.discover` include repository evidence metadata without loading repository code or treating historical proof as current engine health.

Users who already possess compatible GENESIS software can opt in using explicit environment variables:

```shell
NACRE_GENESIS9_ROOT=/path/to/compatible/GENESIS-9
NACRE_GENESIS10_ROOT=/path/to/compatible/GENESIS-10
```

Set these in your shell's normal syntax. For example, PowerShell uses `$env:NACRE_GENESIS9_ROOT = 'D:\\my-adapters\\GENESIS-9'`; a POSIX shell uses `export NACRE_GENESIS9_ROOT=/path/to/GENESIS-9`. These are user-chosen paths, not bundled projects or download instructions. Do not point a bridge at untrusted source code: adapters run as trusted host code with your process permissions.

| Capability group | Existing interface required | Scope |
|---|---|---|
| `math.*` | Compatible GENESIS-9 bounded SymPy worker | Selected algebra, calculus, equations, matrices and numeric evaluation |
| `db.*` external sources | GENESIS-9 database manager and configured drivers/connections | SQL Server, PostgreSQL and MariaDB bounded queries/schema; restricted demo writes |
| `joomla.products` | Existing GENESIS-9 read-only application bridge | Authorized projected product fields |
| `office.sheet` | Existing GENESIS-9 LibreOffice UNO route | New XLSX/ODS output with engine readback |
| `repo.select`, `repo.roundtrip` | Compatible GENESIS-10 and its GENESIS-9 requirements | Selection or its named bounded FOX roundtrip workflow |

The public package does not distribute those projects, credentials, database configurations, drivers, application installations or third-party repository contents. No bridge is automatically installed or enabled. An unconfigured invocation reports UNAVAILABLE. Configuration recognition alone does not validate a database login, service listener, native executable or a compatible revision; run a bounded authorised workload before relying on one.

External database operations retain their own SQL dialects. MariaDB and Joomla bridges are read-only. External demonstration writes remain limited to ownership-marked isolated demo tables, rather than arbitrary DDL/DML. Do not configure them against production data merely to try an example.

The original workstation prototype demonstrated SQL Server, PostgreSQL, SymPy, LibreOffice, Joomla and repository workflows. Its historical integration counts are not public portability guarantees. Public acceptance distinguishes the standalone core from optional integrations.

## Domain values

Tables retain schemas, nominal column types, nullability and source metadata. Exact database decimals may be represented as strings with native precision/scale; conversion to binary Number can lose exactness. A local materialized join is not a federated optimiser or an atomic cross-database snapshot.

Objects identify an origin, kind and id, plus revision and ownership metadata. Identical ids from different origins do not automatically denote the same object. A serialized object or ownership label confers no authority to update an external system.

Artifacts carry a path and SHA-256. Verification checks bytes under the selected workspace outputs. Symbolic results carry engine and expression metadata; they are not implicitly executable host-language strings.

## Optional MCP interface

Install the wheel with its `mcp` extra, then configure a stdio MCP client to execute that environment's Python with arguments `["-m", "nacre.mcp_server"]` and the intended working directory. No Codex installation is a Nacre dependency, and the package does not modify a client's configuration.

The five tools are `nacre_discover`, `nacre_check`, `nacre_run`, `nacre_run_file` and `nacre_verify`. They use the same compiler/runtime as the CLI. File runs are restricted to workspace `.nac` files, and receipts/checkpoints are constrained to their documented output locations. Treat source from an MCP client as code to review before authorising effectful execution.

MCP tooling does not make arithmetic depend on an AI model. Existing engine integration, source checking, actual execution and receipt verification remain distinct evidence levels.
