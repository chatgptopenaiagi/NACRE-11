# Nacre-11 language guide

A Nacre program describes a finite graph of immutable values and capability calls. The compiler resolves names and dependencies before the runtime invokes any capability. Save programs as UTF-8 files ending in `.nac`.

## Values and expressions

```nacre
let quantity: Integer = 6;
let price: Integer = 7;
let total: Integer = quantity * price;
let label: String = "verified " + "total";
verify total == 42;
emit {label:label,total:total};
```

Bindings are typed and cannot be reassigned. Available types are Null, Bool, Integer, Number, String, List, Record, Table, Symbolic, Artifact, Object and Any. An Integer is accepted where Number is required; strings are not automatically converted to numbers. Booleans are distinct from numbers.

Arithmetic supports `+ - * / % ^`. Exponentiation is right-associative: `2^3^2` is 512. Unary minus binds below exponentiation, so `-2^2` is -4. `+` also combines two strings or two lists. Use `and`, `or` and `not` for Boolean expressions.

Records have string fields and lists have nonnegative, zero-based indices:

```nacre
let item: Record = {id:42,name:"sample"};
let values: List = [10,20,30];
verify item.id == 42 and values[1] == 20;
emit item;
```

Field projections often have static type Any; their concrete values are checked when consumed. Missing fields and out-of-range indices fail.

## Tasks and dependencies

```nacre
task total: Number <- core.sum(values=[left,right]);
let right: Integer = 22;
let left: Integer = 20;
verify total == 42;
emit total;
```

A `task` calls a registered capability with named arguments. Forward references are legal. Each referenced binding becomes an edge in the dependency graph; cycles and unknown names are rejected. Unused graph nodes still execute.

Independent nodes can run concurrently within `--workers 1..32`. Textual source order does not order external effects. Express ordering using an actual data dependency. Locks exclude overlapping non-pure work on a shared resource within one runtime instance, and do not promise a global order.

## Tables and mathematical computation

`data.table`, `data.filter`, `data.derive`, `data.column`, `data.stats` and `data.join` provide bounded structured transformations. Ordinary arithmetic and statistics work with the minimal runtime. See `examples/mathematics.nac` and `examples/transformation.nac`.

Symbolic algebra is a separate optional engine boundary. An unconfigured `math.diff` call fails with an availability diagnostic; the portable runtime does not silently install or substitute a symbolic engine.

## Postconditions and outputs

`verify` expressions run after all graph nodes succeed. Each must return true. Only after all postconditions pass are `emit` expressions evaluated in source order. A failed verification suppresses successful emissions, but cannot undo completed external effects.

`io.write_json` creates a new file under workspace `outputs/` and returns an Artifact with its path and hash. `core.artifact_verify` compares the current file bytes with that hash. Files are not silently overwritten.

## Modules and aliases

```nacre
include "modules/constants.nac";
use c = "core";
task answer: Number <- c.sum(values=[base,2]);
verify answer == 42;
emit answer;
```

Includes resolve relative to the including file and must remain inside the workspace. They expand once into a flat declaration scope. Include cycles and duplicate names are errors. A `use` statement aliases a registered capability namespace; it does not import arbitrary host-language modules.

## Errors, retries and resume

The language has structured failures, not `try/catch` syntax. The compiler refuses unsafe retries. `retry 1` allows one additional attempt only for a declared retry-safe, non-write capability and a retryable runtime error. The `demo.flaky` example uses a controlled local marker to demonstrate this policy; it is not real network failover.

`--checkpoint FILE` records execution state. `--resume` can reuse matching pure results after source, contract, implementation and input checks. Reads and writes execute again. Writes are not automatically retried; no exactly-once or cross-engine transaction guarantee is provided.

Continue with the [reference](LANGUAGE-REFERENCE.md), [grammar](SYNTAX.md), [runtime](RUNTIME-ARCHITECTURE.md) and [limitations](KNOWN-LIMITATIONS.md).
