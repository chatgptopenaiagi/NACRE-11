# Optional numerical capabilities

Nacre0.2.0 composes an independently installed Octave Courier0.1 package and GNU Octave>=7. Ordinary Nacre programs need neither. Install downloaded release wheels in a compatible environment; Courier is not claimed to be on PyPI:

```shell
python -m venv .venv
.venv/bin/python -m pip install ./nacre11-0.2.0-py3-none-any.whl ./octave_courier-0.1.0-py3-none-any.whl
.venv/bin/nacre run examples/optional/octave-matrix.nac --receipt
```

On Windows use `.venv\Scripts\python.exe` and `.venv\Scripts\nacre.exe`. Courier resolves `OCTAVE_EXECUTABLE`, PATH, then bounded standard Windows locations. Invalid explicit overrides fail. Programs need no hardcoded machine path. GNU Octave is installed separately; headless PNG export needs its gnuplot toolkit and working font/Ghostscript dependencies. The optional Courier-inclusive executable bundle supplies only the Python bridge. SymPy and MCP workflows use a Python environment with their separate optional dependencies; frozen distributions do not promise arbitrary package-plugin loading.

## Discovery and selection

`nacre capabilities` lists descriptors and dependency availability without executing a workload. `engine.discover()` returns operations, availability and optional configured GENESIS-10 metadata. `engine.select(operation=..., precision="binary64", shape=[rows,columns], output="json")` checks a supported contract and probes runtime identity. Precision, shape and output are optional; plot output uses `"png"`, and shape describes the left/design matrix. Selection has one implemented numerical candidate and explicitly sets `workload_verified=false`; actual invocation establishes operation-specific evidence. Supply the record as `engine=` to its matching numerical operation. Changed selected identities cannot silently fall back.

## Operations

| Capability | Required input | Output and independent check |
|---|---|---|
| `octave.multiply` | compatible nested lists `a`, `b` | `result`, `shape`; rational dot products |
| `octave.solve` | square `a`, matching `b` | `result`, `shape`; rational elimination |
| `octave.inverse` | square `a` | `result`, `shape`; rational inverse and residual |
| `octave.qr` | rectangular `a` | `q`, `r`; reconstruction, orthogonality, triangularity |
| `octave.eigen` | exactly symmetric real `a` | `values`, `vectors`; eigenpair residuals, orthogonality, trace |
| `octave.polynomial` | descending `coefficients`, flat `points` | `result`; rational Horner reference |
| `octave.regression` | design `x`, column response `y` | `coefficients`, `fitted`; rational least-squares reference |
| `octave.fft` | flat real `values` | `real`, `imaginary`; independent direct DFT |
| `octave.statistics` | matrix `values`, at least2 entries | descriptive sample statistics; stdlib reference |
| `octave.numerical_demo` | none | fixed integrals, sqrt2 root and decay ODE; analytical values |
| `octave.signal_demo` | none | fixed impulse FFT, FIR and convolution; expected arrays |
| `octave.optimization_demo` | none | fixed quadratic minimum; analytical value |
| `octave.plot` | none | unique sine PNG `artifact`; signature, dimensions, hash |

Each computation returns `verification.passed` and runtime/version, executable hash and input-digest provenance. Matrices accept finite real values, excluding booleans, NaN, infinity, complex inputs and decimal strings. Dimensions are1..64; rational solve/inverse references are bounded to16 rows and regression to16 coefficients. Vectors preserve row/column shape. Integers must fit+/-2^53; integer multiplication requires safe exact accumulation. General numerical transport is binary64, not exact decimal.

`matrix.verify(a=...,b=...,result=...,operation="matrix_product")` independently checks shape and values. Operation `"solve"` uses rational elimination. Default absolute and relative tolerances are each1e-10; explicit `atol`/`rtol` must be finite in[0,1e-4]. Additional worker operations use absolute1e-9 plus relative1e-8, with reciprocal condition>1e-10 for inverse/regression. Checks establish bounded numerical agreement for the actual inputs, not proof for all matrices.

`symbolic.polynomial(coefficients=[...],action="differentiate")` accepts1..17 bounded exact integers or rational/decimal strings. Actions are `identity`, `differentiate`, `integrate`; integration uses constant0. The result retains exact coefficients and labels their binary64 conversion. The numerical polynomial capability consumes the rounded list. Arbitrary symbolic expressions or source strings are not executed. See `examples/optional/symbolic-octave.nac`.

## Execution boundaries

Adapters call Courier public methods or its documented `run_script` on a fixed Nacre-owned packaged worker. JSON parameters carry data; they are never interpolated into executable source. Trusted local engines run with normal process permissions; this is not a sandbox.

Optional `timeout` defaults30 seconds and must lie in(0,120]. It applies separately to identity and workload children, not the whole graph. Missing engines, shape/domain errors, process failures and timeouts produce structured diagnostics. There is no silent retry or automatic repair. A later explicit valid call can demonstrate recovery.

The original graph determines dependencies and scheduling. Octave calls share one resource lock per runtime; independent non-Octave work may overlap. External numerical nodes rerun on resume. Post-graph `verify` cannot roll back earlier artifacts. PNG byte verification is distinct from visual inspection. Receipt validation checks saved-result and artifact integrity, not mathematical reexecution or authenticity.

Configured `NACRE_GENESIS10_ROOT` lets discovery read bounded historical repository metadata. Metadata never supplies executable routes. Missing/malformed records are reported; current engine identity and each operation's independent checks remain required. Unsupported domains/output requests fail rather than inventing a provider.
