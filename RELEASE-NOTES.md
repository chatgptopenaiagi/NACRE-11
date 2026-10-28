# Nacre-11 0.1.0

Initial **experimental prerelease** of Nacre-11: a language for checked, verified composition of selected software capabilities.

## Start here

Download an asset for your platform from [the v0.1.0 release](https://github.com/chatgptopenaiagi/NACRE-11/releases/tag/v0.1.0), verify its SHA-256, and follow [Windows](INSTALL-WINDOWS.md) or [Linux](INSTALL-LINUX.md) instructions. Try `examples/hello.nac`, then the arithmetic, graph, concurrency, SQLite and output-verification examples.

## Distribution formats

- Windows x86_64 ZIP with `nacre.exe` and a bundled Python runtime.
- Genuine Linux x86_64 executable distribution, built with glibc 2.43. Older glibc systems should use the wheel or rebuild locally.
- A shared `nacre11-0.1.0-py3-none-any.whl`, with no required third-party core runtime dependencies.
- Python source distribution, source and example archives, release manifest and SHA-256 checksums.

Standalone executables bundle the Python interpreter and libraries. They do not compile Nacre programs to native machine code. Optional MCP dependencies and external GENESIS projects are not required for basic execution and are not silently installed.

## Language behavior

The release preserves the prototype's independent syntax and checked immutable graph model. Local arithmetic/statistics, records/lists, typed table transforms, artifact integrity, SQLite, modules, structured diagnostics, explicit retry policy and pure checkpoint reuse are implemented. Optional engine routes activate through explicit configuration.

Examples include expected type, arithmetic and verification failures, which are only accepted when their documented diagnostic and exit code occur. Optional engine examples are separately gated and are not counted as portable live-engine successes.

## Verification scope

Release validation checks extracted artifacts and clean wheel installations separately from the source checkout. The public release metadata and artifact manifest identify the source commit, target platforms, build toolchains, hashes and actual results. Historical prototype results of 103 tests, 19 integration acceptance invocations and 26 timing cases belong to the original workstation experiment; they are not a claim that those external engines exist on a fresh user's machine.

Read [Known limitations](KNOWN-LIMITATIONS.md) before relying on external effects, resume or concurrency. No distributed atomicity, exactly-once effects, universal interoperability, native ARM64 artifact or performance superiority is claimed.
