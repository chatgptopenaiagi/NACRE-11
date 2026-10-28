"""Exercise an installed Nacre CLI in fresh directories without importing it.

Use --command-json '["/path/to/nacre"]' or '["python", "-m", "nacre"]'.
No GENESIS configuration or source-tree PYTHONPATH is inherited by children.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-json", required=True)
    parser.add_argument("--examples", type=Path, default=Path(__file__).resolve().parents[1] / "examples")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--label", default="installed-cli")
    args = parser.parse_args()
    command = json.loads(args.command_json)
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        parser.error("--command-json must be a nonempty array of strings")
    examples = args.examples.resolve()
    manifest = json.loads((examples / "manifest.json").read_text(encoding="utf-8"))
    declared = {item["file"] for item in manifest["examples"]}
    actual = {p.relative_to(examples).as_posix() for p in examples.rglob("*.nac")}
    if actual != declared:
        raise ValueError("Every .nac example must appear exactly once in manifest.json")
    if len(declared) != len(manifest["examples"]):
        raise ValueError("Duplicate example manifest entries")
    environment = {k: v for k, v in os.environ.items()
                   if k not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("NACRE_GENESIS")}
    records = []

    def invoke(arguments, workspace, expected_code=0, *, label, expected_status=None):
        began = time.perf_counter()
        process = subprocess.run(command + arguments, cwd=workspace, env=environment,
                                 capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=90)
        try:
            payload = json.loads(process.stdout)
        except ValueError:
            payload = None
        matched = process.returncode == expected_code
        if expected_status is not None:
            matched = matched and isinstance(payload, dict) and payload.get("status") == expected_status
        row = {"check": label, "status": "PASSED" if matched else "FAILED", "exit_code": process.returncode,
               "expected_exit_code": expected_code, "elapsed_ms": round((time.perf_counter() - began) * 1000, 3),
               "stdout": process.stdout, "stderr": process.stderr}
        records.append(row)
        return payload, row

    def require(row, condition, message):
        if not condition:
            row["status"] = "FAILED"
            row.setdefault("findings", []).append(message)

    def artifacts(value, workspace):
        if isinstance(value, dict):
            if value.get("$type") == "Artifact":
                file = Path(value["path"]).resolve()
                if not file.is_relative_to((workspace / "outputs").resolve()) or not file.is_file():
                    return False
                if hashlib.sha256(file.read_bytes()).hexdigest() != value["sha256"]:
                    return False
            return all(artifacts(item, workspace) for item in value.values())
        if isinstance(value, list):
            return all(artifacts(item, workspace) for item in value)
        return True

    def artifact_count(value):
        if isinstance(value, dict):
            return int(value.get("$type") == "Artifact") + sum(artifact_count(item) for item in value.values())
        if isinstance(value, list):
            return sum(artifact_count(item) for item in value)
        return 0

    with tempfile.TemporaryDirectory(prefix="nacre release unicode-λ-") as temporary:
        root = Path(temporary).resolve()
        _, row = invoke(["--help"], root, label="help")
        require(row, "run" in row["stdout"] and "capabilities" in row["stdout"], "Help must describe commands")
        _, row = invoke(["--version"], root, label="version-flag")
        require(row, "0.1.0" in row["stdout"], "Incorrect version")
        value, row = invoke(["version"], root, label="version-json")
        require(row, value is not None and value.get("version") == "0.1.0", "Incorrect JSON version")
        value, row = invoke(["capabilities"], root, label="capability-discovery")
        require(row, value is not None and any(c["name"] == "core.sum" for c in value.get("capabilities", [])), "Core missing from discovery")
        for index, example in enumerate(manifest["examples"]):
            workspace = root / ("example-" + str(index))
            shutil.copytree(examples, workspace)
            path = workspace / example["file"]
            if example.get("requires"):
                _, row = invoke(["check", str(path)], workspace, label="optional-check:" + example["file"], expected_status="passed")
                value, row = invoke(["run", str(path)], workspace, expected_code=1,
                                    expected_status="failed", label="optional-absence:" + example["file"])
                require(row, value is not None and value.get("error", {}).get("code") == "UNAVAILABLE", "Optional engine absence must be explicit")
                row["optional_integration"] = "Not executed; unconfigured absence behavior tested"
                continue
            value, row = invoke(["run", str(path)], workspace, expected_code=example["expected_exit_code"],
                                expected_status=example["expected_status"], label="example:" + example["file"])
            if "expected_emitted" in example:
                require(row, value is not None and value.get("emitted") == example["expected_emitted"], "Emission differs from example requirement")
            if "expected_error_code" in example:
                require(row, value is not None and value.get("error", {}).get("code") == example["expected_error_code"], "Wrong diagnostic category")
            require(row, value is not None and artifacts(value.get("emitted", []), workspace), "Artifact bytes/path/hash invalid")
            if "expected_artifacts" in example:
                require(row, value is not None and artifact_count(value.get("emitted", [])) == example["expected_artifacts"],
                        "Missing or unexpected emitted artifacts")

        def program(name, source):
            path = root / name
            path.write_text(source, encoding="utf-8")
            return str(path)

        good = program("unicode-λ.nac", 'let value: Integer = 6*7; verify value == 42; emit value; emit "hello λ";')
        _, row = invoke(["check", good], root, label="check-from-clean-directory", expected_status="passed")
        ir = root / "prepared.json"
        value, row = invoke(["compile", good, "--output", str(ir)], root, label="compile-ir")
        require(row, ir.is_file() and value is not None and value.get("format") == "nacre-ir-1", "Compiler IR missing")
        value, row = invoke(["run", good], root, label="unicode-path-and-text", expected_status="passed")
        require(row, value is not None and value.get("emitted") == [42, "hello λ"], "Unicode or arithmetic result incorrect")
        bad = program("bad-syntax.nac", 'let x: Integer = 1 "+" 2;')
        _, row = invoke(["run", bad], root, 2, label="syntax-diagnostic", expected_status="failed")
        bad = program("bad-type.nac", 'let x: Integer = "not an integer";')
        value, row = invoke(["run", bad], root, 2, label="type-diagnostic", expected_status="failed")
        require(row, value is not None and value.get("error", {}).get("code") == "TYPE", "Wrong static error")
        bad = program("bad-runtime.nac", "let x: Number = 1/0; emit x;")
        value, row = invoke(["run", bad], root, 1, label="runtime-diagnostic", expected_status="failed")
        require(row, value is not None and value.get("error", {}).get("code") == "ARITHMETIC", "Wrong runtime error")
        _, row = invoke(["run", str(root / "absent.nac")], root, 2, label="missing-file", expected_status="failed")
        checkpoint = root / "checkpoint.json"
        value, row = invoke(["run", good, "--checkpoint", str(checkpoint)], root, label="checkpoint-save", expected_status="passed")
        value, row = invoke(["run", good, "--checkpoint", str(checkpoint), "--resume"], root, label="checkpoint-resume", expected_status="passed")
        require(row, value is not None and value.get("resumed") and any(e.get("event") == "cache_hit" for e in value.get("events", [])), "Pure checkpoint reuse missing")
        value, row = invoke(["run", good, "--receipt"], root, label="save-execution-receipt", expected_status="passed")
        receipt = value.get("receipt") if value else None
        require(row, bool(receipt), "Receipt path missing")
        if receipt:
            checked, row = invoke(["verify", receipt], root, label="verify-execution-receipt")
            require(row, checked is not None and checked.get("verified") is True, "Receipt verification failed")
            file = Path(receipt)
            payload = json.loads(file.read_text(encoding="utf-8"))
            payload["result"]["emitted"] = [43]
            file.write_text(json.dumps(payload), encoding="utf-8")
            checked, row = invoke(["verify", receipt], root, 1, label="reject-tampered-receipt")
            require(row, checked is not None and checked.get("verified") is False, "Modified receipt was accepted")
    report = {"schema_version": "1.0", "checked_utc": datetime.now(timezone.utc).isoformat(),
              "status": "PASSED" if all(r["status"] == "PASSED" for r in records) else "FAILED", "label": args.label,
              "command": command, "host": platform.platform(), "architecture": platform.machine(), "driver_python": sys.version,
              "passed": sum(r["status"] == "PASSED" for r in records), "failed": sum(r["status"] == "FAILED" for r in records),
              "example_manifest_sha256": hashlib.sha256((examples / "manifest.json").read_bytes()).hexdigest(),
              "scope": "Actual installed CLI in fresh Unicode directories, no development PYTHONPATH or optional integration configuration; optional integrations test absence only.",
              "records": records}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
