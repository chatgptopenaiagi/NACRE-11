# Third-party notices

The [MIT license](LICENSE) covers Nacre-11's original source and documentation. It does not relicense Python, SQLite, optional engines, the MCP SDK or other separately supplied software.

## Source distribution and wheel

The portable core is implemented with Python's standard library and declares no required third-party runtime package. The wheel contains Nacre's Python modules; it does not contain the Python interpreter, database servers, GENESIS projects or other repositories. The optional `mcp` extra installs its own independently licensed dependencies through the Python package manager.

Optional GENESIS bridges refer to software users obtain and configure separately. Importing or calling an external package is not a grant to redistribute its code. No external repository source, application data, private configuration or credentials are part of the public Nacre source distribution.

## Standalone executable distributions

Standalone packages bundle a Python interpreter, standard-library components and selected native runtime libraries. They retain their original licenses. The package's `licenses/` materials and artifact manifest record notices collected from the actual target build environment. Preserve those materials when redistributing an executable package. The interpreter is bundled without changes to Python's source code; Nacre supplies application code and a packaging launcher.

The Python Software Foundation license requires retained notices, and Python incorporates software with additional notices. See the official [Python history and license](https://docs.python.org/3/license.html). SQLite and other bundled native library terms remain component-specific; inspect the included target package notices rather than applying Nacre's MIT license to them.

PyInstaller is used as a build tool. Its published license includes an exception permitting distribution of generated application bundles under the application's chosen terms while preserving dependency obligations. See the official [PyInstaller license](https://pyinstaller.org/en/stable/license.html). Nacre does not modify or relicense PyInstaller itself.

Build tools installed to create a wheel or executable are not automatically runtime contents of every artifact. The target-specific inventory and notices describe what was actually distributed; a source-only archive and a bundled-interpreter executable have different component sets.
