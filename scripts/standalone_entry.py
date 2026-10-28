"""PyInstaller entry point; this bundles a Python interpreter, not Nacre machine code."""
from nacre.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
