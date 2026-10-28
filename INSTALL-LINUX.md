# Install on Linux

## Linux x86_64 bundled distribution

Download `Nacre-11-0.2.0-linux-x86_64.tar.gz` and the checksum manifest from the [v0.2.0 release](https://github.com/chatgptopenaiagi/NACRE-11/releases/tag/v0.2.0). Verify the archive before extracting it into a new folder:

```shell
sha256sum Nacre-11-0.2.0-linux-x86_64.tar.gz
mkdir nacre11
tar -xzf Nacre-11-0.2.0-linux-x86_64.tar.gz -C nacre11
cd nacre11/Nacre-11-0.2.0-linux-x86_64
./nacre --help
./nacre --version
./nacre run examples/hello.nac
```

The official v0.2.0 Linux release asset is built and tested in genuine Linux x86_64, with a bundled Python 3.14.4 runtime. Its build environment is Ubuntu 26.04 and its glibc baseline is **2.43**. CI-generated and local builds can use a different interpreter and system ABI; their bundled `BUILD-INFO.json` records the actual environment. Do not infer ABI compatibility from the filename alone. The official asset is not a universal Linux binary. On older glibc systems, use the wheel with a compatible locally installed Python, or build the executable on that system. musl-based distributions are not covered by this binary.

Keep the extracted distribution together. A separate Python installation is not required for the bundled executable, but system ABI compatibility still matters. No root installation or system PATH change is required; invoke `nacre` by its extracted path.

## Python wheel

The same pure-Python wheel is used on Windows and Linux. A separate Linux wheel is unnecessary for the core:

```shell
python3 -m venv .venv
.venv/bin/python -m pip install ./nacre11-0.2.0-py3-none-any.whl
.venv/bin/nacre --version
.venv/bin/nacre run examples/hello.nac
```

The system's Python installation must support virtual environments. Examples come from the examples archive, source tree or standalone package. The core requires no third-party Python package at runtime. Package metadata requires Python 3.10 or later; the release record distinguishes actual tested versions from this compatibility declaration.

## Source installation

The source distribution includes `pyproject.toml` and `src/nacre/`:

```shell
python3 -m venv .venv
.venv/bin/python -m pip install ./nacre11-0.2.0.tar.gz
.venv/bin/nacre --version
```

Building from source may require downloading the declared build backend. The wheel path avoids that build step.

## Other architectures

No native ARM64 or macOS standalone build is claimed for v0.2.0. The wheel contains no architecture-specific extension, but its tag alone does not establish runtime testing on ARM64, alternative Python implementations or every Linux distribution. Consult the release verification manifest for tested environments.

For optional MCP, install the wheel with `[mcp]` and run `python -m nacre.mcp_server` using that environment. External database/application bridges are separately configured; see [Interoperability](INTEROPERABILITY.md).
