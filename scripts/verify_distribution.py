"""Install/extract a release artifact and exercise it independently of source."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


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
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    examples = args.examples.resolve()
    driver = Path(__file__).with_name("release_acceptance.py").resolve()
    record = {"checked_utc": datetime.now(timezone.utc).isoformat(), "artifact": artifact.name,
              "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "kind": args.kind,
              "host": platform.platform(), "architecture": platform.machine(), "status": "FAILED"}
    with tempfile.TemporaryDirectory(prefix="nacre installed distribution-λ-") as temporary:
        root = Path(temporary).resolve()
        command = None
        if args.kind == "wheel":
            venv.EnvBuilder(with_pip=True, clear=False).create(root / "venv")
            python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
            process = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(artifact)],
                                     cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=120)
            record["installation"] = {"exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr,
                                      "dependencies_downloaded": False}
            if process.returncode:
                raise RuntimeError("Clean wheel installation failed: " + process.stderr)
            executable = root / "venv" / ("Scripts/nacre.exe" if os.name == "nt" else "bin/nacre")
            if not executable.is_file():
                raise RuntimeError("Installed console entry point missing")
            command = [str(executable)]
            probe = subprocess.run([str(python), "-I", "-c", "import nacre; print(nacre.__version__)"],
                                   cwd=root, capture_output=True, text=True, check=True)
            record["installed_import_version"] = probe.stdout.strip()
        else:
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
                    if any(member.issym() or member.islnk() or not (member.isfile() or member.isdir()) for member in archive.getmembers()):
                        raise ValueError("Links/devices are excluded from release archives")
                    archive.extractall(extracted)
            record["archive_paths_verified"] = True
            if args.kind == "standalone":
                name = "nacre.exe" if os.name == "nt" else "nacre"
                candidates = [p for p in extracted.rglob(name) if p.is_file()]
                if len(candidates) != 1:
                    raise ValueError("Standalone executable missing or ambiguous")
                executable = candidates[0]
                examples = executable.parent / "examples"
                if not (executable.parent / "LICENSE").is_file() or not (executable.parent / "licenses/NOTICE-MANIFEST.json").is_file():
                    raise ValueError("Runtime/Nacre license notices missing")
                info = json.loads((executable.parent / "BUILD-INFO.json").read_text(encoding="utf-8"))
                record["build_info"] = info
                command = [str(executable)]
            elif args.kind in ("sdist", "source"):
                metadata = list(extracted.rglob("pyproject.toml"))
                if len(metadata) != 1 or not (metadata[0].parent / "src/nacre/language.py").is_file():
                    raise ValueError("Source build metadata or implementation missing")
                source = metadata[0].parent
                required = ["LICENSE", "README.md", "GETTING-STARTED.md", "examples/manifest.json", "MANIFEST.in"]
                if any(not (source / name).is_file() for name in required):
                    raise ValueError("Source archive incomplete")
                record["source_metadata_complete"] = True
            elif args.kind == "examples":
                manifests = list(extracted.rglob("manifest.json"))
                if len(manifests) != 1:
                    raise ValueError("Examples manifest missing or ambiguous")
                record["examples_manifest_present"] = True
        if command:
            acceptance = root / "acceptance.json"
            process = subprocess.run([sys.executable, str(driver), "--command-json", json.dumps(command),
                                      "--examples", str(examples), "--output", str(acceptance), "--label", artifact.name],
                                     cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=600)
            record["acceptance_exit_code"] = process.returncode
            if acceptance.is_file():
                record["acceptance"] = json.loads(acceptance.read_text(encoding="utf-8"))
            else:
                record["acceptance_error"] = {"stdout": process.stdout, "stderr": process.stderr}
            record["status"] = "PASSED" if process.returncode == 0 else "FAILED"
        else:
            record["status"] = "PASSED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ("acceptance", "build_info", "installation")}, indent=2))
    return 0 if record["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
