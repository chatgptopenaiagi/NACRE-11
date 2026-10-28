# Nacre-11 0.2.0

Experimental release of optional mathematical composition through the independent Octave Courier 0.1 public API. The original Nacre syntax, checked immutable graph, postconditions and portable core remain compatible with v0.1 programs.

Install the Nacre wheel and separately downloaded Courier wheel, provide GNU Octave, then run `nacre run examples/optional/octave-matrix.nac --receipt`. It selects a matrix-product contract, executes a real Octave process, checks shape and an independent rational reference, and emits `[[19,22],[43,50]]`. See [Numerical capabilities](NUMERICAL-CAPABILITIES.md) for exact commands and dependencies.

New contracts cover product/solve/inverse, QR, symmetric-real eigenvalues, polynomial evaluation, least-squares regression, Fourier transforms and descriptive statistics. Fixed integral/root/ODE, signal and optimization demonstrations plus sine PNG export are explicitly bounded examples. Optional SymPy transforms exact univariate rational polynomials before labeled binary64 evaluation. Unsupported domains are rejected.

Runtime identity, input hashes, independent numerical checks and artifact checks are recorded separately. Historical repository evidence does not certify a current workload. Selection is bounded to implemented providers and does not promise optimal costs or arbitrary compatibility.

Distributions include a wheel, source distribution, source/examples archives and real Windows/Linux x86_64 executable bundles. The release manifest binds exact source commits, artifact hashes, build tools and executed artifact acceptance. Explicitly Courier-inclusive bundles contain its public Python bridge; GNU Octave is never bundled. SymPy and MCP remain optional Python-environment integrations. The Linux native bundle has glibc baseline2.43; use the wheel on otherwise compatible older systems.

The portable v0.1 examples remain supported. Changed source/contract identities intentionally invalidate old checkpoints. No native Nacre machine-code compilation, arbitrary user Octave script dispatch, general complex/decimal numerical transport, distributed atomicity or performance superiority is claimed. Read [Known limitations](KNOWN-LIMITATIONS.md) before using this experimental release.