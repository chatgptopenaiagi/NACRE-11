# Executable examples

Every published `.nac` file has an entry in `examples/manifest.json`. Release acceptance runs portable entries in fresh workspaces, checks the actual CLI exit code/status and expected values, and validates emitted artifact bytes. Optional entries have explicit prerequisites. In the default acceptance environment, their source is checked and their absent-integration diagnostic is tested with configuration cleared; their external workload is skipped with a reason. This is not a live integration test. Expected failures are successful acceptance cases only when the required diagnostic is observed.

Run from a copied source/examples tree using `nacre run examples/hello.nac`. Standalone users use `.\\nacre.exe` on Windows or `./nacre` on Linux in place of `nacre`.

| Program | Demonstration | Expected result |
|---|---|---|
| `hello.nac` | First program | `["Hello, Nacre-11!"]` |
| `arithmetic.nac` | Precedence and right-associated powers | `[14,512]` |
| `expressions.nac` | Typed immutable bindings and records | Record with total 42 |
| `mathematics.nac` | Local arithmetic/statistics | Squared hypotenuse 25 and mean 2.5 |
| `dependency-graph.nac` | Forward dependency references | `[42]` |
| `concurrent.nac` | Two independent bounded waits | `[42]` |
| `error-handling.nac` | Controlled retry-safe failure | `[42]` |
| `verification.nac` | New JSON output and artifact digest check | Artifact and true |
| `sqlite.nac` | Owned SQLite write, rollback and query | `[42,true]` |
| `transformation.nac` | Derive/filter/aggregate a typed table | `[78]` |
| `objects.nac` | Identity compared independently of revision | `[true]` |
| `modules.nac` | Workspace-contained include | `[42]` |
| `modules/constants.nac` | Include support file; also valid on its own | No emissions |
| `invalid-type.nac` | Expected compile error | Exit 2, TYPE |
| `failed-verification.nac` | Expected postcondition failure | Exit 1, VERIFY |
| `arithmetic-error.nac` | Expected runtime error | Exit 1, ARITHMETIC |
| `optional/symbolic.nac` | Configured GENESIS-9/SymPy | Derivative and independent evaluation |
| `optional/external-composition.nac` | Configured read-only SQL Server plus SymPy | Exact symbolic result 1764 |

All portable examples work without optional engines. File-generating examples should be run in a new workspace to avoid deliberately refused output overwrites. Copy the whole examples tree, including `modules/`, when experimenting in another folder.

The retry fixture creates a marker for its workspace/key. A repeated standalone run may no longer encounter the injected first failure. Release acceptance uses fresh workspaces so it observes the intended behavior. The fixture is not a claim about production service recovery.

To save and verify a receipt:

```shell
nacre run examples/verification.nac --receipt
nacre verify outputs/runs/RETURNED-UUID.json
```

Use the actual receipt path returned by the first command. Optional software setup is described in [Interoperability](INTEROPERABILITY.md); optional programs are never treated as portable successes merely because their source checks.
