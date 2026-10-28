# Nacre-11 runtime architecture

`src/nacre/runtime.py` interprets a checked `Plan`. This is a local finite-graph runtime implemented with the existing Python standard library; no AI inference, workflow server or remote worker is required.

## Scheduling and isolation

`Runtime(capabilities, invoke, workspace, workers=4)` accepts 1..32 workers. `run(plan, checkpoint=None, resume=False, cancel_event=None)` validates current contracts against the plan, then repeatedly submits nodes whose named dependencies are complete. Ready nodes use declaration order for admission; completion order depends on work duration. Outputs and postconditions retain source order. The runtime copies values into task snapshots to prevent accidental sharing of mutable host containers.

Local `let` expressions and `pure` capabilities may overlap. `read` and `write` tasks acquire a lock using their declared resource or capability name. Thus the current shared `database` key conservatively serializes database calls, even across distinct engines; independent pure mathematics may overlap with database work. Locks belong to one runtime instance. They provide neither cross-process coordination nor transactions. They guarantee exclusion, not ordering among independent tasks.

Every submitted node produces start/completion/failure events. A node failure stops submission, signals a cancellation event and prevents dependent execution. In-flight operations are awaited and may still produce side effects. `core.wait` cooperates with the cancellation event; most external calls can only be cancelled before invocation or bounded by their existing adapter timeout. There is no forcible rollback of an already-running external process.

After graph success, Boolean `verify` expressions run, followed by `emit` expressions. A verification is a postcondition, not a graph node or effect barrier. A failed postcondition cannot undo completed writes.

A cancellation event already set when execution starts also suppresses postconditions and emissions for a program with no graph nodes. Arithmetic errors in bindings, postconditions and emissions consistently use `ARITHMETIC` diagnostics with the failing expression's source line.

## Retry policy

The compiler permits `retry n` only for non-write capabilities with `retry_safe=True`. Runtime repeats an invocation only after `NacreError(retryable=True)` and only within the explicit extra-attempt count. Arguments are evaluated once for that task. Write effects are never automatically retried, even if a custom descriptor labels them retry-safe. There is no retry backoff or language-level alternate branch in version 0.1.

`demo.flaky` intentionally creates a workspace marker and fails the first invocation for a key. Later attempts return the supplied value. This controlled test is classified as a replay-safe read for scheduling purposes despite its test marker; it is a demonstration instrument, not a production read abstraction.

## Checkpoint and resume

With a checkpoint path, the scheduler writes `nacre-checkpoint-1` documents at start, completion/failure observations and final status. A document includes run id, signature, successful node records, status/error and a digest. Node records contain the value, value hash, input hash and effect. Persistence writes a unique temporary file, flushes and `fsync`s it, then atomically replaces the destination; temporary cleanup is attempted even on failure.

The signature binds program/module fingerprints, capability contracts and the runtime implementation digest. Loaded Python module code supplies implementation fingerprints, so installed wheels and frozen executables do not require loose `.py` files beside the launcher. The interpreter version, selected environment identity, SQLite version and configured external dependency fingerprints also participate; frozen execution additionally binds the executable's bytes. These are selected implementation/runtime bindings, not a complete snapshot of every installed package, native library or service. Runtime changes outside the observed binding require a fresh checkpoint and scoped verification.

`--resume` requires an existing valid checkpoint and matching signature. A pure node can reuse a recorded value only when its current node/dependency-value input hash and recorded value hash match and its declared type validates. External reads and writes always execute again. Therefore a pure transform of a read snapshot is reused only when the new read produces the same dependency value. Postconditions and emissions are recomputed.

This mechanism detects accidental corruption and observed code/contract/source changes. Plain hashes are not signatures or authentication: a malicious author able to replace both a checkpoint and its digest can forge it. Checkpoints contain result values and must be stored with the same care as those results. The CLI accepts a caller-supplied path; the MCP interface constrains its checkpoint name under workspace `outputs/`.

## Effects and crash ambiguity

The journal is not a distributed commit log. A process can crash after a database commit or file creation and before successful persistence. Because writes execute again on resume, the operator must inspect prior external state before resuming a program with writes. `io.write_json` refuses existing files; Office uses fresh unique output names; the owned demo database write updates only its marked table. These are operation-specific behaviors, not exactly-once execution.

`db.demo` has its own transaction and readback within one database. It cannot atomically coordinate a PostgreSQL commit with a SQL Server write or an Office file. Failed `verify` predicates do not trigger compensating transactions. There is no cross-engine atomicity, distributed lock service, automatic compensation or global rollback.

## Results and diagnostics

A run returns `status` (`passed`, `failed`, `cancelled`), `run_id`, binding `results`, ordered `emitted` values, postcondition observations, events, structured error, resume flag, elapsed milliseconds, worker count and pending names. Error codes distinguish syntax/checking from runtime arithmetic/index/adapter/verification/checkpoint failures. Non-language arithmetic exceptions become `ARITHMETIC`; other unexpected runtime exceptions become `EXECUTION`. Invalid checkpoint setup fails before effects. A midrun persistence failure stops dependent scheduling. A final persistence failure returns failed status and `checkpoint_error` while retaining completed results, since their effects may already have occurred.

`api.save_receipt` persists a result with its digest under `outputs/runs/`. `api.verify_receipt` rechecks that digest and currently available artifact bytes within the workspace. It does not rerun the program, authenticate external evidence or prove arbitrary mathematical truth. MCP runs save receipts; CLI `run --receipt` also saves a new receipt and returns its path. `nacre verify` checks an existing receipt. Checkpoints are persisted only when requested.

## Resource limits and efficiency

Parser limits, worker bounds, bounded waits/exponents, adapter row/timeout limits and a 10,000-row join cap prevent several accidental excesses. They do not impose a comprehensive memory/CPU sandbox. Copying snapshots and canonical hashing add overhead; table join is a bounded nested-loop implementation. More workers do not imply faster CPU-bound work. Historical prototype timings are specific to their workstation workloads. The public release does not claim a general performance advantage; its acceptance evidence tests correctness and installation on the recorded platforms.

Deferred features include remote scheduling, streaming/reactivity, deterministic effect ordering without dependencies, transactional checkpoints across processes, automatic recovery of ambiguous commits and forcible interruption of arbitrary adapters.

## Public workspaces and optional MCP

The current working directory is the default workspace for the CLI and embedding API. `--workspace` selects another directory. All generated artifacts stay under the selected workspace outputs, and include paths must remain inside the workspace. The optional MCP process uses its working directory or `NACRE_WORKSPACE`; installing Nacre does not change client configurations. Basic language execution does not import the optional SDK or require any AI model.
