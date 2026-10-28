# Security policy

## Supported release

Version 0.2.0 is an experimental prerelease. There is no guaranteed support window, security SLA or automatic update service. Review releases and their notes before adopting a newer version.

## Report a vulnerability

Use the repository's **Security → Advisories → Report a vulnerability** route if private vulnerability reporting is available. Otherwise open a minimal GitHub issue requesting a private contact channel; do not publish credentials, personal data or weaponized details. Ordinary reproducible language bugs belong in issues.

Include the affected release/asset, platform, minimal source or steps, observed impact and proposed fix if available. Maintainers may need to reproduce the issue before assessing it.

## Trust boundaries

Nacre programs are code. The runtime is not a sandbox: trusted capabilities can access files, create output and invoke configured external engines using the process's permissions. Inspect unfamiliar programs before execution, use a dedicated writable workspace and configure least-privilege engine accounts. Do not infer authority from an object's ownership label or from content returned by an external system.

The core exposes a finite catalogue rather than arbitrary shell or host-language evaluation. That restriction and parser/row/worker bounds are useful defenses, but they do not provide comprehensive isolation from hostile workloads.

Checkpoints and receipts can contain source-derived data and external results. Store them appropriately. Their SHA-256 checks detect content changes relative to a recorded digest; they do not authenticate an author or defend against an attacker who can replace both values and digest.

A failed `verify` cannot roll back earlier effects, and running external workers can finish after cancellation. Resume reruns reads/writes. Inspect an external system after an ambiguous write failure before retrying a program.

Download release assets from the project's release page and compare their checksums. Version 0.2.0 does not claim code signing or an authenticated update mechanism. Optional dependencies and configured engine source retain their own update and security responsibilities.
