"""Shared adapter contracts and nominal cross-system value validation."""
from dataclasses import dataclass, asdict
import hashlib
import json
import math

TYPES = frozenset({"Any", "Null", "Bool", "Integer", "Number", "String", "List", "Record", "Table", "Symbolic", "Artifact", "Object"})
DOMAIN_TYPES = frozenset({"Table", "Symbolic", "Artifact", "Object"})

class NacreError(Exception):
    def __init__(self, code, message, *, line=None, node=None, retryable=False):
        super().__init__(message)
        self.code, self.message = code, str(message)
        self.line, self.node, self.retryable = line, node, retryable

    def to_dict(self):
        return {"code": self.code, "message": self.message, "line": self.line,
                "node": self.node, "retryable": self.retryable}

@dataclass(frozen=True)
class Capability:
    name: str
    inputs: dict
    output: str
    effect: str = "pure"
    resource: str = ""
    retry_safe: bool = False
    optional: tuple = ()
    description: str = ""
    implementation: str = "nacre-0.1"

    def to_dict(self):
        return asdict(self)

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

def type_of(value):
    if value is None: return "Null"
    if isinstance(value, bool): return "Bool"
    if isinstance(value, int): return "Integer"
    if isinstance(value, float): return "Number"
    if isinstance(value, str): return "String"
    if isinstance(value, list): return "List"
    if isinstance(value, dict):
        if "$type" not in value: return "Record"
        tag = value["$type"]
        return tag if isinstance(tag, str) and tag in DOMAIN_TYPES else "Invalid"
    return "Invalid"

def compatible(actual, expected):
    return expected == "Any" or actual == expected or (actual == "Integer" and expected == "Number")

def validate(value, expected, where="value"):
    actual = type_of(value)
    if expected not in TYPES or actual not in TYPES or not compatible(actual, expected):
        raise NacreError("TYPE", f"{where}: expected {expected}, received {actual}")
    if isinstance(value, float) and not math.isfinite(value):
        raise NacreError("VALUE", f"{where}: non-finite numbers are not portable")
    if isinstance(value, list):
        for item in value: validate(item, "Any", where)
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise NacreError("TYPE", f"{where}: record keys must be strings")
        for item in value.values(): validate(item, "Any", where)
    if actual == "Table":
        if not isinstance(value.get("schema"), list) or not isinstance(value.get("rows"), list) or not isinstance(value.get("source"), str):
            raise NacreError("CONTRACT", f"{where}: Table requires schema, rows and source")
        names = set()
        for col in value["schema"]:
            if (not isinstance(col, dict) or not isinstance(col.get("name"), str)
                    or not isinstance(col.get("type"), str) or col["type"] not in TYPES
                    or ("nullable" in col and type(col["nullable"]) is not bool)):
                raise NacreError("CONTRACT", f"{where}: invalid table column")
            if col["name"] in names: raise NacreError("CONTRACT", f"{where}: duplicate table column")
            names.add(col["name"])
        for row in value["rows"]:
            if not isinstance(row, dict) or set(row) != names:
                raise NacreError("CONTRACT", f"{where}: row fields disagree with schema")
            for col in value["schema"]:
                item = row[col["name"]]
                if item is None and col.get("nullable", False): continue
                validate(item, col["type"], f"{where}.{col['name']}")
    elif actual == "Symbolic":
        if not isinstance(value.get("expression"), str) or not isinstance(value.get("engine"), str):
            raise NacreError("CONTRACT", f"{where}: Symbolic requires expression and engine")
    elif actual == "Artifact":
        digest = value.get("sha256")
        if (not isinstance(value.get("path"), str) or not isinstance(digest, str)
                or len(digest) != 64 or any(char not in "0123456789abcdefABCDEF" for char in digest)):
            raise NacreError("CONTRACT", f"{where}: Artifact requires path and SHA-256")
    elif actual == "Object":
        if not all(isinstance(value.get(k), str) for k in ("origin", "kind", "id", "revision", "ownership")):
            raise NacreError("CONTRACT", f"{where}: Object identity/provenance incomplete")
    return value
