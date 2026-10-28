"""Prepare a public release manifest only from accepted, commit-bound assets.

Input build/acceptance records stay local. Public output contains artifact hashes,
tool versions, platform facts and receipt basenames, without commands, credentials
or private paths. Existing assets, manifests and checksum files are never replaced.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
PAYLOADS = {
    f"nacre11-{VERSION}-py3-none-any.whl": ("wheel", "any", "any"),
    f"nacre11-{VERSION}.tar.gz": ("source-distribution", "any", "any"),
    f"Nacre-11-{VERSION}-windows-x86_64.zip": ("bundled-interpreter", "Windows", "x86_64"),
    f"Nacre-11-{VERSION}-linux-x86_64.tar.gz": ("bundled-interpreter", "Linux", "x86_64"),
    f"Nacre-11-{VERSION}-source.zip": ("source-archive", "any", "any"),
    f"Nacre-11-{VERSION}-examples.zip": ("examples-archive", "any", "any"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def safe_basename(path):
    name = Path(path).name
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None, "Evidence/artifact basename must be public-safe")
    return name


def safe_members(names):
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name,
                "Unsafe archive member name")


def archive_build_info(path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            safe_members(archive.namelist())
            require(archive.testzip() is None, "ZIP CRC verification failed: " + path.name)
            matches = [name for name in archive.namelist() if PurePosixPath(name).name == "BUILD-INFO.json"]
            require(len(matches) == 1, "Exactly one embedded BUILD-INFO.json is required: " + path.name)
            return json.loads(archive.read(matches[0]).decode("utf-8"))
    with tarfile.open(path, "r:gz") as archive:
        safe_members(archive.getnames())
        matches = [item for item in archive.getmembers() if PurePosixPath(item.name).name == "BUILD-INFO.json" and item.isfile()]
        require(len(matches) == 1, "Exactly one embedded BUILD-INFO.json is required: " + path.name)
        return json.loads(archive.extractfile(matches[0]).read().decode("utf-8"))


def metadata(path, kind, provenance):
    """Check Python payload identity against the matching build source inventory."""
    hashes = provenance.get("source_sha256", {})
    require(isinstance(hashes, dict) and hashes, "Build source inventory is missing")
    if kind == "wheel":
        with zipfile.ZipFile(path) as archive:
            safe_members(archive.namelist())
            require(archive.testzip() is None, "Wheel CRC verification failed")
            records = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            wheels = [name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")]
            require(len(records) == len(wheels) == 1, "Wheel metadata is missing or ambiguous")
            info = archive.read(records[0]).decode("utf-8")
            wheel = archive.read(wheels[0]).decode("utf-8")
            require("Tag: py3-none-any" in wheel and "Root-Is-Purelib: true" in wheel, "Universal wheel tags are not supported by its metadata")
            require(not any(name.lower().endswith((".dll", ".pyd", ".so", ".dylib")) for name in archive.namelist()),
                    "Platform binary found in the universal Python wheel")
            core = [name for name in archive.namelist() if name.startswith("nacre/") and name.endswith(".py")]
            require(core, "Wheel contains no Nacre implementation")
            for name in core:
                require(hashes.get("src/" + name) == sha256(archive.read(name)), "Wheel source differs from its build record: " + name)
    else:
        with tarfile.open(path, "r:gz") as archive:
            safe_members(archive.getnames())
            records = [item for item in archive.getmembers() if item.isfile() and item.name.endswith("/PKG-INFO") and item.name.count("/") == 1]
            require(len(records) == 1, "Source distribution package metadata is missing or ambiguous")
            info = archive.extractfile(records[0]).read().decode("utf-8")
            core = [item for item in archive.getmembers() if item.isfile() and "/src/nacre/" in item.name and item.name.endswith(".py")]
            require(core, "Source distribution contains no Nacre implementation")
            for item in core:
                name = item.name.split("/", 1)[1]
                require(hashes.get(name) == sha256(archive.extractfile(item).read()), "Source distribution differs from its build record: " + name)
    info = info.replace("\r\n", "\n")
    require(re.search(r"^Name: nacre11$", info, re.M) is not None, "Unexpected Python package name")
    require(re.search(r"^Version: " + re.escape(VERSION) + r"$", info, re.M) is not None, "Unexpected Python package version")
    python = re.search(r"^Requires-Python: (.+)$", info, re.M)
    require(python is not None, "Python compatibility metadata is missing")
    return python.group(1).strip()


def environment(provenance):
    """Whitelist public platform facts; never serialize the raw build record."""
    result = {}
    for key in ("platform", "architecture", "python", "python_implementation"):
        value = provenance.get(key)
        require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.+ -]+", value) is not None,
                "Invalid public build environment field: " + key)
        result[key] = value
    libc = provenance.get("libc")
    if libc:
        require(isinstance(libc, list) and len(libc) == 2 and all(isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_.+-]+", v) for v in libc),
                "Invalid public libc metadata")
        result["libc"] = libc
    return result


def toolchain(provenance):
    result = {}
    for key in ("PyInstaller", "build", "setuptools", "wheel"):
        value = provenance.get("toolchain", {}).get(key)
        if value is not None:
            require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.+-]+", value) is not None, "Invalid build tool version")
            result[key] = value
    return result


def verification_summary(path, record):
    summary = {"receipt": safe_basename(path), "status": "PASSED"}
    acceptance = record.get("acceptance", record)
    for name in ("passed", "failed"):
        value = acceptance.get(name)
        if value is not None:
            require(type(value) is int and value >= 0, "Invalid acceptance count")
            summary[name] = value
    require(summary.get("failed", 0) == 0, "Passed receipt contains failed acceptance checks")
    host = str(record.get("host", acceptance.get("host", "")))
    if host.startswith("Windows"):
        summary["platform"] = "Windows"
    elif host.startswith("Linux"):
        summary["platform"] = "Linux"
    elif host:
        summary["platform"] = "Other"
    architecture = str(record.get("architecture", acceptance.get("architecture", ""))).lower()
    if architecture in ("amd64", "x86_64"):
        summary["architecture"] = "x86_64"
    version = re.search(r"\b\d+\.\d+\.\d+\b", str(acceptance.get("driver_python", "")))
    if version:
        summary["test_driver_python"] = version.group()
    return summary


def prepare(args):
    assets = args.assets.resolve()
    require(assets.is_dir(), "Asset directory is missing")
    require(re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is not None, "A full release source commit is required")
    require(re.fullmatch(r"\d+\.\d+", args.linux_glibc) is not None, "Actual Linux glibc major.minor is required")
    builds = [(path, read_json(path)) for path in args.build_record]
    verifications = [(path, read_json(path)) for path in args.verification]
    require(builds, "Commit-bound build records are required")
    require(verifications, "Passed artifact acceptance receipts are required")
    for _, record in verifications:
        require(record.get("status") == "PASSED", "Every supplied verification receipt must have status PASSED")
    rows = []
    all_summaries = []
    for name, (kind, target, architecture) in PAYLOADS.items():
        path = assets / name
        require(path.is_file(), "Required release artifact missing: " + name)
        content = path.read_bytes()
        digest = sha256(content)
        matches = [(p, b) for p, b in builds if any(a.get("filename") == name and a.get("sha256") == digest
                                                   for a in b.get("artifacts", []))]
        require(matches, "No matching build record for final artifact bytes: " + name)
        for _, build in matches:
            require(build.get("status") in ("BUILT_NOT_YET_ACCEPTED", "PASSED"), "Matching build record did not build successfully")
            require(build.get("provenance", {}).get("source_commit") == args.source_commit, "Build source commit differs from release source: " + name)
        provenance = matches[-1][1]["provenance"]
        accepted = [(p, r) for p, r in verifications if r.get("artifact_sha256") == digest
                    and Path(str(r.get("artifact", name))).name == name]
        require(accepted, "No passed verification bound to final artifact SHA-256: " + name)
        summaries = [verification_summary(p, r) for p, r in accepted]
        all_summaries.extend(summaries)
        if target in ("Windows", "Linux"):
            require(any(s.get("platform") == target and s.get("architecture") == architecture for s in summaries),
                    "Standalone acceptance was not performed on its real target platform: " + name)
        row = {"filename": name, "artifact_type": kind, "target_platform": target, "target_architecture": architecture,
               "supported_python": None, "bytes": len(content), "sha256": digest, "source_commit": args.source_commit,
               "build_toolchain": toolchain(provenance), "build_environment": environment(provenance),
               "verification_status": "PASSED", "verification": summaries}
        if kind in ("wheel", "source-distribution"):
            row["supported_python"] = metadata(path, kind, provenance)
            row["python_compatibility_scope"] = "Declared compatibility; tested Python versions/platforms are listed separately"
        if kind in ("bundled-interpreter", "source-archive"):
            embedded = archive_build_info(path)
            require(embedded.get("source_commit") == args.source_commit and embedded.get("version") == VERSION,
                    "Embedded build source/version differs from requested release: " + name)
            require(embedded.get("source_sha256") == provenance.get("source_sha256"), "Embedded source inventory differs from its build receipt: " + name)
            row["embedded_build_info_verified"] = True
            if kind == "bundled-interpreter":
                require(embedded.get("target") == target.lower() + "-x86_64", "Embedded binary target is mislabeled: " + name)
                row["bundled_python_version"] = embedded["python"]
                row["execution_architecture"] = "Bundled Python interpreter and Nacre bytecode; not native Nacre machine-code compilation"
                if target == "Linux":
                    require(embedded.get("libc") == ["glibc", args.linux_glibc], "Linux libc build fact differs from requested manifest")
                    row["minimum_documented_glibc"] = args.linux_glibc
                    row["linux_compatibility_scope"] = "Built and tested on this glibc; older glibc environments are not verified. Use the wheel for other compatible Python hosts."
        rows.append(row)
    wheel_summaries = next(row["verification"] for row in rows if row["artifact_type"] == "wheel")
    require({s.get("platform") for s in wheel_summaries} >= {"Windows", "Linux"}, "The shared wheel requires separate Windows and Linux acceptance")
    notes = args.release_notes.resolve()
    require(notes.is_file(), "Release notes source is missing")
    notes_content = notes.read_bytes()
    notes_asset = assets / "RELEASE-NOTES.md"
    require(not notes_asset.exists() or notes_asset.read_bytes() == notes_content, "Existing release notes differ; preserved")
    rows.append({"filename": notes_asset.name, "artifact_type": "release-notes", "target_platform": "any", "target_architecture": "any",
                 "supported_python": None, "bytes": len(notes_content), "sha256": sha256(notes_content), "source_commit": args.source_commit,
                 "build_toolchain": {}, "build_environment": {"platform": "source-document"}, "verification_status": "PASSED",
                 "verification": [{"check": "Release notes bytes match the supplied source document", "status": "PASSED"}]})
    manifest = {"schema_version": "1.0", "project": "Nacre-11", "version": VERSION, "release_tag": "v" + VERSION,
                "source_commit": args.source_commit, "generated_utc": datetime.now(timezone.utc).isoformat(), "status": "PASSED",
                "artifacts": rows, "tested_platforms": ["Windows x86_64", "Linux x86_64"],
                "tested_python_versions": sorted({s["test_driver_python"] for s in all_summaries if "test_driver_python" in s}),
                "unverified_platforms": ["Linux ARM64", "Windows ARM64", "macOS"],
                "reproducibility": "Exact source commit, recorded tool versions, source inventories and artifact hashes; byte-identical binary rebuilds are not asserted",
                "checksum_scope": "SHA256SUMS covers all payloads, release notes and this manifest; it excludes SHA256SUMS itself to avoid a circular digest",
                "evidence_scope": "Local input receipts are not distributed here. Basenames and bounded check summaries link the release review without exporting private paths or logs."}
    output = (args.output if args.output.is_absolute() else assets / args.output).resolve() if args.output else assets / "ARTIFACT-MANIFEST.json"
    checksums = assets / "SHA256SUMS"
    require(output.parent == assets and output.name not in PAYLOADS and output.name not in (notes_asset.name, checksums.name),
            "Manifest output must be a separate filename inside the asset directory")
    require(not output.exists() and not checksums.exists(), "Manifest or SHA256SUMS already exists; no release files were replaced")
    allowed = set(PAYLOADS) | {notes_asset.name}
    require(all(path.name in allowed for path in assets.iterdir() if path.is_file()), "Unexpected existing file in final release asset directory")
    manifest_content = (json.dumps(manifest, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    hashes = {row["filename"]: row["sha256"] for row in rows}
    hashes[output.name] = sha256(manifest_content)
    checksum_content = "".join(digest + "  " + name + "\n" for name, digest in sorted(hashes.items())).encode("ascii")
    return manifest, output, manifest_content, checksums, checksum_content, notes_asset, notes_content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=ROOT / "dist")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--verification", type=Path, action="append", default=[], help="Passed artifact-aware acceptance JSON; repeat for each target/artifact")
    parser.add_argument("--build-record", type=Path, action="append", default=[], help="Commit-bound build record JSON; repeat for each build")
    parser.add_argument("--linux-glibc", required=True, help="Actual tested Linux build glibc major.minor")
    parser.add_argument("--release-notes", type=Path, default=ROOT / "RELEASE-NOTES.md")
    parser.add_argument("--output", type=Path, help="New manifest filename under --assets; existing files are never replaced")
    parser.add_argument("--dry-run", action="store_true", help="Check all evidence and prepare output without writing release files")
    args = parser.parse_args()
    manifest, output, content, checksums, sums, notes, notes_content = prepare(args)
    if not args.dry_run:
        if not notes.exists():
            with notes.open("xb") as stream:
                stream.write(notes_content)
        with output.open("xb") as stream:
            stream.write(content)
        with checksums.open("xb") as stream:
            stream.write(sums)
        for line in checksums.read_text(encoding="ascii").splitlines():
            expected, filename = line.split("  ", 1)
            require(sha256((args.assets.resolve() / filename).read_bytes()) == expected, "Checksum readback failed: " + filename)
    print(json.dumps({"status": "PREVIEW_PASSED" if args.dry_run else "PASSED", "source_commit": args.source_commit,
                      "artifacts": len(manifest["artifacts"]), "checksum_entries": len(manifest["artifacts"]) + 1,
                      "manifest": output.name, "manifest_sha256": sha256(content), "checksums": checksums.name,
                      "written": not args.dry_run}, indent=2))


if __name__ == "__main__":
    main()
