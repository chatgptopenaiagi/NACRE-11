# Research roadmap

These are possible development directions, not implemented guarantees or delivery promises.

1. Improve schema propagation through record fields and table transforms while preserving predictable gradual checks.
2. Expand portable mathematical and database capabilities only when a bounded interface, clear ownership rules and independent tests exist.
3. Replace selected materialized nested-loop operations when measured workloads justify a more efficient algorithm.
4. Study durable reconciliation after ambiguous external commits; retain explicit limits until crash experiments establish stronger behavior.
5. Improve diagnostics, editor support, source maps and examples using real user feedback.
6. Test additional Python runtimes, older Linux ABI baselines and genuine ARM64 environments before declaring support.
7. Explore stable extension contracts and authenticated receipt provenance without introducing arbitrary evaluation paths.

Near-term contributions should favor reproducible defects, installation failures, clear examples and test coverage. Language redesigns should explain the concrete composition problem they solve and preserve an executable prototype throughout the work.
