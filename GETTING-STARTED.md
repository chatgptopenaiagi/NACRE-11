# Getting started with Nacre-11

Use a standalone distribution for your platform, or install the downloaded wheel in a Python virtual environment. The core does not require an account, an AI model, a database server or an internet connection after the artifact has been obtained.

## Your first program

Create a writable folder and save this UTF-8 text as `answer.nac`:

```nacre
let answer: Integer = 6 * 7;
verify answer == 42;
emit answer;
```

Open a terminal in that folder and run:

```shell
nacre check answer.nac
nacre run answer.nac
```

For an extracted Windows package, use `.\nacre.exe` if it is in the current folder. For an extracted Linux package, use `./nacre`. You may call the executable by its full path from a different working directory.

`check` parses the whole program and checks its types, capability arguments and dependencies without invoking engines. `run` performs those checks and executes the resulting graph. A successful run returns JSON containing:

```json
{"status": "passed", "emitted": [42]}
```

The actual result also includes diagnostics, events and binding values. `emit` appends a language value to `emitted`; it does not print an unstructured line.

## Useful commands

```shell
nacre --help
nacre --version
nacre capabilities
nacre compile answer.nac --output answer-ir.json
nacre run answer.nac --workers 2 --receipt
```

`compile` writes checked JSON graph IR; saved IR is not currently an executable input format. `--receipt` creates a new receipt in `outputs/runs/` and returns its path. Use the actual returned path:

```shell
nacre verify outputs/runs/RETURNED-UUID.json
```

Receipt verification checks the saved result digest and referenced artifact bytes. Malformed receipts, including non-finite JSON numbers, produce a structured RECEIPT diagnostic. Verification does not rerun the program, authenticate an external service or prove arbitrary mathematics.

## Working directories and files

The current directory is the default workspace. `--workspace DIR` selects another one for `check`, `compile`, `run` and receipt verification. Outputs belong under that workspace's `outputs/` directory, rather than inside the installed package. Includes must stay within the selected workspace.

File-generating examples refuse to overwrite an existing JSON output. Use a new workspace when rerunning those examples, or choose a new output filename in your own program. The SQLite example uses a project-local database and a table with an ownership marker.

## Reading errors

A check or setup error normally exits with code 2; a runtime or postcondition failure exits with code 1. Successful commands exit with code 0. Errors carry a category, message and available source/binding location. Expected-failure examples demonstrate these differences:

```shell
nacre check examples/invalid-type.nac
nacre run examples/arithmetic-error.nac
nacre run examples/failed-verification.nac
```

No `try/catch` syntax is implemented. Explicit `retry` applies only to retry-safe capabilities, and never automatically to writes. See [Examples](EXAMPLES.md) and [Runtime architecture](RUNTIME-ARCHITECTURE.md).
