"""Programmatic embedding and durable execution receipts."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
from . import __version__
from . import builtin, adapters, numerical
from .contracts import NacreError, fingerprint


def workspace_path(workspace=None):
    """Resolve user work outside the installed package directory."""
    return Path(workspace).resolve() if workspace is not None else Path.cwd().resolve()

def registry():
    caps = builtin.get_capabilities()
    external = adapters.get_capabilities()
    if caps.keys() & external.keys(): raise NacreError("CAPABILITY", "Duplicate capability registration")
    numbers = numerical.get_capabilities()
    if (caps.keys() | external.keys()) & numbers.keys(): raise NacreError("CAPABILITY", "Duplicate numerical capability registration")
    return {**caps, **external, **numbers}

def discover():
    capabilities=registry()
    available={name:{"available":True,"requires":[],"scope":"Portable local capability"} for name in builtin.get_capabilities()}
    available.update(adapters.capability_availability())
    available.update(numerical.availability())
    return {"language":"Nacre-11","version":__version__,"capabilities":[cap.to_dict() for _,cap in sorted(capabilities.items())],
            "availability":available,"availability_scope":"Configuration/path discovery only; no external engines launched or service workloads verified"}

def invoke(name, args, context):
    if name in numerical.get_capabilities(): return numerical.invoke(name,args,context)
    return (builtin.invoke if name in builtin.get_capabilities() else adapters.invoke)(name,args,context)

def check(source, workspace=None, source_path=None):
    from .language import compile_source
    return compile_source(source,registry(),workspace=workspace_path(workspace),source_path=source_path)

def execute(source, *, workspace=None, workers=4, checkpoint=None, resume=False, source_path=None):
    from .runtime import Runtime
    workspace=workspace_path(workspace)
    caps=registry()
    from .language import compile_source
    plan=compile_source(source,caps,workspace=workspace,source_path=source_path)
    result=Runtime(caps,invoke,workspace,workers=workers).run(plan,checkpoint=checkpoint,resume=resume)
    result["language"]="Nacre-11"
    result["version"]=__version__
    return result

def save_receipt(result, workspace=None):
    workspace=workspace_path(workspace)
    path=(workspace/"outputs"/"runs"/(str(uuid.uuid4())+".json")).resolve()
    if not path.is_relative_to(workspace/"outputs"/"runs"):
        raise NacreError("PATH","Receipt destination must stay inside workspace")
    path.parent.mkdir(parents=True,exist_ok=True)
    payload={"created_utc":datetime.now(timezone.utc).isoformat(),"result":result,"result_sha256":fingerprint(result)}
    with path.open("x",encoding="utf-8") as stream: json.dump(payload,stream,ensure_ascii=False,indent=2,allow_nan=False)
    return {"receipt":str(path),"result_sha256":payload["result_sha256"],"run_id":result["run_id"]}

def verify_receipt(receipt, workspace=None):
    workspace=workspace_path(workspace)
    path=Path(receipt)
    path=(workspace/path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(workspace/"outputs"/"runs") or path.suffix!=".json":
        raise NacreError("PATH","Receipt must be under outputs/runs")
    def reject_constant(value):
        raise ValueError("Non-finite JSON constant")
    try:
        payload=json.loads(path.read_text(encoding="utf-8"),parse_constant=reject_constant)
        result=payload["result"]
        digest_value=payload["result_sha256"]
        if not isinstance(result,dict) or not isinstance(digest_value,str) or len(digest_value)!=64:
            raise ValueError("Invalid saved result shape")
        from .contracts import validate
        validate(result,"Record","receipt result")
        digest=fingerprint(result)==digest_value
    except (NacreError,ValueError,KeyError,TypeError,RecursionError):
        raise NacreError("RECEIPT","Receipt is not an intact Nacre saved result") from None
    artifacts=[]
    def visit(value):
        if isinstance(value,dict):
            if value.get("$type")=="Artifact":
                from .contracts import validate
                validate(value,"Artifact","receipt artifact")
                file=Path(value["path"]).resolve()
                matched=file.is_relative_to(workspace/"outputs") and file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest()==value["sha256"]
                artifacts.append({"path":str(file),"hash_matches":matched})
            for item in value.values(): visit(item)
        elif isinstance(value,list):
            for item in value: visit(item)
    try:
        visit(result)
    except (NacreError,ValueError,KeyError,TypeError,RecursionError):
        raise NacreError("RECEIPT","Receipt is not an intact Nacre saved result") from None
    verified=digest and result.get("status")=="passed" and all(a["hash_matches"] for a in artifacts)
    return {"verified":verified,"run_id":result.get("run_id"),"receipt_hash_matches":digest,"artifacts":artifacts,
            "scope":"Saved result digest and current artifact bytes; not authentication, reexecution or proof of arbitrary mathematics."}
