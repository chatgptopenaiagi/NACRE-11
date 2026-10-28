"""Small deterministic standard library. No shell, SQL evaluator, or host eval."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import time
from .contracts import Capability, NacreError, validate, type_of, fingerprint

def get_capabilities():
    specs = [
        Capability("core.length", {"value": "Any"}, "Integer", description="Length of a list, string, record or table rows."),
        Capability("core.sum", {"values": "List"}, "Number"),
        Capability("core.approx", {"actual": "Number", "expected": "Number", "tolerance": "Number"}, "Bool"),
        Capability("core.wait", {"value": "Number", "milliseconds": "Integer"}, "Number", description="Bounded deterministic result with simulated latency for scheduling experiments."),
        Capability("core.object", {"origin":"String", "kind":"String", "id":"String", "revision":"String", "ownership":"String"}, "Object"),
        Capability("core.same_object", {"left":"Object", "right":"Object"}, "Bool"),
        Capability("core.artifact_verify", {"artifact":"Artifact"}, "Bool", effect="read", resource="workspace-files", retry_safe=True),
        Capability("data.table", {"rows":"List", "source":"String"}, "Table"),
        Capability("data.project", {"table":"Table", "columns":"List"}, "Table"),
        Capability("data.filter", {"table":"Table", "column":"String", "operator":"String", "value":"Any"}, "Table"),
        Capability("data.derive", {"table":"Table", "source_column":"String", "column":"String", "operator":"String", "value":"Number"}, "Table"),
        Capability("data.convert", {"table":"Table", "column":"String", "target":"String"}, "Table"),
        Capability("data.column", {"table":"Table", "column":"String"}, "List"),
        Capability("data.stats", {"values":"List"}, "Record"),
        Capability("data.join", {"left":"Table", "right":"Table", "left_key":"String", "right_key":"String"}, "Table"),
        Capability("io.write_json", {"value":"Any", "filename":"String"}, "Artifact", effect="write", resource="workspace-files", retry_safe=False),
        Capability("demo.flaky", {"value":"Number", "key":"String"}, "Number", effect="read", resource="recovery-demo", retry_safe=True,
                   description="Controlled recoverable failure: first attempt for a workspace key fails, later attempts succeed."),
    ]
    from .identity import module_fingerprint
    implementation = module_fingerprint(__name__)
    from dataclasses import replace
    return {s.name: replace(s, implementation=implementation) for s in specs}

def _numeric(value):
    if type(value) not in (int, float): raise NacreError("CONVERSION", "Numeric operation requires Number; convert explicitly")
    return value

def _column(table, name):
    for col in table["schema"]:
        if col["name"] == name: return col
    raise NacreError("SCHEMA", f"Unknown table column: {name}")

def _table(rows, source):
    if len(rows)>10000: raise NacreError("RESOURCE", "Table input exceeds 10000 rows")
    if not all(isinstance(r, dict) and "$type" not in r for r in rows):
        raise NacreError("SCHEMA", "Table rows must be ordinary records")
    names = list(rows[0]) if rows else []
    if any(set(r) != set(names) for r in rows): raise NacreError("SCHEMA", "Table rows must have identical fields")
    schema = []
    for name in names:
        values = [r[name] for r in rows]
        types = {type_of(v) for v in values if v is not None}
        if not types: typ = "Null"
        elif types <= {"Integer", "Number"}: typ = "Number" if "Number" in types else "Integer"
        elif len(types) == 1: typ = next(iter(types))
        else: raise NacreError("SCHEMA", f"Mixed types in column {name}; explicit conversion required")
        schema.append({"name":name, "type":typ, "nullable":None in values})
    return validate({"$type":"Table", "schema":schema, "rows":rows, "source":source,"snapshot":fingerprint(rows),"count":len(rows)}, "Table")

def _output_path(workspace, filename):
    base = (Path(workspace) / "outputs").resolve()
    base.mkdir(parents=True, exist_ok=True)
    target = (base / filename).resolve()
    if not target.is_relative_to(base) or target == base: raise NacreError("PATH", "Output path must stay inside workspace outputs")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target

def invoke(name, args, context):
    if name == "core.length":
        value = args["value"]
        if type_of(value) == "Table": return len(value["rows"])
        if isinstance(value, (str, list, dict)): return len(value)
        raise NacreError("TYPE", "core.length accepts String, List, Record or Table")
    if name == "core.sum": return sum(_numeric(v) for v in args["values"])
    if name == "core.approx":
        if args["tolerance"] < 0: raise NacreError("VALUE", "Tolerance must be nonnegative")
        return abs(args["actual"] - args["expected"]) <= args["tolerance"]
    if name == "core.wait":
        if not 0 <= args["milliseconds"] <= 5000: raise NacreError("VALUE", "milliseconds must be in [0,5000]")
        event = context.get("cancel_event")
        if event:
            if event.wait(args["milliseconds"] / 1000): raise NacreError("CANCELLED", "Computation cancelled")
        else: time.sleep(args["milliseconds"] / 1000)
        return args["value"]
    if name == "core.object": return {"$type":"Object", **args}
    if name == "core.same_object":
        return all(args["left"][k] == args["right"][k] for k in ("origin","kind","id"))
    if name == "core.artifact_verify":
        path = Path(args["artifact"]["path"]).resolve()
        base = (Path(context["workspace"]) / "outputs").resolve()
        if not path.is_relative_to(base): raise NacreError("PATH", "Artifact verification is limited to workspace outputs")
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == args["artifact"]["sha256"]
    if name == "data.table": return _table(deepcopy(args["rows"]), args["source"])
    if name in ("data.project", "data.filter", "data.derive", "data.convert", "data.column"):
        table = deepcopy(args["table"])
        if name == "data.project":
            columns=args["columns"]
            if not all(isinstance(c,str) for c in columns) or len(set(columns)) != len(columns): raise NacreError("SCHEMA", "Projection columns must be unique strings")
            table["schema"] = [_column(table, c) for c in columns]
            table["rows"] = [{c:r[c] for c in columns} for r in table["rows"]]
            if "identity" in table: table["identity"]["key_retained"]=table["identity"].get("key") in columns
        elif name == "data.column":
            _column(table, args["column"])
            return [r[args["column"]] for r in table["rows"]]
        elif name == "data.filter":
            col=_column(table,args["column"])
            validate(args["value"], col["type"], "filter value")
            from operator import eq, ne, lt, le, gt, ge
            operators={"==":eq,"!=":ne,"<":lt,"<=":le,">":gt,">=":ge}
            if args["operator"] not in operators: raise NacreError("VALUE", "Unknown filter operator")
            op=operators[args["operator"]]
            table["rows"]=[r for r in table["rows"] if r[args["column"]] is not None and op(r[args["column"]],args["value"])]
        elif name == "data.derive":
            col=_column(table,args["source_column"])
            if col["type"] not in ("Number","Integer"): raise NacreError("CONVERSION", "Derived arithmetic requires a numeric source column")
            if any(c["name"]==args["column"] for c in table["schema"]): raise NacreError("SCHEMA", "Derived column already exists")
            if args["operator"] not in ("+","-","*","/"): raise NacreError("VALUE", "Unknown derive operator")
            from operator import add, sub, mul, truediv
            op={"+":add,"-":sub,"*":mul,"/":truediv}[args["operator"]]
            for r in table["rows"]: r[args["column"]]=None if r[args["source_column"]] is None else op(r[args["source_column"]],args["value"])
            table["schema"].append({"name":args["column"],"type":"Number","nullable":col.get("nullable",False)})
        else:
            col=_column(table,args["column"])
            target=args["target"]
            if target not in ("Number","Integer","String"): raise NacreError("CONVERSION", "Conversion target must be Number, Integer or String")
            for r in table["rows"]:
                v=r[args["column"]]
                if v is None: continue
                if type(v) not in (int,float,str): raise NacreError("CONVERSION", "Conversion requires scalar text or numeric value")
                try:
                    if target == "Integer":
                        converted=int(v)
                        if isinstance(v,float) and converted != v: raise ValueError("lossy integer conversion")
                    elif target == "Number": converted=float(v)
                    else: converted=str(v)
                    validate(converted,target)
                except (ValueError,OverflowError) as ex: raise NacreError("CONVERSION", str(ex)) from ex
                r[args["column"]]=converted
            col["native_type_before_conversion"]=col["type"]
            col["type"]=target
        table.setdefault("transformations",[]).append({"capability":name,"arguments":{k:v for k,v in args.items() if k!="table"}})
        table["snapshot"],table["count"]=fingerprint(table["rows"]),len(table["rows"])
        return validate(table,"Table")
    if name == "data.stats":
        values=[_numeric(v) for v in args["values"]]
        if not values: raise NacreError("VALUE", "Statistics require at least one value")
        return {"count":len(values),"sum":sum(values),"mean":statistics.mean(values),"minimum":min(values),"maximum":max(values)}
    if name == "data.join":
        left, right=args["left"], args["right"]
        lc,rc=_column(left,args["left_key"]),_column(right,args["right_key"])
        if lc["type"] != rc["type"]: raise NacreError("CONVERSION", "Join key types must match exactly; convert explicitly")
        if lc["type"] not in ("String","Integer","Number","Bool"): raise NacreError("TYPE", "Join keys must be scalar")
        schema=[{**c,"name":prefix+c["name"]} for prefix,t in (("left_",left),("right_",right)) for c in t["schema"]]
        rows=[]
        for l in left["rows"]:
            if l[args["left_key"]] is None: continue
            for r in right["rows"]:
                if r[args["right_key"]] is not None and l[args["left_key"]] == r[args["right_key"]]:
                    rows.append({**{"left_"+k:v for k,v in l.items()},**{"right_"+k:v for k,v in r.items()}})
                    if len(rows)>10000: raise NacreError("RESOURCE", "Join output exceeds 10000 rows")
        return {"$type":"Table","source":"join:"+fingerprint([left["source"],right["source"]]),"schema":schema,"rows":rows,"snapshot":fingerprint(rows),"count":len(rows),
                "provenance":{"left":left["source"],"right":right["source"],"keys":[args["left_key"],args["right_key"]]}}
    if name == "io.write_json":
        path=_output_path(context["workspace"],args["filename"])
        content=(json.dumps(args["value"],ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
        try:
            with path.open("xb") as stream: stream.write(content)
        except FileExistsError as ex: raise NacreError("EXISTS", "Output already exists; choose a new filename") from ex
        return {"$type":"Artifact","path":str(path),"sha256":hashlib.sha256(content).hexdigest(),"media_type":"application/json","ownership":"workspace"}
    if name == "demo.flaky":
        key=hashlib.sha256(args["key"].encode()).hexdigest()
        path=_output_path(context["workspace"],"recovery/"+key+".marker")
        try:
            with path.open("xb") as stream: stream.write(b"controlled failure observed\n")
        except FileExistsError: return args["value"]
        raise NacreError("TRANSIENT_DEMO", "Controlled first-attempt failure; safe retry is available",retryable=True)
    raise NacreError("CAPABILITY", f"Unknown built-in capability: {name}")
