"""Build source, wheel and real-platform bundled-interpreter distributions.

Install requirements-build.txt in an isolated environment first. Run on each
target OS; PyInstaller is not a cross-compiler. No installer or global setting
is changed by this script. Build provenance is recorded inside each bundle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
PUBLIC_DOCS_EXCLUDED = {"FINAL-RELEASE-REPORT.md", "SESSION-HANDOFF.md"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, log):
    with log.open("wb") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError("Build failed; inspect " + str(log))


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def public_files():
    files = [p for p in ROOT.glob("*.md") if p.name not in PUBLIC_DOCS_EXCLUDED]
    files += [ROOT / name for name in ("LICENSE", "pyproject.toml", "MANIFEST.in", "requirements-build.txt", "requirements-build-linux.txt") if (ROOT / name).is_file()]
    for name in ("src", "tests", "examples", "scripts", "packaging", ".github"):
        directory = ROOT / name
        if directory.is_dir():
            files.extend(p for p in directory.rglob("*") if p.is_file()
                         and "__pycache__" not in p.parts and not any(part.endswith(".egg-info") for part in p.parts)
                         and p.suffix not in (".pyc", ".pyo"))
    return sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())


def provenance(commit, kind):
    files = public_files()
    return {
        "schema_version": "1.0", "language": "Nacre-11", "version": VERSION,
        "kind": kind, "source_commit": commit,
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system(), "architecture": platform.machine(),
        "python": platform.python_version(), "python_implementation": platform.python_implementation(),
        "libc": list(platform.libc_ver()) if sys.platform.startswith("linux") else None,
        "toolchain": {name: package_version(name) for name in ("PyInstaller", "build", "setuptools", "wheel")},
        "source_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in files},
        "packaging": "Bundled Python interpreter and Nacre bytecode; not native Nacre machine-code compilation" if kind == "standalone" else "Pure Python source/runtime with no mandatory third-party dependencies",
        "reproducibility": "Source identity, pinned build tools and artifact hashes are recorded. Bit-identical binary rebuilds are not asserted.",
    }


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_commit(commit):
    if commit == "UNCOMMITTED" or not (ROOT / ".git").exists():
        return
    actual = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if actual != commit:
        raise RuntimeError("The requested release commit is not the source tree HEAD")
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    if status.strip():
        raise RuntimeError("Release source tree must be clean before a commit-bound build")


def runtime_licenses(destination):
    destination.mkdir(parents=True)
    copied = []
    candidates = []
    pyinstaller = importlib.metadata.distribution("PyInstaller")
    for entry in pyinstaller.files or []:
        if Path(str(entry)).name == "COPYING.txt":
            candidates.append((Path(pyinstaller.locate_file(entry)), "PYINSTALLER-COPYING.txt"))
    if os.name == "nt":
        base = Path(sys.base_prefix)
        candidates += [(base / "LICENSE_PYTHON.txt", "PYTHON-LICENSE.txt"), (base / "LICENSE.txt", "PYTHON-LICENSE.txt")]
        for p in (base / "Library/share/doc").rglob("*"):
            if p.is_file() and re.search(r"LICENSE|COPYING|copyright", p.name, re.IGNORECASE) and any(part in ("zlib", "xz", "expat") for part in p.parts):
                candidates.append((p, "-".join(p.relative_to(base / "Library/share/doc").parts)))
    else:
        for name in ("python3.14", "libpython3.14-stdlib", "libsqlite3-0", "zlib1g", "libssl3t64", "libbz2-1.0", "liblzma5", "libffi8", "libexpat1", "libgcc-s1", "libstdc++6"):
            candidates.append((Path("/usr/share/doc") / name / "copyright", name + "-copyright.txt"))
        # Other interpreter versions used by CI may ship their notice here.
        for p in Path("/usr/share/doc").glob("python3.*/copyright"):
            candidates.append((p, p.parent.name + "-copyright.txt"))
        for p in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
            candidates.append((p, "PYTHON-LICENSE.txt"))
    custom = ROOT / "packaging/runtime-licenses"
    if custom.is_dir():
        candidates.extend((p, p.name) for p in custom.iterdir() if p.is_file())
    for source, name in candidates:
        if source.is_file() and name not in copied:
            shutil.copyfile(source, destination / name)
            copied.append(name)
    if not any("python" in name.lower() for name in copied):
        raise RuntimeError("Actual bundled Python runtime license is required")
    if "PYINSTALLER-COPYING.txt" not in copied:
        raise RuntimeError("Actual PyInstaller copyright/bootloader exception notice is required")
    write_json(destination / "NOTICE-MANIFEST.json", {"scope": "License/copyright notices for the actual bundled interpreter and selected native dependencies; Nacre LICENSE applies only to Nacre source", "files": {name: digest(destination / name) for name in sorted(copied)}})
    return copied


def archive_directory(directory, path):
    files = sorted((p for p in directory.rglob("*") if p.is_file()), key=lambda p: p.relative_to(directory.parent).as_posix())
    if path.suffix == ".zip":
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for p in files:
                archive.write(p, p.relative_to(directory.parent).as_posix())
    else:
        with tarfile.open(path, "x:gz") as archive:
            for p in files:
                archive.add(p, arcname=p.relative_to(directory.parent).as_posix(), recursive=False)


def build_standalone(output, commit, token):
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("This release recipe has verified x86_64 targets only")
    target = "windows-x86_64" if os.name == "nt" else "linux-x86_64" if sys.platform.startswith("linux") else None
    if target is None:
        raise RuntimeError("Standalone target requires Windows or GNU/Linux")
    work = ROOT / "outputs" / ("standalone-build-" + target + "-" + token)
    work.mkdir(parents=True)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "nacre",
               "--paths", str(ROOT / "src"), "--distpath", str(work / "dist"), "--workpath", str(work / "work"),
               "--specpath", str(work), "--exclude-module", "nacre.mcp_server", "--exclude-module", "mcp",
               "--exclude-module", "genesis9", "--exclude-module", "genesis10", str(ROOT / "scripts/standalone_entry.py")]
    run(command, work / "pyinstaller.log")
    bundle = work / ("Nacre-11-" + VERSION + "-" + target)
    shutil.copytree(work / "dist/nacre", bundle)
    for p in ROOT.glob("*.md"):
        if p.name not in PUBLIC_DOCS_EXCLUDED:
            shutil.copyfile(p, bundle / p.name)
    for name in ("LICENSE",):
        shutil.copyfile(ROOT / name, bundle / name)
    shutil.copytree(ROOT / "examples", bundle / "examples")
    runtime_licenses(bundle / "licenses")
    info = provenance(commit, "standalone")
    info["target"] = target
    write_json(bundle / "BUILD-INFO.json", info)
    name = bundle.name + (".zip" if os.name == "nt" else ".tar.gz")
    destination = output / name
    archive_directory(bundle, destination)
    return [destination]


def build_python(output, commit, token):
    log = ROOT / "evidence" / ("python-package-build-" + token + ".log")
    log.parent.mkdir(exist_ok=True)
    # Default build creates the wheel from the generated sdist, verifying that
    # the source distribution is sufficient for the wheel build.
    run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)], log)
    return [output / ("nacre11-" + VERSION + suffix) for suffix in ("-py3-none-any.whl", ".tar.gz")]


def build_archives(output, commit, token):
    source_zip = output / ("Nacre-11-" + VERSION + "-source.zip")
    examples_zip = output / ("Nacre-11-" + VERSION + "-examples.zip")
    with zipfile.ZipFile(source_zip, "x", zipfile.ZIP_DEFLATED) as archive:
        for p in public_files():
            archive.write(p, "Nacre-11-" + VERSION + "/" + p.relative_to(ROOT).as_posix())
        archive.writestr("Nacre-11-" + VERSION + "/BUILD-INFO.json", json.dumps(provenance(commit, "source"), indent=2))
    with zipfile.ZipFile(examples_zip, "x", zipfile.ZIP_DEFLATED) as archive:
        for p in sorted((ROOT / "examples").rglob("*")):
            if p.is_file():
                archive.write(p, p.relative_to(ROOT).as_posix())
        archive.write(ROOT / "LICENSE", "LICENSE")
    return [source_zip, examples_zip]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("python", "standalone", "archives"), required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--source-commit", required=True, help="Exact release source commit, or UNCOMMITTED for an explicitly provisional build")
    args = parser.parse_args()
    if args.source_commit != "UNCOMMITTED" and not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be a 40-digit Git SHA or UNCOMMITTED")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = time.perf_counter()
    try:
        verify_commit(args.source_commit)
        artifacts = {"python": build_python, "standalone": build_standalone, "archives": build_archives}[args.kind](output, args.source_commit, token)
        record = {"status": "BUILT_NOT_YET_ACCEPTED", "checked_utc": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": round(time.perf_counter() - started, 3),
                  "provenance": provenance(args.source_commit, args.kind), "artifacts": [{"filename": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in artifacts]}
    except Exception as exc:
        record = {"status": "FAILED", "checked_utc": datetime.now(timezone.utc).isoformat(), "kind": args.kind, "error": str(exc), "source_commit": args.source_commit}
        (ROOT / "evidence").mkdir(exist_ok=True)
        write_json(ROOT / "evidence" / ("build-" + args.kind + "-" + platform.system().lower() + "-" + token + ".json"), record)
        raise
    (ROOT / "evidence").mkdir(exist_ok=True)
    receipt = ROOT / "evidence" / ("build-" + args.kind + "-" + platform.system().lower() + "-" + token + ".json")
    write_json(receipt, record)
    print(json.dumps({"receipt": str(receipt), "status": record["status"], "artifacts": record["artifacts"]}, indent=2))


if __name__ == "__main__":
    main()
