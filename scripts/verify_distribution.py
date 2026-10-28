"""Build/install or extract a release artifact and test away from its source.

Source artifacts build with the existing release-tool interpreter, then install
into a new dependency-free runtime. Optional wheels are explicit, hash-recorded
inputs. This verifier never downloads dependencies.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_names(names):
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe archive member: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--kind", choices=("wheel", "standalone", "sdist", "source", "examples"), required=True)
    parser.add_argument("--examples", type=Path, default=Path(__file__).resolve().parents[1] / "examples")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-wheel", type=Path, help="Nacre wheel used to execute an examples-only archive")
    parser.add_argument("--dependency-wheel", type=Path, action="append", default=[], help="Optional dependency wheel; repeat as needed")
    parser.add_argument("--with-octave", action="store_true")
    parser.add_argument("--with-symbolic", action="store_true")
    args = parser.parse_args()
    if args.with_symbolic and not args.with_octave:
        parser.error("--with-symbolic requires --with-octave")
    if args.kind == "standalone" and (args.dependency_wheel or args.with_symbolic):
        parser.error("Standalone cannot install dependency wheels; SymPy is intentionally not bundled")
    if args.kind == "examples" and args.runtime_wheel is None:
        parser.error("--kind examples requires --runtime-wheel for actual example execution")
    artifact = args.artifact.resolve()
    examples = args.examples.resolve()
    driver = Path(__file__).with_name("release_acceptance.py").resolve()
    environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    record = {"checked_utc": datetime.now(timezone.utc).isoformat(), "artifact": artifact.name,
              "artifact_sha256": digest(artifact), "kind": args.kind,
              "host": platform.platform(), "architecture": platform.machine(), "status": "FAILED",
              "acceptance_driver_sha256": digest(driver), "dependencies_downloaded": False,
              "optional_execution": {"octave": args.with_octave, "symbolic": args.with_symbolic},
              "dependency_wheels": [{"filename": p.name, "sha256": digest(p)} for p in args.dependency_wheel]}

    def process(command, cwd, label, timeout=180):
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=environment,
                                capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        record[label] = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        if result.returncode:
            raise RuntimeError(label + " failed; see recorded stdout/stderr")
        return result

    try:
        with tempfile.TemporaryDirectory(prefix="nacre installed distribution-λ-") as temporary:
            root = Path(temporary).resolve()
            wheel = artifact if args.kind == "wheel" else None
            command = None
            if args.kind != "wheel":
                extracted = root / "extracted"
                extracted.mkdir()
                if artifact.suffix == ".zip":
                    with zipfile.ZipFile(artifact) as archive:
                        safe_names(archive.namelist())
                        if archive.testzip() is not None:
                            raise ValueError("ZIP CRC mismatch")
                        archive.extractall(extracted)
                else:
                    with tarfile.open(artifact) as archive:
                        safe_names(archive.getnames())
                        if any(m.issym() or m.islnk() or not (m.isfile() or m.isdir()) for m in archive.getmembers()):
                            raise ValueError("Links/devices are excluded from release archives")
                        archive.extractall(extracted)
                record["archive_paths_verified"] = True
                if args.kind == "standalone":
                    candidates = [p for p in extracted.rglob("nacre.exe" if os.name == "nt" else "nacre") if p.is_file()]
                    if len(candidates) != 1:
                        raise ValueError("Standalone executable missing or ambiguous")
                    executable = candidates[0]
                    examples = executable.parent / "examples"
                    notices = executable.parent / "licenses/NOTICE-MANIFEST.json"
                    if not (executable.parent / "LICENSE").is_file() or not notices.is_file():
                        raise ValueError("Runtime/Nacre license notices missing")
                    for name, expected in json.loads(notices.read_text(encoding="utf-8"))["files"].items():
                        if digest(notices.parent / name) != expected:
                            raise ValueError("Runtime license notice digest mismatch")
                    info = json.loads((executable.parent / "BUILD-INFO.json").read_text(encoding="utf-8"))
                    record["build_info"] = info
                    courier = info.get("optional_integrations", {}).get("octave_courier", {})
                    if args.with_octave and (courier.get("version") != "0.1.0" or courier.get("bundled") is not True):
                        raise ValueError("Mathematical standalone acceptance requires bundled public Courier 0.1.0")
                    command = [str(executable)]
                elif args.kind in ("sdist", "source"):
                    metadata = list(extracted.rglob("pyproject.toml"))
                    if len(metadata) != 1:
                        raise ValueError("Source build metadata missing or ambiguous")
                    source = metadata[0].parent
                    required = ["LICENSE", "README.md", "GETTING-STARTED.md", "examples/manifest.json", "MANIFEST.in",
                                "src/nacre/language.py", "src/nacre/octave_operations.m"]
                    if any(not (source / name).is_file() for name in required):
                        raise ValueError("Source archive incomplete")
                    record["source_metadata_complete"] = True
                    examples = source / "examples"
                    built = root / "rebuilt-wheels"
                    process([sys.executable, "-I", "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                             "--wheel-dir", built, source], root, "source_build")
                    wheels = list(built.glob("nacre11-*.whl"))
                    if len(wheels) != 1:
                        raise ValueError("Source artifact did not build exactly one Nacre wheel")
                    wheel = wheels[0]
                    record["rebuilt_wheel_sha256"] = digest(wheel)
                else:
                    manifests = list(extracted.rglob("manifest.json"))
                    if len(manifests) != 1:
                        raise ValueError("Examples manifest missing or ambiguous")
                    examples = manifests[0].parent
                    wheel = args.runtime_wheel.resolve()
                    record["runtime_wheel"] = {"filename": wheel.name, "sha256": digest(wheel)}
            if wheel is not None:
                venv.EnvBuilder(with_pip=True, clear=False).create(root / "venv")
                python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                process([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel,
                         *[p.resolve() for p in args.dependency_wheel]], root, "installation")
                process([python, "-I", "-m", "pip", "check"], root, "dependency_check")
                executable = root / "venv" / ("Scripts/nacre.exe" if os.name == "nt" else "bin/nacre")
                if not executable.is_file():
                    raise RuntimeError("Installed console entry point missing")
                command = [str(executable)]
                probe = process([python, "-I", "-c",
                    "import nacre,json,importlib.util; from pathlib import Path; print(json.dumps({'version':nacre.__version__, 'module':nacre.__file__, 'worker_present':Path(nacre.__file__).with_name('octave_operations.m').is_file(),'courier_present':importlib.util.find_spec('octave_courier') is not None,'sympy_present':importlib.util.find_spec('sympy') is not None}))"], root, "installed_import")
                imported = json.loads(probe.stdout)
                record["installed_import_version"] = imported["version"]
                if not imported["worker_present"]:
                    raise RuntimeError("Installed package is missing its owned numerical worker")
                if not args.dependency_wheel and (imported["courier_present"] or imported["sympy_present"]):
                    raise RuntimeError("Core-only environment unexpectedly acquired an optional engine")
            acceptance = root / "acceptance.json"
            flags = (["--with-octave"] if args.with_octave else []) + (["--with-symbolic"] if args.with_symbolic else [])
            result = subprocess.run([sys.executable, str(driver), "--command-json", json.dumps(command),
                                     "--examples", str(examples), "--output", str(acceptance), "--label", artifact.name, *flags],
                                    cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=600)
            record["acceptance_exit_code"] = result.returncode
            if acceptance.is_file():
                record["acceptance"] = json.loads(acceptance.read_text(encoding="utf-8"))
            else:
                record["acceptance_error"] = {"stdout": result.stdout, "stderr": result.stderr}
            record["status"] = "PASSED" if result.returncode == 0 else "FAILED"
    except Exception as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ("acceptance", "build_info", "installation")}, indent=2))
    return 0 if record["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
