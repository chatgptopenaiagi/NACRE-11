# Known limitations

Nacre-11 0.1.0 is an experimental composition language. Expect rough edges and incompatible changes during its 0.x evolution.

- Programs form finite graphs. There are no user functions, loops, mutable assignment, general exception handlers, reactive streams or distributed workers.
- The compiler emits inspectable JSON graph IR, not machine code. Saved IR is not currently loaded as an executable input format.
- Field/list projections often have static type Any and receive concrete runtime checks. Complete record-schema inference and parametric container types are absent.
- Number uses finite binary floating-point values. It is not an exact decimal type. Database decimal strings/native metadata require explicit interpretation and conversion.
- The capability catalogue is finite and trusted. Optional bridge presence is not a live service or compatibility guarantee. Arbitrary executables, Python functions and MCP servers cannot be invoked by inventing a capability name.
- GENESIS bridges require separately obtained compatible projects, engines, drivers and authorised configuration. They are not included in the portable release.
- `verify` runs after graph nodes. A failed postcondition cannot undo prior file/database effects. Required ordering must be expressed as a data dependency.
- Reads and writes rerun on resume. Writes receive no automatic retry, compensation or exactly-once guarantee. A crash can occur after an external commit but before checkpoint persistence.
- Resource locks coordinate one Runtime instance. They do not coordinate unrelated processes or provide cross-engine transactions. Already-running external operations may finish after cancellation.
- Checkpoints and receipts use integrity hashes, not authentication. Someone able to replace content and its digest can forge them. They can contain sensitive results.
- Work is materialized in memory. Joins are bounded nested loops; copying, validation and hashing add overhead. Parallel execution is not always faster, and no universal performance advantage is claimed.
- Parser/worker/row limits prevent selected accidental excesses; this is not a complete CPU, memory, filesystem or security sandbox.
- The Linux standalone artifact requires Linux x86_64 with glibc 2.43 or later. It does not target musl or all older distributions. The wheel is the alternative when a compatible Python is available.
- Native ARM64, macOS standalone binaries, code signing and an automatic updater are not supplied in this release. A universal wheel tag does not certify every OS, CPU or Python implementation.
- JSON output filenames refuse overwrite. Start artifact examples in a fresh workspace. Optional engine output ownership/readback rules are operation-specific.

The release manifest and acceptance record distinguish tests actually run from skipped optional or unsupported environments. Please report a minimal reproducible case for behavior outside these documented limits.
