# Source provenance and licensing scope

Nacre-11 began as an operator-directed, AI-assisted programming-language engineering experiment. The public release adapts that existing implementation while preserving its independent grammar and execution semantics. The release was prepared with the operator's explicit authorization to publish the project.

The reviewed portable language modules implement their own parser, contracts, expressions and scheduler using Python's standard library. This source review found no vendored third-party library implementation or third-party copyright notice inside the original language modules/tests. Established algorithms and language ideas are acknowledged as prior art; this is not a claim of universal novelty or proof about the origin of every possible similar code fragment.

The project's MIT license applies to the original Nacre code, examples and documentation contributed to this release. Separately installed GENESIS projects, libraries, database drivers, engines, MCP dependencies and bundled runtime components retain their own ownership and license terms. They are not relicensed by a bridge or a JSON representation.

The public tree excludes private integration configuration, unrelated repository source, application datasets and developer environments. Release validation records the source commit and artifact digests. See [Third-party notices](THIRD-PARTY-NOTICES.md), [Contributing](CONTRIBUTING.md) and the release manifest when extending or redistributing the project.
