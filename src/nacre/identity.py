"""Implementation identity for source, installed wheels and frozen executables.

These digests invalidate caches; they are not signatures or authentication.
The module loader supplies the same trusted code Python imported, so frozen
distributions do not need loose .py files beside the executable.
"""
import hashlib
import importlib
import marshal
import types


MODULES = ("__init__", "contracts", "identity", "language", "runtime", "builtin", "adapters", "api", "cli", "mcp_server")


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
        return hashlib.sha256(marshal.dumps(code)).hexdigest()
    # A loader may intentionally expose no complete module code. Bind every
    # function/class method already loaded instead of reading module.__file__.
    loaded = {}
    for key, value in vars(module).items():
        if isinstance(value, types.FunctionType) and value.__module__ == name:
            loaded[key] = marshal.dumps(value.__code__)
        elif isinstance(value, type) and value.__module__ == name:
            for attr, member in vars(value).items():
                if isinstance(member, (staticmethod, classmethod)):
                    member = member.__func__
                if isinstance(member, types.FunctionType):
                    loaded[key + "." + attr] = marshal.dumps(member.__code__)
    content = b"\0".join(key.encode("utf-8") + b"\0" + value for key, value in sorted(loaded.items()))
    if not content:
        content = repr(getattr(module, "__version__", "nacre-0.1.0")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def core_fingerprints():
    # MCP is optional and does not participate in ordinary language evaluation.
    return {name: module_fingerprint("nacre" if name == "__init__" else "nacre." + name)
            for name in MODULES if name != "mcp_server"}
