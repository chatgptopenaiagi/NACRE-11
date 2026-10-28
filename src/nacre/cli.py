"""Stable JSON CLI for the independent Nacre-11 source language."""
from pathlib import Path
import argparse
import json
import sys

from . import __version__
from .contracts import NacreError
from .language import compile_source
from .runtime import Runtime


def registry():
    """Compatibility embedding interface: catalogue and checked dispatcher."""
    from . import api
    return api.registry(), api.invoke


def main(argv=None):
    parser=argparse.ArgumentParser(prog="nacre",description="Nacre-11: experimental checked capability composition language")
    parser.add_argument("--version",action="version",version=f"Nacre-11 {__version__}")
    commands=parser.add_subparsers(dest="command",required=True)
    commands.add_parser("version",help="Report the language version as JSON")
    commands.add_parser("capabilities",help="List implemented contracts and their current configuration requirements")
    for command in ("check","compile","run"):
        sub=commands.add_parser(command,help={"check":"Check source without invoking capabilities","compile":"Prepare checked dependency-graph IR","run":"Execute a .nac program"}[command])
        sub.add_argument("file",help="UTF-8 .nac source file")
        sub.add_argument("--workspace",help="Workspace for includes and outputs; defaults to the current directory")
        if command=="compile":
            sub.add_argument("--output",help="Write graph IR JSON to this file")
        if command=="run":
            sub.add_argument("--workers",type=int,default=4,help="Local worker bound, 1..32 (default: 4)")
            sub.add_argument("--checkpoint",help="Checkpoint JSON path")
            sub.add_argument("--resume",action="store_true",help="Reuse matching pure results; reads and writes run again")
            sub.add_argument("--receipt",action="store_true",help="Save a unique execution receipt under workspace outputs/runs")
    sub=commands.add_parser("verify",help="Verify a saved result digest and current artifact bytes")
    sub.add_argument("receipt",help="Saved JSON receipt under workspace outputs/runs")
    sub.add_argument("--workspace",help="Original execution workspace; defaults to the current directory")
    options=parser.parse_args(argv)
    try:
        from . import api
        if options.command=="version":
            result={"language":"Nacre-11","version":__version__}
        elif options.command=="capabilities":
            result=api.discover()
        elif options.command=="verify":
            result=api.verify_receipt(options.receipt,workspace=options.workspace)
        else:
            source_path=Path(options.file).resolve()
            workspace=api.workspace_path(options.workspace)
            source=source_path.read_text(encoding="utf-8-sig")
            capabilities,invoke=registry()
            plan=compile_source(source,capabilities,workspace=workspace,source_path=source_path)
            if options.command=="check":
                result={"status":"passed","nodes":len(plan.nodes),"source_hash":plan.source_hash,"capabilities_hash":plan.capabilities_hash}
            elif options.command=="compile":
                result=plan.to_dict()
                if options.output:
                    output=Path(options.output)
                    output.parent.mkdir(parents=True,exist_ok=True)
                    output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
            else:
                result=Runtime(capabilities,invoke,workspace,workers=options.workers).run(plan,checkpoint=options.checkpoint,resume=options.resume)
                result.update(language="Nacre-11",version=__version__)
                if options.receipt:
                    result={**result,**api.save_receipt(result,workspace)}
        # Escaped JSON remains valid on legacy terminals and redirected streams.
        print(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False))
        return 0 if result.get("status","passed")=="passed" and result.get("verified") is not False else 1
    except NacreError as exc:
        print(json.dumps({"status":"failed","error":exc.to_dict()},ensure_ascii=True,indent=2))
        return 2
    except (OSError,UnicodeError) as exc:
        print(json.dumps({"status":"failed","error":{"code":"IO","message":str(exc)}},ensure_ascii=True,indent=2))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
