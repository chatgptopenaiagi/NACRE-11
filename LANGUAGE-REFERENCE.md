# Nacre-11 language reference, version 0.1

Nacre-11 is a small language for checked composition of registered software capabilities. Its computational unit is a finite immutable dependency graph. The source has its own lexer, parser, type checker and expression interpreter; neither a `.nac` program nor its local expressions are evaluated as Python, PowerShell or SQL. External engines receive only explicit adapter payloads.

```nacre
use c = "core";
let expected: Integer = 42;
task actual: Number <- c.sum(values=[20,22]);
verify actual == expected;
emit actual;
```

## Programs, values and types

A program contains `use`, `include`, `let`, `task`, `verify` and `emit` statements. Each value binding has a unique name and an explicit type. Bindings may reference later declarations; the compiler checks the resulting graph for cycles. Aliases and value names occupy separate compiler maps. All declarations are checked before any capability invocation. Unused graph nodes still execute: this prototype does not perform dead-code elimination.

| Type | Meaning |
|---|---|
| `Null` | `null` |
| `Bool` | `true` or `false`; distinct from numbers |
| `Integer` | Host arbitrary-precision integer within implementation/resource limits |
| `Number` | Numeric supertype accepting integers or finite binary floating-point values |
| `String` | Unicode text |
| `List` | Ordered portable values; element types checked at operation boundaries |
| `Record` | String-keyed portable values |
| `Table` | Validated schema, exact row fields, column types/nullability, and source identity |
| `Symbolic` | Tagged result with expression text, engine and adapter metadata |
| `Artifact` | Tagged file reference with path and SHA-256 |
| `Object` | Tagged external identity with origin, kind, id, revision and ownership |
| `Any` | Gradual boundary whose concrete value is checked at runtime |

Compatibility is exact nominal equality, `Integer` to `Number`, or any valid portable value to `Any`. There is no implicit string-to-number conversion, domain-object coercion or engine-independent decimal type. Non-finite floating-point values and unsupported host objects are rejected. Portable records with reserved `$type` tags must satisfy the corresponding domain contract; serialization alone is insufficient.

The reserved `$type` field accepts only `Table`, `Symbolic`, `Artifact` and `Object`. A record cannot impersonate a primitive or container type by naming it in this field. Table column `nullable` metadata, when supplied, must be a Boolean; artifact digests must contain exactly 64 hexadecimal digits. Malformed tags and metadata produce structured language errors.

Lists and records are copied at expression/reference and adapter boundaries. Nacre source cannot mutate a bound value. This is value-level immutability, not a guarantee that an external database or file cannot change.

## Local expression semantics

Arithmetic supports `+ - * / % ^` with precedence in `SYNTAX.md`. `/` produces a numeric division result; `^` denotes exponentiation. `+` also concatenates two strings or two lists. Arithmetic rejects booleans and incompatible types. Ordering accepts numeric pairs or two strings. `and` and `or` short-circuit and require booleans; `not` requires a boolean. The static dependency graph conservatively includes references from both Boolean operands even when one will not be evaluated.

Numeric equality permits integer/float equivalence. Other equality uses compatible top-level nominal types and canonical JSON representations; for example, `true == 1` is false. Structured equality is representation-sensitive, so `[1] == [1.0]` is false. Field access `r.name` is `r["name"]`; list/string indices are zero-based nonnegative integers. Missing fields and out-of-range indices fail. Most field access is statically `Any` and is validated when consumed; this prototype does not infer complete record schemas through bindings.

## Capability and task semantics

A capability is a registered `Capability` descriptor plus an implemented invocation route. The descriptor names inputs, optional inputs, output type, effect (`pure`, `read`, `write`), resource key, replay safety and implementation identity. An unknown namespace/operation, missing/extra parameter, incompatible known input/output type or unsafe retry is a compile error.

