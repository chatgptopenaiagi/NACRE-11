"""Dependency-aware interpreter with explicit effects and journaled resume."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock
import hashlib
import json
import math
import os
import sys
import time
import uuid

from .contracts import NacreError, canonical, fingerprint, type_of, validate


def evaluate(expr, values):
    """Interpret Nacre expression nodes, with no host-language eval facility."""
    try:
        return _evaluate(expr, values)
    except NacreError as exc:
        if exc.line is None:
            exc.line = expr.get("line")
        raise
    except ArithmeticError as exc:
        raise NacreError("ARITHMETIC", str(exc), line=expr.get("line")) from None


def _evaluate(expr, values):
    kind = expr["kind"]
    if kind == "literal": return deepcopy(expr["value"])
    if kind == "ref": return deepcopy(values[expr["name"]])
    if kind == "list": return [evaluate(item, values) for item in expr["items"]]
    if kind == "record": return {key: evaluate(item, values) for key, item in expr["items"].items()}
    if kind == "index":
        base, index = evaluate(expr["base"], values), evaluate(expr["index"], values)
        if isinstance(base, (list, str)):
            if type(index) is not int or index < 0 or index >= len(base):
                raise NacreError("INDEX", "List/String index must be a nonnegative in-range Integer", line=expr["line"])
        elif isinstance(base, dict):
            if not isinstance(index, str) or index not in base:
                raise NacreError("INDEX", f"Missing record key {index!r}", line=expr["line"])
        else:
            raise NacreError("TYPE", f"Cannot index {type_of(base)}", line=expr["line"])
        return deepcopy(base[index])
    if kind == "unary":
        value, op = evaluate(expr["expr"], values), expr["op"]
        validate(value, "Bool" if op == "not" else "Number", "unary operand")
        return not value if op == "not" else +value if op == "+" else -value
    if kind == "binary":
        op, left = expr["op"], evaluate(expr["left"], values)
        if op in ("and", "or"):
            validate(left, "Bool", f"{op} left operand")
            if (op == "and" and not left) or (op == "or" and left): return left
            right = evaluate(expr["right"], values)
            validate(right, "Bool", f"{op} right operand")
            return right
        right = evaluate(expr["right"], values)
        if op in ("==", "!="):
            # Python equates True with 1; Nacre deliberately preserves nominal tags.
            same_type = type_of(left) == type_of(right) or {type_of(left), type_of(right)} <= {"Integer", "Number"}
            equal = same_type and canonical(left) == canonical(right)
            if same_type and type_of(left) in ("Integer", "Number"): equal = left == right
            return equal if op == "==" else not equal
        if op in ("<", "<=", ">", ">="):
            if isinstance(left, str) and isinstance(right, str): pass
            else:
                validate(left, "Number", "comparison left operand")
                validate(right, "Number", "comparison right operand")
            if op == "<": return left < right
            if op == "<=": return left <= right
            if op == ">": return left > right
            return left >= right
        if op == "+" and type(left) is type(right) and isinstance(left, (str, list)):
            return left + right
        validate(left, "Number", f"{op} left operand")
        validate(right, "Number", f"{op} right operand")
        if op == "+": value = left + right
        elif op == "-": value = left - right
        elif op == "*": value = left * right
        elif op == "/": value = left / right
        elif op == "%": value = left % right
        elif op == "^":
            if abs(right) > 10000:
                raise NacreError("LIMIT", "Exponent magnitude exceeds 10000", line=expr["line"])
            if isinstance(left, int) and isinstance(right, int) and right > 0 and left.bit_length() * right > 100000:
                raise NacreError("LIMIT", "Integer power exceeds 100000 bits", line=expr["line"])
            value = left ** right
        else: raise NacreError("INTERNAL", f"Unknown operator {op}")
        validate(value, "Number", "arithmetic result")
        return value
    raise NacreError("INTERNAL", f"Unknown expression node {kind}")


def _implementation_digest():
    from .identity import core_fingerprints
    source = core_fingerprints()
    try:
        from .adapters import dependency_fingerprints
        dependencies = dependency_fingerprints()
    except ImportError:
        dependencies = {}
    frozen = bool(getattr(sys, "frozen", False))
    interpreter = {"executable": str(Path(sys.executable).resolve()), "version": sys.version,
                   "base_prefix": "<bundled>" if frozen else sys.base_prefix,
                   "pointer_bits": 64 if sys.maxsize > 2**32 else 32, "frozen": frozen}
    if frozen:
        interpreter["executable_sha256"] = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    return fingerprint({"source": source, "dependencies": dependencies, "interpreter": interpreter})


def _atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise NacreError("CHECKPOINT", f"Cannot persist checkpoint: {exc.strerror or type(exc).__name__}") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class Runtime:
    def __init__(self, capabilities, invoke, workspace, workers=4):
        if type(workers) is not int or not 1 <= workers <= 32:
            raise NacreError("RESOURCE", "workers must be an integer from 1 to 32")
        self.capabilities, self.invoke = capabilities, invoke
        self.workspace, self.workers = Path(workspace).resolve(), workers
        self._resources = {}
        self._resource_guard = Lock()

    def _resource_lock(self, key):
        with self._resource_guard:
            return self._resources.setdefault(key, Lock())

    def run(self, plan, checkpoint=None, resume=False, cancel_event=None):
        """Execute a checked Plan; failures are returned as structured results.

        Resume reuses only pure nodes. External reads and writes always execute
        again. Writes never receive automatic retries or an exactly-once claim.
        """
        started = time.perf_counter()
        cancel = cancel_event or Event()
        run_id = str(uuid.uuid4())
        events, values, records, verifications, emitted = [], {}, {}, [], []
        current_contracts = fingerprint({name: cap.to_dict() for name, cap in sorted(self.capabilities.items())})
        if current_contracts != plan.capabilities_hash:
            raise NacreError("CONTRACT", "Runtime capability contracts differ from the compiled plan")
        signature = fingerprint({"source": plan.source_hash, "capabilities": plan.capabilities_hash,
                                 "implementation": _implementation_digest(), "format": "nacre-ir-1"})
        checkpoint_path = Path(checkpoint).resolve() if checkpoint else None
        cache, error, resumed = {}, None, False

        # A checkpoint is an owned runtime document, never a destination for
        # replacing an unrelated report supplied accidentally by the caller.
        if checkpoint_path is not None and checkpoint_path.exists() and not resume:
            try:
                prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                prior_digest = prior.pop("digest")
                if prior.get("format") != "nacre-checkpoint-1" or fingerprint(prior) != prior_digest:
                    raise ValueError("not an intact Nacre checkpoint")
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise NacreError("CHECKPOINT", "Existing destination is not an intact Nacre checkpoint; preserved") from exc

        def event(kind, **fields):
            events.append({"event": kind, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), **fields})

        def persist(status, error_value=None):
            if checkpoint_path is None: return
            document = {"format": "nacre-checkpoint-1", "signature": signature, "run_id": run_id,
                        "status": status, "nodes": records, "error": error_value}
            document["digest"] = fingerprint(document)
            _atomic_json(checkpoint_path, document)

        if resume:
            if checkpoint_path is None:
                raise NacreError("CHECKPOINT", "--resume requires a checkpoint path")
            try:
                document = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                digest = document.pop("digest")
                if fingerprint(document) != digest or document.get("format") != "nacre-checkpoint-1":
                    raise NacreError("CHECKPOINT", "Checkpoint integrity check failed")
                if document.get("signature") != signature:
                    raise NacreError("CHECKPOINT", "Checkpoint source, contract or implementation binding changed")
                cache = document["nodes"]
                if not isinstance(cache, dict): raise ValueError("invalid node map")
                resumed = True
            except NacreError: raise
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise NacreError("CHECKPOINT", "Cannot load a valid checkpoint") from exc

        def execute(node, snapshot):
            local_events = []
            input_hash = fingerprint({"node": node, "dependencies": {name: snapshot[name] for name in node["dependencies"]}})
            cached = cache.get(node["name"])
            if node["effect"] == "pure" and isinstance(cached, dict) and cached.get("input_hash") == input_hash:
                value = cached.get("value")
                if cached.get("value_hash") != fingerprint(value):
                    raise NacreError("CHECKPOINT", f"Cached value integrity check failed for {node['name']}")
                validate(value, node["type"], node["name"])
                return deepcopy(value), input_hash, [{"event": "cache_hit", "node": node["name"]}]
            if cancel.is_set():
                raise NacreError("CANCELLED", "Execution cancelled", node=node["name"])
            if node["kind"] == "let":
                value = evaluate(node["expr"], snapshot)
            else:
                cap = self.capabilities[node["capability"]]
                args = {key: evaluate(expr, snapshot) for key, expr in node["args"].items()}
                for key, value in args.items(): validate(value, cap.inputs[key], f"{cap.name}.{key}")
                context = {"workspace": self.workspace, "run_id": run_id, "cancel_event": cancel, "node": node["name"]}
                for attempt in range(node["retry"] + 1):
                    if cancel.is_set(): raise NacreError("CANCELLED", "Execution cancelled", node=node["name"])
                    try:
                        if cap.effect == "pure":
                            value = self.invoke(cap.name, deepcopy(args), context)
                        else:
                            with self._resource_lock(cap.resource or cap.name):
                                if cancel.is_set(): raise NacreError("CANCELLED", "Execution cancelled", node=node["name"])
                                value = self.invoke(cap.name, deepcopy(args), context)
                        validate(value, cap.output, cap.name)
                        break
                    except NacreError as exc:
                        if not exc.retryable or attempt >= node["retry"] or not cap.retry_safe or cap.effect == "write": raise
                        local_events.append({"event": "retry", "node": node["name"], "attempt": attempt + 1, "code": exc.code})
            validate(value, node["type"], node["name"])
            return deepcopy(value), input_hash, local_events

        remaining = {node["name"]: node for node in plan.nodes}
        running = {}
        persist("running")
        try:
            with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="nacre") as pool:
                while remaining or running:
                    if cancel.is_set() and error is None:
                        error = NacreError("CANCELLED", "Execution cancelled").to_dict()
                    if error is None:
                        ready = [node for node in remaining.values() if all(name in values for name in node["dependencies"])]
                        for node in ready[:max(0, self.workers - len(running))]:
                            del remaining[node["name"]]
                            event("start", node=node["name"], effect=node["effect"])
                            running[pool.submit(execute, node, deepcopy(values))] = node
                    if not running:
                        if remaining and error is None: error = NacreError("DEPENDENCY", "No runnable nodes remain").to_dict()
                        break
                    done, _ = wait(running, timeout=0.1, return_when=FIRST_COMPLETED)
                    for future in sorted(done, key=lambda f: running[f]["name"]):
                        node = running.pop(future)
                        try:
                            value, input_hash, local_events = future.result()
                            values[node["name"]] = value
                            records[node["name"]] = {"input_hash": input_hash, "value": value,
                                                       "value_hash": fingerprint(value), "effect": node["effect"]}
                            for item in local_events:
                                kind = item.pop("event")
                                event(kind, **item)
                            event("complete", node=node["name"])
                        except Exception as exc:
                            if isinstance(exc, NacreError):
                                failure = exc.to_dict()
                            elif isinstance(exc, (ZeroDivisionError, OverflowError, ArithmeticError)):
                                failure = NacreError("ARITHMETIC", str(exc)).to_dict()
                            else:
                                failure = NacreError("EXECUTION", f"{type(exc).__name__}: {exc}").to_dict()
                            failure["node"] = failure.get("node") or node["name"]
                            failure["line"] = failure.get("line") or node["line"]
                            event("failed", **failure)
                            if error is None: error = failure
                            cancel.set()
                        persist("failed" if error else "running", error)
                if error is None and cancel.is_set():
                    raise NacreError("CANCELLED", "Execution cancelled")
                if error is None:
                    for item in plan.verifications:
                        value = evaluate(item["expr"], values)
                        validate(value, "Bool", "verify")
                        verifications.append({"line": item["line"], "passed": value})
                        if not value:
                            raise NacreError("VERIFY", "Program verification failed", line=item["line"])
                    emitted = [evaluate(item["expr"], values) for item in plan.emissions]
                    for value in emitted: validate(value, "Any", "emit")
        except NacreError as exc:
            error = exc.to_dict()
            event("failed", **error)
        except Exception as exc:
            error = NacreError("EXECUTION", f"{type(exc).__name__}: {exc}").to_dict()
            event("failed", **error)
        status = "passed" if error is None else "cancelled" if error["code"] == "CANCELLED" else "failed"
        checkpoint_error = None
        try:
            persist(status, error)
        except NacreError as exc:
            checkpoint_error = exc.to_dict()
            event("failed", **checkpoint_error)
            if error is None:
                error, status = checkpoint_error, "failed"
        return {"status": status, "run_id": run_id, "results": values, "emitted": emitted,
                "verifications": verifications, "events": events, "error": error,
                "checkpoint_error": checkpoint_error,
                "resumed": resumed, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "workers": self.workers, "pending": sorted(remaining)}
