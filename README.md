# Nacre-11

**An experimental programming language for composing and verifying capabilities across independent software systems.**

Nacre-11 turns typed, immutable bindings and named capability calls into a checked dependency graph. Its own parser and expression interpreter execute `.nac` programs. Independent nodes may run concurrently; explicit postconditions check the result. Ordinary execution needs no AI model, Codex installation, database server or GENESIS project.

```nacre
let answer: Integer = 6 * 7;
verify answer == 42;
emit answer;
```

Run it with `nacre run answer.nac`. The JSON result has `"status": "passed"` and `"emitted": [42]`.

## Get version 0.1.0

Download assets and their checksums from the [v0.1.0 experimental release](https://github.com/chatgptopenaiagi/NACRE-11/releases/tag/v0.1.0). This is a prerelease intended for investigation and feedback.

| Asset | Use |
|---|---|
| `Nacre-11-0.1.0-windows-x86_64.zip` | Extract and run `nacre.exe`; includes a Python runtime |
| `Nacre-11-0.1.0-linux-x86_64.tar.gz` | Linux x86_64 bundled runtime; glibc 2.43 or later |
| `nacre11-0.1.0-py3-none-any.whl` | Install into an existing compatible Python environment on Windows or Linux |
| `nacre11-0.1.0.tar.gz` | Python source distribution with build metadata |
| Source and examples archives | Read, build and experiment with the language |

No PyPI publication is required: install the downloaded wheel directly.

```shell
python -m venv .venv
# Activate .venv using your platform's normal command.
python -m pip install ./nacre11-0.1.0-py3-none-any.whl
nacre --version
nacre run examples/hello.nac
```

Download the examples archive or source tree for that last command. The wheel installs the runtime and CLI; examples also ship beside the standalone executables. See [Getting started](GETTING-STARTED.md), [Windows installation](INSTALL-WINDOWS.md) and [Linux installation](INSTALL-LINUX.md).

## What is implemented

- An independent syntax, lexer, Pratt parser, type checks and inspectable graph IR.
- Immutable values, forward references, dependency-aware scheduling and source-order emissions.
- Arithmetic, lists, records, explicit object identities, typed tables and data transformations.
- Local SQLite queries, schema inspection and an ownership-marked demonstration transaction.
- Structured diagnostics, explicit postconditions, controlled retries and pure-node checkpoint reuse.
- Output artifacts and execution receipts with integrity checks.
- Optional configured GENESIS bridges for selected symbolic, database, application and repository operations.
- An optional five-tool stdio MCP interface using the same compiler and runtime.

```nacre
task left: Number <- core.wait(value=20, milliseconds=100);
task right: Number <- core.wait(value=22, milliseconds=100);
let total: Number = left + right;
verify total == 42;
emit total;
```

The waits are independent. Their shared consumer runs after both values are available. This demonstrates scheduling; it is not a claim that threads accelerate every workload.

## The model

```text
.nac source → lexer/parser → names/types/contracts/DAG checks
            → checked graph IR → bounded local interpreter
                               → portable capabilities
                               → configured optional adapters
            → postconditions → emitted values and receipts
```

Nacre is a small composition language. Python and Go are general-purpose languages; either can implement orchestration with suitable libraries. Nacre makes a selected graph, its capability contracts and its verification expressions explicit in source. The implementation is written in Python. `nacre compile` produces JSON graph IR, and the standalone executable bundles an interpreter; neither is a native Nacre machine-code compiler. No universal interoperability or performance superiority is claimed.

## Platforms and optional engines

The core wheel has no required third-party runtime dependencies. Package metadata requires Python 3.10 or later; the release verification record identifies the actual versions tested. A `py3-none-any` wheel is shared across compatible operating systems: it contains Python code, not separate Windows and Linux native binaries. That tag is not an assertion that every Python implementation, OS or CPU has been tested.

The standalone Linux build is produced in a genuine Linux environment. Its glibc baseline is narrower than the wheel's installation possibilities. Native ARM64 and macOS standalone builds are not included in this release.

The portable core does not need GENESIS-8/9/10/11, SQL Server, PostgreSQL, MariaDB, Joomla, LibreOffice or SymPy. Optional operations require explicit configuration and compatible software. Discovery reports configuration, not proof that a remote service is running. See [Interoperability](INTEROPERABILITY.md).

## Explore and contribute

Start with [Examples](EXAMPLES.md), then the [Language guide](LANGUAGE-GUIDE.md), [Language reference](LANGUAGE-REFERENCE.md) and [Syntax](SYNTAX.md). The [compiler](COMPILER-ARCHITECTURE.md) and [runtime](RUNTIME-ARCHITECTURE.md) documents describe implementation boundaries.

Read [Known limitations](KNOWN-LIMITATIONS.md), [Release notes](RELEASE-NOTES.md), [Security](SECURITY.md) and [Contributing](CONTRIBUTING.md) before running unfamiliar programs or proposing changes. Report reproducible bugs through [GitHub issues](https://github.com/chatgptopenaiagi/NACRE-11/issues). The [roadmap](ROADMAP.md) lists research directions rather than promised features.

Nacre's original code and documentation are provided under the [MIT license](LICENSE). Bundled runtimes and optional dependencies keep their own licenses; see [Third-party notices](THIRD-PARTY-NOTICES.md) and [Provenance](PROVENANCE.md).