A task evaluates named argument expressions from completed dependencies, validates those values, invokes its implementation and validates both the contract output and its declared result type. Effects are contract metadata trusted by the runtime. `pure` means cache-eligible computation; `read` observes an external source; `write` may create/change state. It is not a general algebraic effect calculus or a security sandbox.

## Dependencies and execution order

Every referenced binding adds a graph dependency. A node is eligible only when all dependencies have succeeded. Independent nodes may execute concurrently within the worker bound. Non-pure calls sharing a resource key are mutually exclusive within one `Runtime` instance. A lock prevents overlap; it does not promise source-order scheduling. Independent database operations are not ordered by their written line order. Express required ordering through a real value dependency.

After every graph node succeeds, `verify` predicates run in source order; each must produce `true`. They are postconditions, not barriers that guard earlier writes. If all predicates pass, `emit` expressions are evaluated in source order. A false predicate yields `VERIFY` failure and suppresses successful emission. Prior external effects are not undone by a failed predicate.

## Errors, recovery and verification

Language errors carry `code`, `message`, source `line`, binding `node` and `retryable`. Parse/check failures prevent execution. During execution, failed nodes prevent their dependents from starting; the scheduler stops submitting new work and signals cooperative cancellation. Already-running external operations may finish. There is no language-level `try`/`catch` or fallback branch.

`retry n` permits at most `n` extra attempts, from zero to ten. It is legal only for declared retry-safe non-write capabilities and occurs only for a retryable structured error. There is no automatic retry of write effects. `demo.flaky` supplies a controlled first-failure example, not a simulation of all network errors.

Checkpoint/resume preserves completed pure-node results under program, contract, implementation and dependency-value checks. Reads and writes run again. A resumed pure consumer is reused only if its newly obtained dependency values match. A checkpoint digest detects accidental corruption; it is not authentication against an actor able to rewrite both contents and digest. Consult `RUNTIME-ARCHITECTURE.md` for exact scope and crash limits.

Verification has several levels: runtime type/shape validation; explicit language predicates; adapter-specific readback/transaction checks; and saved-result/artifact digest checks. These are distinct. Hash agreement does not prove arbitrary mathematics, ownership authority or truthful adapter behavior.

## External objects and persistent state

An `Object` uses `(origin, kind, id)` as identity; revision and ownership are required metadata. `core.same_object` compares identity, deliberately ignoring revision and ownership. Revision is an opaque source-supplied string, not a distributed version clock. An object record confers no authority to update its source. Snapshots may be copied; mutations require a separately registered operation. Generic write-back and automatic cross-system identity reconciliation are absent.

Tables retain source/schema metadata and may include snapshot/provenance/native type metadata. Database decimal values remain exact strings annotated with native precision and scale where provided. Explicit conversion to `Number` can lose decimal exactness. Artifacts carry content hashes and workspace ownership metadata. Generated files do not transfer ownership of the source objects from which they were derived.

Between executions, persist source/includes, runtime/adapter bindings, capability descriptors, checkpoints when used, receipts, artifacts and experiment evidence. The runtime does not require an AI model. Main limitations are the finite trusted catalogue, coarse `Any` projections, local scheduling, no cross-engine atomicity, and no exactly-once external effects.

## Portable and optional capabilities

Version 0.2.0 adds capability contracts, not new grammar or nominal types. Matrices are nested `List` values with explicit finite-real shape checks; results, engine identities and independent checks are `Record` values. New `engine.*`, `octave.*`, `matrix.verify` and `symbolic.polynomial` contracts are listed in [Numerical capabilities](NUMERICAL-CAPABILITIES.md). Existing v0.1 source syntax and post-graph verification semantics remain unchanged. Updated implementation/contract identities deliberately invalidate older checkpoints; rerun the program to create a new checkpoint.

The public core requires no third-party runtime package for local arithmetic, structured transformations, artifacts or SQLite. Symbolic and external application/database/repository routes require explicitly configured compatible bridges. `nacre capabilities` separates descriptors from configuration availability, which is not a live service check. See [Interoperability](INTEROPERABILITY.md).
