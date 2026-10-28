"""Implementation identity for source, installed wheels and frozen executables.

These digests invalidate caches; they are not signatures or authentication.
The module loader supplies the same trusted code Python imported, so frozen
distributions do not need loose .py files beside the executable.
"""
import hashlib
import importlib
import json
import struct
import types


MODULES = ("__init__", "contracts", "identity", "language", "runtime", "builtin", "adapters", "api", "cli", "mcp_server")


def _constant_data(value):
    """Encode compiler constants without hash-seed-dependent set iteration."""
    if value is None:
        return ["none"]
    if value is Ellipsis:
        return ["ellipsis"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        return ["float", struct.pack("!d", value).hex()]
    if type(value) is complex:
        return ["complex", struct.pack("!d", value.real).hex(), struct.pack("!d", value.imag).hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    if type(value) is tuple:
        return ["tuple", [_constant_data(item) for item in value]]
    if type(value) is frozenset:
        items = [_constant_data(item) for item in value]
        items.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return ["frozenset", items]
    if isinstance(value, types.CodeType):
        return ["code", _code_data(value)]
    raise TypeError("Unsupported compiler constant type: " + type(value).__name__)


def _code_data(code):
    data = {key: getattr(code, key) for key in (
        "co_argcount", "co_posonlyargcount", "co_kwonlyargcount", "co_nlocals",
        "co_stacksize", "co_flags", "co_filename", "co_name", "co_firstlineno")}
    data.update(co_qualname=getattr(code, "co_qualname", code.co_name),
                co_code=code.co_code.hex(), co_consts=[_constant_data(item) for item in code.co_consts],
                co_names=list(code.co_names), co_varnames=list(code.co_varnames),
                co_freevars=list(code.co_freevars), co_cellvars=list(code.co_cellvars),
                co_linetable=getattr(code, "co_linetable", b"").hex(),
                co_exceptiontable=getattr(code, "co_exceptiontable", b"").hex())
    return data


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def module_fingerprint(name):
    module = importlib.import_module(name)
    loader = getattr(getattr(module, "__spec__", None), "loader", None)
    code = None
    if loader is not None and hasattr(loader, "get_code"):
        try:
            code = loader.get_code(name)
        except (ImportError, OSError):
            pass
    if isinstance(code, types.CodeType):
        return _digest(_code_data(code))
    # A loader may intentionally expose no complete module code. Bind every
    # function/class method already loaded instead of reading module.__file__.
    loaded = {}
    for key, value in vars(module).items():
        if isinstance(value, types.FunctionType) and value.__module__ == name:
            loaded[key] = _code_data(value.__code__)
        elif isinstance(value, type) and value.__module__ == name:
            for attr, member in vars(value).items():
                if isinstance(member, (staticmethod, classmethod)):
                    member = member.__func__
                if isinstance(member, types.FunctionType):
                    loaded[key + "." + attr] = _code_data(member.__code__)
    if not loaded:
        loaded["version"] = getattr(module, "__version__", "nacre-0.1.0")
    return _digest(loaded)


def core_fingerprints():
    # MCP is optional and does not participate in ordinary language evaluation.
    return {name: module_fingerprint("nacre" if name == "__init__" else "nacre." + name)
            for name in MODULES if name != "mcp_server"}
