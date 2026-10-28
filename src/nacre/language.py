"""Nacre lexer, Pratt expression parser and checked dependency-graph compiler.

The input grammar is implemented here. No Python/PowerShell/SQL evaluator is
used to parse or evaluate Nacre source.
"""
from dataclasses import dataclass, field
from pathlib import Path
import json
import math
import re

from .contracts import TYPES, NacreError, compatible, fingerprint, type_of

RESERVED = frozenset({"use", "include", "let", "task", "verify", "emit", "retry", "true", "false", "null", "and", "or", "not"})


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int


def lex(source):
    if len(source) > 1_000_000:
        raise NacreError("LIMIT", "Source exceeds 1 MB")
    tokens, pos, line, column = [], 0, 1, 1
    pattern = re.compile(r'(?P<space>[ \t\r\n]+)|(?P<comment>\#[^\n]*)|(?P<string>"(?:[^"\\\n]|\\.)*")|(?P<number>(?:\d+(?:\.\d+)?)(?:[eE][+-]?\d+)?)|(?P<id>[A-Za-z_][A-Za-z_0-9]*)|(?P<op><-|==|!=|<=|>=|[+*/%^<>=:;,()\[\]{}.\-])')
    while pos < len(source):
        match = pattern.match(source, pos)
        if not match:
            raise NacreError("SYNTAX", f"Unexpected character at column {column}", line=line)
        kind, value = match.lastgroup, match.group()
        if kind not in ("space", "comment"):
            if kind == "string":
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise NacreError("SYNTAX", f"Invalid string escape: {exc.msg}", line=line) from None
            elif kind == "number":
                try:
                    if not any(c in value for c in ".eE") and len(value) > 4300:
                        raise ValueError("Integer literal exceeds 4300 digits")
                    value = float(value) if any(c in value for c in ".eE") else int(value)
                except (ValueError, OverflowError):
                    raise NacreError("LIMIT", "Numeric literal is too large", line=line) from None
                if isinstance(value, float) and not math.isfinite(value):
                    raise NacreError("VALUE", "Numeric literals must be finite", line=line)
            tokens.append(Token(kind, value, line, column))
        newlines = value.count("\n") if kind in ("space", "comment") else 0
        if newlines:
            line += newlines
            column = len(match.group().rsplit("\n", 1)[-1]) + 1
        else:
            column += len(match.group())
        pos = match.end()
        if len(tokens) > 100_000:
            raise NacreError("LIMIT", "Too many tokens", line=line)
    tokens.append(Token("eof", "<eof>", line, column))
    return tokens


