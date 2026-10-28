# Contributing to Nacre-11

Nacre-11 is experimental. Small, reproducible changes that preserve the documented language are easier to evaluate than broad redesigns.

## Report a bug or request a feature

Use [GitHub issues](https://github.com/chatgptopenaiagi/NACRE-11/issues). Include the Nacre version, operating system, Python version or standalone asset name, minimal `.nac` source, exact command, expected behavior, actual JSON error and exit code. State whether optional integrations were configured. Remove credentials, private paths and confidential records.

For a feature request, describe the problem and a small example. Separate desired syntax from an implementation proposal, and identify the current limitation it addresses. Security-sensitive reports follow [SECURITY.md](SECURITY.md).

## Develop and test

Clone this public repository and use a virtual environment:

```shell
python -m venv .venv
# Activate the environment using your platform's normal command.
python -m pip install -e .
python -m unittest discover -s tests -v
```

The portable tests must not depend on private GENESIS trees, databases or installed Office software. Optional bridge tests use controlled fixtures or an explicitly configured integration environment and must identify that scope. Public CI exercises the core on maintained Windows and Linux runners.

Every published `.nac` example belongs in `examples/manifest.json`. Record expected failures honestly, and make artifact-producing acceptance tests use fresh workspaces. Regression tests should establish behavior at a meaningful boundary, rather than merely duplicate implementation lines.

To build wheel and source distributions, install the declared build tools in an isolated environment and run `python -m build`. Standalone builds must run on the target operating system; see the release scripts and artifact manifests for the exact toolchain. A Windows executable is not a Linux build.

## Code and review conventions

Use four-space indentation and familiar Python standard-library facilities. Keep parser, contracts, scheduler and adapter boundaries explicit. Add structured `NacreError` diagnostics with useful source locations. Never add arbitrary host-language evaluation or shell invocation through a language program. Preserve the full-graph check before effects, immutable value semantics, retry restrictions and output path boundaries.

For new capabilities, document input/output types, optional arguments, effect, resource, retry policy, implementation binding and actual verification scope. Do not label a descriptor as proof of a live integration. Include independent readback or result checks where practical.

Open a focused pull request describing the concrete problem, resulting behavior, relevant tests and known limits. Include documentation changes when behavior changes. Do not include credentials, local environments, generated executables, bulk private evidence or unrelated source.

## Versioning and licensing

Use semantic versioning as a guide. During 0.x, incompatible experimental changes may occur in a minor version, but must be recorded in the changelog and release notes. A public release tag identifies its tested source commit; do not replace released artifacts in place without an explicit correction record.

Contribute only material you have the right to submit under the project's MIT license. Keep third-party notices intact and identify any new dependency or copied material in the pull request. No contribution transfers ownership of separately installed engines.
