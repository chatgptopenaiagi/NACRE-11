# Install on Windows

## Standalone x64 package

Download `Nacre-11-0.2.0-windows-x86_64.zip` and the release checksum manifest from the [v0.2.0 release](https://github.com/chatgptopenaiagi/NACRE-11/releases/tag/v0.2.0). Compare the ZIP's SHA-256 with the published manifest:

```powershell
Get-FileHash .\Nacre-11-0.2.0-windows-x86_64.zip -Algorithm SHA256
Expand-Archive .\Nacre-11-0.2.0-windows-x86_64.zip -DestinationPath .\nacre11
Set-Location .\nacre11\Nacre-11-0.2.0-windows-x86_64
.\nacre.exe --help
.\nacre.exe --version
.\nacre.exe run .\examples\hello.nac
```

Keep the extracted distribution together. The official v0.2.0 Windows release asset includes a Python 3.14.7 runtime and native runtime libraries, so a separate Python installation is not required. CI-generated and local builds can use a different Python version; inspect their bundled `BUILD-INFO.json` for the actual toolchain. The executable is a bundled-interpreter application, not a compiler that generates native Nacre machine code. Build and component details accompany the release artifacts.

Call the executable by its full path from any writable working directory. You may add its containing directory to your own PATH if desired; no installer, global environment change, Codex installation or administrator privilege is required by Nacre.

Unsigned binaries may receive operating-system reputation warnings. Version 0.2.0 does not claim an Authenticode signature. Obtain the archive from the project's release page and check its digest.

## Python wheel

Use a supported Python installation and download `nacre11-0.2.0-py3-none-any.whl`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .\nacre11-0.2.0-py3-none-any.whl
.\.venv\Scripts\nacre.exe --version
.\.venv\Scripts\nacre.exe run .\examples\hello.nac
```

Examples come from the source/examples archive or standalone package. The wheel installs the core and console entry point. It has no required external runtime packages. Metadata declares Python 3.10 or later; the release record lists tested interpreter versions.

If PowerShell script activation is disabled, the explicit executable paths above work without changing your execution policy.

## Optional MCP

MCP is excluded from the minimal core dependencies. To install the downloaded wheel with its optional SDK dependency, use:

```powershell
.\.venv\Scripts\python.exe -m pip install ".\nacre11-0.2.0-py3-none-any.whl[mcp]"
.\.venv\Scripts\python.exe -m nacre.mcp_server
```

That command starts a stdio server and waits for an MCP client. Optional dependency installation may need internet access. Do not send ordinary terminal output into an MCP protocol stream. See [Interoperability](INTEROPERABILITY.md) for configuration.