class Parser:
    PRECEDENCE = {"or": 10, "and": 20, "==": 30, "!=": 30,
                  "<": 40, "<=": 40, ">": 40, ">=": 40,
                  "+": 50, "-": 50, "*": 60, "/": 60, "%": 60, "^": 80}

    def __init__(self, source):
        self.tokens, self.i = lex(source), 0

    @property
    def token(self):
        return self.tokens[self.i]

    def matches(self, value):
        # A quoted operator/keyword is data, never punctuation or grammar.
        kind = "id" if value in RESERVED else "op"
        return self.token.kind == kind and self.token.value == value

    def take(self, value=None, kind=None):
        token = self.token
        if (value is not None and not self.matches(value)) or (kind is not None and token.kind != kind):
            wanted = repr(value) if value is not None else kind
            raise NacreError("SYNTAX", f"Expected {wanted}, received {token.value!r} at column {token.column}", line=token.line)
        self.i += 1
        return token

    def accept(self, value):
        if self.matches(value):
            self.take()
            return True
        return False

    def parse(self):
        statements = []
        while self.token.kind != "eof":
            token = self.take(kind="id")
            kind, line = token.value, token.line
            if kind == "use":
                name = self.take(kind="id").value
                self.take("=")
                statement = {"kind": kind, "name": name, "namespace": self.take(kind="string").value, "line": line}
            elif kind == "include":
                statement = {"kind": kind, "path": self.take(kind="string").value, "line": line}
            elif kind in ("let", "task"):
                name = self.take(kind="id").value
                self.take(":")
                declared = self.take(kind="id").value
                statement = {"kind": kind, "name": name, "type": declared, "line": line}
                if kind == "let":
                    self.take("=")
                    statement["expr"] = self.expr()
                else:
                    self.take("<-")
                    parts = [self.take(kind="id").value]
                    while self.accept("."):
                        parts.append(self.take(kind="id").value)
                    statement["capability"] = ".".join(parts)
                    self.take("(")
                    args = {}
                    if not self.matches(")"):
                        while True:
                            key = self.take(kind="id").value
                            if key in args:
                                raise NacreError("DUPLICATE", f"Duplicate argument {key}", line=line)
                            self.take("=")
                            args[key] = self.expr()
                            if not self.accept(","): break
                    self.take(")")
                    statement["args"], statement["retry"] = args, 0
                    if self.accept("retry"):
                        retry = self.take(kind="number")
                        if type(retry.value) is not int or not 0 <= retry.value <= 10:
                            raise NacreError("RETRY", "retry requires an integer from 0 to 10", line=retry.line)
                        statement["retry"] = retry.value
            elif kind in ("verify", "emit"):
                statement = {"kind": kind, "expr": self.expr(), "line": line}
            else:
                raise NacreError("SYNTAX", f"Unknown statement {kind!r}", line=line)
            self.take(";")
            statements.append(statement)
        return statements

    def expr(self, minimum=0, depth=0):
        if depth > 100:
            raise NacreError("LIMIT", "Expression nesting exceeds 100", line=self.token.line)
        token = self.take()
        line = token.line
        if token.kind in ("number", "string"):
            left = {"kind": "literal", "value": token.value, "line": line}
        elif token.value in ("true", "false", "null"):
            left = {"kind": "literal", "value": {"true": True, "false": False, "null": None}[token.value], "line": line}
        elif token.value in ("+", "-", "not"):
            left = {"kind": "unary", "op": token.value, "expr": self.expr(25 if token.value == "not" else 70, depth + 1), "line": line}
        elif token.value == "(":
            left = self.expr(0, depth + 1)
            self.take(")")
        elif token.value == "[":
            items = []
            if not self.matches("]"):
                while True:
                    items.append(self.expr(0, depth + 1))
                    if not self.accept(","): break
            self.take("]")
            left = {"kind": "list", "items": items, "line": line}
        elif token.value == "{":
            items = {}
            if not self.matches("}"):
                while True:
                    key = self.take()
                    if key.kind not in ("id", "string"):
                        raise NacreError("SYNTAX", "Record keys must be names or strings", line=key.line)
                    if key.value in items:
                        raise NacreError("DUPLICATE", f"Duplicate field {key.value}", line=line)
                    self.take(":")
                    items[key.value] = self.expr(0, depth + 1)
                    if not self.accept(","): break
            self.take("}")
            left = {"kind": "record", "items": items, "line": line}
        elif token.kind == "id":
            left = {"kind": "ref", "name": token.value, "line": line}
        else:
            raise NacreError("SYNTAX", f"Expected an expression, received {token.value!r}", line=line)
        while True:
            if (self.matches(".") or self.matches("[")) and minimum <= 90:
                if self.accept("."):
                    left = {"kind": "index", "base": left, "index": {"kind": "literal", "value": self.take(kind="id").value, "line": self.token.line}, "line": line}
                else:
                    self.take("[")
                    key = self.expr(0, depth + 1)
                    self.take("]")
                    left = {"kind": "index", "base": left, "index": key, "line": line}
                continue
            op = self.token.value
            precedence = self.PRECEDENCE.get(op, -1) if self.token.kind in ("op", "id") else -1
            if precedence < minimum: break
            self.take()
            right = self.expr(precedence if op == "^" else precedence + 1, depth + 1)
            left = {"kind": "binary", "op": op, "left": left, "right": right, "line": line}
        return left


def references(expr):
    kind = expr["kind"]
    if kind == "ref": return {expr["name"]}
    if kind in ("literal",): return set()
    if kind == "unary": return references(expr["expr"])
    if kind == "binary": return references(expr["left"]) | references(expr["right"])
    if kind == "index": return references(expr["base"]) | references(expr["index"])
    if kind == "list": return set().union(*(references(item) for item in expr["items"]))
    if kind == "record": return set().union(*(references(item) for item in expr["items"].values()))
    raise NacreError("INTERNAL", f"Unknown expression node {kind}")


