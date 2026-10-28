"""Official SDK stdio interface. The interpreter remains usable without AI."""
from pathlib import Path
import os
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from . import __version__
from .api import registry, discover, check, execute, save_receipt, verify_receipt
from .contracts import NacreError

ROOT=Path(os.environ.get("NACRE_WORKSPACE",Path.cwd())).expanduser().resolve()
mcp=FastMCP("Nacre-11",instructions="Nacre-11 is an experimental typed capability graph language. Discover contracts and configuration requirements, check a .nac program, run it, and verify the saved receipt. No host-language eval. Core execution and SQLite are portable; external integrations require explicit configuration. Outputs belong to the current workspace. Failure/retry/resume limits are explicit; writes never retry automatically.")
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
RUN=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)

def _error(ex):
    if not isinstance(ex,NacreError):
        ex=NacreError("IO",str(ex))
    return {"status":"failed","error":ex.to_dict()}

@mcp.tool(annotations=READ)
def nacre_discover() -> dict:
    """Discover implemented language capabilities, types, effects and executable paths."""
    return {**discover(),"workspace":str(ROOT),"extension":".nac","cli":"nacre",
            "documentation":"https://github.com/chatgptopenaiagi/NACRE-11"}

@mcp.tool(annotations=READ)
def nacre_check(source:str) -> dict:
    """Parse and type check Nacre source, returning its dependency IR without external operations."""
    try: return {"status":"checked","plan":check(source,workspace=ROOT).to_dict()}
    except NacreError as ex: return _error(ex)

@mcp.tool(annotations=RUN)
def nacre_run(source:str,workers:int=4,checkpoint:str|None=None,resume:bool=False) -> dict:
    """Execute a Nacre program through checked capabilities and persist a result receipt."""
    try:
        if checkpoint is not None:
            candidate=(ROOT/"outputs"/checkpoint).resolve()
            if not candidate.is_relative_to((ROOT/"outputs").resolve()): raise NacreError("PATH","Checkpoint must stay under outputs")
            if candidate.suffix.lower()!=".json": raise NacreError("PATH","Checkpoint filename must use .json")
            checkpoint=str(candidate)
        result=execute(source,workspace=ROOT,workers=workers,checkpoint=checkpoint,resume=resume)
        return {**result,**save_receipt(result,ROOT)}
    except (NacreError,OSError,UnicodeError) as ex: return _error(ex)

@mcp.tool(annotations=RUN)
def nacre_run_file(path:str,workers:int=4) -> dict:
    """Run a workspace .nac file, preserving its include-module source location."""
    try:
        target=(ROOT/path).resolve()
        if not target.is_relative_to(ROOT) or target.suffix!=".nac": raise NacreError("PATH","Expected workspace .nac file")
        result=execute(target.read_text(encoding="utf-8-sig"),workspace=ROOT,workers=workers,source_path=target)
        return {**result,**save_receipt(result,ROOT)}
    except (NacreError,OSError,UnicodeError) as ex: return _error(ex)

@mcp.tool(annotations=READ)
def nacre_verify(receipt:str) -> dict:
    """Recheck a saved result digest and actual artifact hashes, with the verification scope stated."""
    try: return verify_receipt(receipt,ROOT)
    except (NacreError,OSError,UnicodeError) as ex: return _error(ex)

def main(): mcp.run(transport="stdio")

if __name__=="__main__": main()
