# Nacre-11 compiler architecture

The compiler in `src/nacre/language.py` translates Nacre source to checked graph IR, format `nacre-ir-1`. It does not emit machine code. `compile` writes inspectable JSON; `run` recompiles source and interprets the checked plan. Loading arbitrary saved IR for execution is not implemented.

## Pipeline

1. `lex(source)` recognizes identifiers, JSON strings, numeric literals, operators, comments and delimiters, preserving token line/column locations.
2. `Parser.parse()` constructs statement dictionaries. A Pratt parser builds literal, reference, list, record, index, unary and binary expression nodes.
3. `compile_source(...)` expands workspace-contained `.nac` includes once. It records source identities, rejects include cycles and uses one flat declaration scope.
4. A declaration pass collects capability aliases and unique typed value names. This permits forward references without executing anything.
5. `infer(...)` checks local expression categories, argument names/types, result declarations and Boolean postconditions. Unknown projections propagate `Any` and receive runtime validation.
6. `references(...)` extracts dependency names. Iterative Kahn validation rejects graph cycles without recursive graph traversal.
7. `Plan` preserves nodes, postconditions, emissions, aliases, module fingerprints and source/capability hashes.

The compiler does not connect to databases, start Office or invoke mathematical engines. Capability descriptor discovery reads local implementation metadata only; checking is separate from functional availability testing.

## IR contract

Each node retains `kind`, `name`, declared `type`, source/line, expression or resolved capability/arguments, effect, resource and sorted dependencies. Tasks also retain retry count. `Plan.to_dict()` contains `format`, `nodes`, `verifications`, `emissions`, `aliases`, `source_hash`, `capabilities_hash` and `modules`. Contract hashing uses stable canonical JSON with sorted keys and rejects nonportable numeric values.

There is no optimizer, bytecode VM, JIT, native code generation, Hindley-Milner inference, parametric container type syntax, user function compiler or SQL compiler. These would add scope without proving the composition hypothesis. The existing independent mathematical and database parsers own their explicit payload languages.

## Diagnostics and limits

Errors identify a category and available source/binding location. Common categories include `SYNTAX`, `NAME`, `TYPE`, `DUPLICATE`, `CAPABILITY`, `ARGUMENT`, `RETRY`, `MODULE`, `CYCLE` and `LIMIT`. Runtime conditions such as a missing record field, invalid column name or unavailable engine are not generally decidable during this coarse static pass.

Lexing limits each source text to 1,000,000 characters and 100,000 tokens. Non-finite numeric literals fail during checking; integer literals exceeding 4,300 decimal digits are rejected consistently across supported Python versions. Expression parser nesting and AST depth are bounded at 100, including long left-associated expressions; aggregate statements at 10,000; include nesting at 32. Reserved value names and aliases are rejected. These are defensive bounds, not a complete resource sandbox. Release acceptance and CI record the actual tests and source commit; see [Contributing](CONTRIBUTING.md).

## Installation boundary

The compiler runs from an installed wheel, a source checkout or a bundled interpreter. The current directory or explicit `--workspace` supplies the user workspace; package installation paths do not select output directories. Code identity uses loaded module code rather than requiring loose source files beside a frozen executable. Optional engine imports are deferred until their explicit invocation.