def _expression_limit(expr):
    """Bound semantic recursion even for long left-associative expressions."""
    pending = [(expr, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > 100:
            raise NacreError("LIMIT", "Expression tree depth exceeds 100", line=node["line"])
        kind = node["kind"]
        if kind == "unary": children = [node["expr"]]
        elif kind == "binary": children = [node["left"], node["right"]]
        elif kind == "index": children = [node["base"], node["index"]]
        elif kind == "list": children = node["items"]
        elif kind == "record": children = node["items"].values()
        else: children = []
        pending.extend((child, depth + 1) for child in children)


def infer(expr, types):
    kind, line = expr["kind"], expr["line"]
    def fail(message): raise NacreError("TYPE", message, line=line)
    if kind == "literal": return type_of(expr["value"])
    if kind == "ref":
        if expr["name"] not in types:
            raise NacreError("NAME", f"Unknown binding {expr['name']}", line=line)
        return types[expr["name"]]
    if kind == "list":
        for item in expr["items"]: infer(item, types)
        return "List"
    if kind == "record":
        for item in expr["items"].values(): infer(item, types)
        return "Record"
    if kind == "index":
        base, key = infer(expr["base"], types), infer(expr["index"], types)
        if base not in ("Any", "List", "Record", "Table", "Symbolic", "Artifact", "Object", "String"):
            fail(f"Cannot index {base}")
        if base in ("List", "String") and key not in ("Integer", "Any"):
            fail(f"{base} requires an Integer index")
        if base in ("Record", "Table", "Symbolic", "Artifact", "Object") and key not in ("String", "Any"):
            fail(f"{base} requires a String key")
        if expr["base"]["kind"] == "record" and expr["index"]["kind"] == "literal":
            name = expr["index"]["value"]
            if name not in expr["base"]["items"]: fail(f"Unknown record field {name}")
            return infer(expr["base"]["items"][name], types)
        return "String" if base == "String" else "Any"
    if kind == "unary":
        operand = infer(expr["expr"], types)
        if expr["op"] == "not":
            if operand not in ("Bool", "Any"): fail("not requires Bool")
            return "Bool"
        if operand not in ("Number", "Integer", "Any"): fail("Unary arithmetic requires Number")
        return operand
    if kind == "binary":
        left, right, op = infer(expr["left"], types), infer(expr["right"], types), expr["op"]
        if op in ("and", "or"):
            if left not in ("Bool", "Any") or right not in ("Bool", "Any"): fail(f"{op} requires Bool operands")
            return "Bool"
        if op in ("==", "!="): return "Bool"
        if op in ("<", "<=", ">", ">="):
            if left != "Any" and right != "Any" and not ((left in ("Number", "Integer") and right in ("Number", "Integer")) or left == right == "String"):
                fail(f"Cannot order {left} and {right}")
            return "Bool"
        if op == "+" and left == right and left in ("String", "List"): return left
        if left not in ("Number", "Integer", "Any") or right not in ("Number", "Integer", "Any"):
            fail(f"{op} requires compatible numeric operands")
        if op == "/": return "Number"
        if "Any" in (left, right): return "Any"
        if "Number" in (left, right) or op == "^": return "Number"
        return "Integer"
    raise NacreError("INTERNAL", f"Unknown expression node {kind}")


@dataclass
class Plan:
    nodes: list
    verifications: list
    emissions: list
    aliases: dict
    source_hash: str
    capabilities_hash: str
    modules: dict = field(default_factory=dict)

    def to_dict(self):
        return {"format": "nacre-ir-1", "nodes": self.nodes,
                "verifications": self.verifications, "emissions": self.emissions,
                "aliases": self.aliases, "source_hash": self.source_hash,
                "capabilities_hash": self.capabilities_hash, "modules": self.modules}


def compile_source(source, capabilities, workspace=None, source_path=None):
    """Parse and check all graph nodes before any capability may execute."""
    workspace = Path(workspace or Path.cwd()).resolve()
    modules, active, included = {}, set(), set()
    statement_count = [0]

    def expand(text, path=None):
        key = str(path) if path else "<source>"
        if key in active:
            raise NacreError("MODULE", f"Cyclic include: {key}")
        if key in included:
            return []
        active.add(key)
        modules[key] = fingerprint(text)
        statements = Parser(text).parse()
        statement_count[0] += len(statements)
        if statement_count[0] > 10000:
            raise NacreError("LIMIT", "Program exceeds 10000 statements")
        result = []
        for item in statements:
            if item["kind"] == "include":
                if len(active) >= 32:
                    raise NacreError("MODULE", "Include depth exceeds 32", line=item["line"])
                candidate = ((path.parent if path else workspace) / item["path"]).resolve()
                if not candidate.is_relative_to(workspace) or candidate.suffix != ".nac":
                    raise NacreError("MODULE", "Includes must be .nac files inside the workspace", line=item["line"])
                try:
                    child = candidate.read_text(encoding="utf-8-sig")
                except OSError as exc:
                    raise NacreError("MODULE", f"Cannot read include {item['path']}: {exc.strerror}", line=item["line"]) from None
                result.extend(expand(child, candidate))
            else:
                item["source"] = key
                result.append(item)
        active.remove(key)
        included.add(key)
        return result

    initial_path = Path(source_path).resolve() if source_path else None
    try:
        statements = expand(source, initial_path)
    except RecursionError:
        raise NacreError("LIMIT", "Program nesting exceeds parser limit") from None
    aliases, nodes, types, verifications, emissions = {}, [], {}, [], []
    for item in statements:
        kind = item["kind"]
        if kind == "use":
            if item["name"] in RESERVED:
                raise NacreError("NAME", f"Reserved word cannot be an alias: {item['name']}", line=item["line"])
            if item["name"] in aliases:
                raise NacreError("DUPLICATE", f"Duplicate capability alias {item['name']}", line=item["line"])
            namespace = item["namespace"]
            if not any(name == namespace or name.startswith(namespace + ".") for name in capabilities):
                raise NacreError("CAPABILITY", f"Unknown capability namespace {namespace!r}", line=item["line"])
            aliases[item["name"]] = namespace
        elif kind in ("let", "task"):
            name = item["name"]
            if name in RESERVED:
                raise NacreError("NAME", f"Reserved word cannot be a binding: {name}", line=item["line"])
            if name in types:
                raise NacreError("DUPLICATE", f"Binding {name} is immutable and already declared", line=item["line"])
            if item["type"] not in TYPES:
                raise NacreError("TYPE", f"Unknown type {item['type']}", line=item["line"])
            types[name] = item["type"]
            nodes.append(item)
        elif kind == "verify": verifications.append(item)
        elif kind == "emit": emissions.append(item)

    for node in nodes:
        if node["kind"] == "let":
            _expression_limit(node["expr"])
            actual = infer(node["expr"], types)
            deps = references(node["expr"])
            node["effect"], node["resource"] = "pure", ""
        else:
            parts = node["capability"].split(".")
            if parts[0] in aliases:
                node["capability"] = ".".join([aliases[parts[0]], *parts[1:]])
            name = node["capability"]
            if name not in capabilities:
                raise NacreError("CAPABILITY", f"Unknown capability {name}", line=node["line"], node=node["name"])
            cap = capabilities[name]
            if (cap.effect not in ("pure", "read", "write") or cap.output not in TYPES
                    or not all(value in TYPES for value in cap.inputs.values())
                    or not set(cap.optional) <= set(cap.inputs)):
                raise NacreError("CONTRACT", f"Invalid capability contract {name}", line=node["line"])
            missing = set(cap.inputs) - set(cap.optional) - set(node["args"])
            extra = set(node["args"]) - set(cap.inputs)
            if missing or extra:
                raise NacreError("ARGUMENT", f"{name}: missing {sorted(missing)}, unknown {sorted(extra)}", line=node["line"])
            deps = set()
            for arg, expr in node["args"].items():
                _expression_limit(expr)
                inferred = infer(expr, types)
                if inferred != "Any" and not compatible(inferred, cap.inputs[arg]):
                    raise NacreError("TYPE", f"{name}.{arg}: expected {cap.inputs[arg]}, received {inferred}", line=node["line"], node=node["name"])
                deps |= references(expr)
            if node["retry"] and (not cap.retry_safe or cap.effect == "write"):
                raise NacreError("RETRY", f"{name} does not permit automatic retries", line=node["line"], node=node["name"])
            actual = cap.output
            node["effect"], node["resource"] = cap.effect, cap.resource
        if actual != "Any" and not compatible(actual, node["type"]):
            raise NacreError("TYPE", f"{node['name']}: declared {node['type']}, expression produces {actual}", line=node["line"], node=node["name"])
        node["dependencies"] = sorted(deps)
    for item in verifications + emissions:
        _expression_limit(item["expr"])
        actual = infer(item["expr"], types)
        if item["kind"] == "verify" and actual not in ("Bool", "Any"):
            raise NacreError("TYPE", "verify requires a Bool expression", line=item["line"])
        item["dependencies"] = sorted(references(item["expr"]))
    # Iterative Kahn validation avoids Python recursion for long dependency chains.
    remaining = {node["name"]: set(node["dependencies"]) for node in nodes}
    complete = set()
    while remaining:
        ready = [name for name, deps in remaining.items() if deps <= complete]
        if not ready:
            raise NacreError("CYCLE", f"Dependency cycle among {', '.join(sorted(remaining))}")
        complete.update(ready)
        for name in ready: del remaining[name]
    caps_hash = fingerprint({name: cap.to_dict() for name, cap in sorted(capabilities.items())})
    return Plan(nodes, verifications, emissions, aliases, fingerprint({"source": source, "modules": modules}), caps_hash, modules)
