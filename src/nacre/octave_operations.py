"""Bounded numerical operations through Octave Courier's public script API.

Only this package's fixed worker is executable. Parameters are JSON data, never
Octave expressions. Verification is independent Python arithmetic; it does not
turn double precision into exact decimal or arbitrary-precision transport.
"""
import cmath
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import tempfile

from .contracts import NacreError

MAX_DIMENSION = 64
ABS_TOL = 1e-9
REL_TOL = 1e-8
MIN_RCOND = 1e-10
SCHEMAS = {
    "inverse": {"a"}, "qr": {"a"}, "eigen": {"a"},
    "polynomial": {"coefficients", "points"},
    "regression": {"x", "y"}, "fft": {"values"},
}


def _fail(message, code="NUMERICAL_INPUT"):
    raise NacreError(code, message)


def _number(value):
    if type(value) not in (int, float):
        _fail("Expected finite real numbers; boolean, decimal strings and complex values are unsupported")
    if type(value) is int and abs(value) > 2**53:
        _fail("Integer input exceeds exact IEEE double range")
    if not math.isfinite(value):
        _fail("NaN and infinity are unsupported")
    return float(value)


def _vector(value, name):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_DIMENSION:
        _fail(f"{name} must be a list of 1..{MAX_DIMENSION} finite real numbers")
    return [_number(x) for x in value]


def _matrix(value, name):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_DIMENSION:
        _fail(f"{name} must have 1..{MAX_DIMENSION} rows")
    rows = [_vector(row, name) for row in value]
    if len({len(row) for row in rows}) != 1:
        _fail(f"{name} must be rectangular")
    return rows


def _encode(matrix):
    return {"rows": len(matrix), "columns": len(matrix[0]), "values": [x for row in matrix for x in row]}


def _decode(item):
    if not isinstance(item, dict) or set(item) != {"rows", "columns", "values"}:
        _fail("Worker returned an invalid matrix envelope", "NUMERICAL_RESULT")
    rows, cols = item["rows"], item["columns"]
    if type(rows) is not int or type(cols) is not int or not 1 <= rows <= MAX_DIMENSION or not 1 <= cols <= MAX_DIMENSION:
        _fail("Worker returned invalid dimensions", "NUMERICAL_RESULT")
    values = item["values"]
    # Octave jsonencode encodes a single numeric element as a scalar.
    values = [values] if type(values) in (int, float) else values
    if not isinstance(values, list) or len(values) != rows * cols:
        _fail("Worker data count disagrees with dimensions", "NUMERICAL_RESULT")
    for value in values:
        if type(value) not in (int, float) or not math.isfinite(value):
            _fail("Worker returned nonfinite or non-real output", "NUMERICAL_RESULT")
    return [values[i * cols:(i + 1) * cols] for i in range(rows)]


def _transpose(a):
    return [list(row) for row in zip(*a)]


def _product(a, b):
    if (not a or not b or not a[0] or not b[0]
            or any(len(row) != len(a[0]) for row in a)
            or any(len(row) != len(b[0]) for row in b)
            or len(a[0]) != len(b)):
        _fail("Independent product check has incompatible matrix dimensions", "NUMERICAL_VERIFICATION")
    return [[math.fsum(x * y for x, y in zip(row, column)) for column in zip(*b)] for row in a]


def _identity(n):
    return [[int(i == j) for j in range(n)] for i in range(n)]


def _compare(actual, expected, label):
    if len(actual) != len(expected) or any(len(a) != len(b) for a, b in zip(actual, expected)):
        _fail(f"Independent {label} check failed: matrix shape differs", "NUMERICAL_VERIFICATION")
    errors = []
    for row, ref in zip(actual, expected):
        for value, target in zip(row, ref):
            error = abs(value - target)
            if not math.isfinite(error) or error > ABS_TOL + REL_TOL * abs(target):
                _fail(f"Independent {label} check failed: tolerance exceeded", "NUMERICAL_VERIFICATION")
            errors.append(error)
    return {"check": label, "passed": True, "max_absolute_error": max(errors, default=0)}


def _fraction_solve(a, b):
    """Independent exact rational elimination of the represented input floats."""
    n = len(a)
    rows = [[Fraction(x) for x in row] + [Fraction(x) for x in rhs] for row, rhs in zip(a, b)]
    for k in range(n):
        pivot = next((i for i in range(k, n) if rows[i][k]), None)
        if pivot is None:
            _fail("Independent reference found a singular system", "NUMERICAL_VERIFICATION")
        rows[k], rows[pivot] = rows[pivot], rows[k]
        factor = rows[k][k]
        rows[k] = [x / factor for x in rows[k]]
        for i in range(n):
            if i != k:
                factor = rows[i][k]
                rows[i] = [x - factor * y for x, y in zip(rows[i], rows[k])]
    return [[float(x) for x in row[n:]] for row in rows]


def _condition(response):
    value = response.get("rcond")
    if type(value) not in (int, float) or not math.isfinite(value) or value <= MIN_RCOND:
        _fail("Matrix is singular or exceeds the reciprocal-condition threshold", "NUMERICAL_CONDITION")


def run(engine, operation, parameters):
    """Execute a fixed operation and return independently checked numerical data.

    inverse/qr/eigen: {a: matrix}; polynomial: {coefficients: list, points: list};
    regression: {x: full-rank design matrix, y: column matrix}; fft: {values: list}.
    """
    if operation not in SCHEMAS:
        _fail(f"Unsupported bounded operation: {operation}")
    if not isinstance(parameters, dict) or set(parameters) != SCHEMAS[operation]:
        _fail(f"{operation} requires exactly {sorted(SCHEMAS[operation])}")
    request = {"schema_version": 1, "operation": operation}
    p = {}
    for name, value in parameters.items():
        if name in {"a", "x", "y"}:
            p[name] = _matrix(value, name)
            request[name] = _encode(p[name])
        else:
            p[name] = _vector(value, name)
            request[name] = _encode([p[name]])
    if operation in {"inverse", "eigen"} and len(p["a"]) != len(p["a"][0]):
        _fail(f"{operation} requires a square matrix")
    if operation == "inverse" and len(p["a"]) > 16:
        _fail("Exact-rational inverse verification is bounded to 16 rows")
    if operation == "eigen" and p["a"] != _transpose(p["a"]):
        _fail("Eigenvalue operation accepts exactly real symmetric matrices only")
    if operation == "regression":
        if len(p["x"]) < len(p["x"][0]) or len(p["x"]) != len(p["y"]) or len(p["y"][0]) != 1:
            _fail("Regression needs rows >= columns and a matching column-vector y")
        if len(p["x"][0]) > 16:
            _fail("Exact-rational regression verification is bounded to 16 coefficients")
    worker = Path(__file__).with_suffix(".m")
    with tempfile.TemporaryDirectory(prefix="nacre-octave-") as directory:
        folder = Path(directory)
        input_path, output_path = folder / "request.json", folder / "response.json"
        input_path.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")
        execution = engine.run_script(worker, args=(str(input_path), str(output_path)), cwd=folder)
        if (execution.get("script_changed_during_execution")
                or type(execution.get("exit_code")) is not int or execution["exit_code"] != 0
                or execution.get("timed_out") is not False):
            _fail("Numerical worker identity or exit status changed", "NUMERICAL_RESULT")
        if not output_path.is_file() or output_path.stat().st_size > 1024 * 1024:
            _fail("Worker did not produce a bounded response", "NUMERICAL_RESULT")
        def invalid_constant(value):
            _fail(f"Nonfinite worker JSON constant: {value}", "NUMERICAL_RESULT")
        response = json.loads(output_path.read_text(encoding="utf-8"), parse_constant=invalid_constant)
        if response.get("schema_version") != 1 or response.get("operation") != operation:
            _fail("Worker returned mismatched operation identity", "NUMERICAL_RESULT")
        if response.get("octave_version") != engine.runtime_version:
            _fail("Worker returned mismatched GNU Octave runtime version", "NUMERICAL_RESULT")
        response_sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
    checks = []
    output = {}
    if operation == "inverse":
        _condition(response)
        result = _decode(response["result"])
        checks.append(_compare(result, _fraction_solve(p["a"], _identity(len(p["a"]))), "exact-rational inverse reference"))
        checks.append(_compare(_product(p["a"], result), _identity(len(p["a"])), "inverse residual"))
        output.update(result=result, shape=[len(result), len(result[0])], rcond=response["rcond"])
    elif operation == "qr":
        q, r = _decode(response["q"]), _decode(response["r"])
        m, n = len(p["a"]), len(p["a"][0])
        k = min(m, n)
        if [len(q), len(q[0])] != [m, k] or [len(r), len(r[0])] != [k, n]:
            _fail("QR result dimensions disagree with economy factorization", "NUMERICAL_RESULT")
        checks.append(_compare(_product(q, r), p["a"], "QR reconstruction"))
        checks.append(_compare(_product(_transpose(q), q), _identity(len(q[0])), "Q orthogonality"))
        checks.append(_compare([[r[i][j] if i > j else 0 for j in range(len(r[0]))] for i in range(len(r))], [[0] * len(r[0]) for _ in r], "R upper triangle"))
        output.update(q=q, r=r, shape=[len(p["a"]), len(p["a"][0])])
    elif operation == "eigen":
        vectors, values = _decode(response["vectors"]), _decode(response["values"])
        n = len(p["a"])
        if len(values) != n or len(values[0]) != 1 or len(vectors) != n or len(vectors[0]) != n:
            _fail("Eigen result dimensions are incompatible", "NUMERICAL_RESULT")
        checks.append(_compare(_product(p["a"], vectors), [[vectors[i][j] * values[j][0] for j in range(n)] for i in range(n)], "eigenpair residuals"))
        checks.append(_compare(_product(_transpose(vectors), vectors), _identity(n), "eigenvector orthogonality"))
        checks.append(_compare([[sum(v[0] for v in values)]], [[sum(p["a"][i][i] for i in range(n))]], "eigenvalue trace"))
        output.update(values=[v[0] for v in values], vectors=vectors, shape=[n, n])
    elif operation == "polynomial":
        result = _decode(response["result"])
        reference = []
        for point in p["points"]:
            value = Fraction(0)
            for coefficient in p["coefficients"]:
                value = value * Fraction(point) + Fraction(coefficient)
            reference.append(float(value))
        checks.append(_compare(result, [reference], "exact-rational Horner reference"))
        output.update(result=result, shape=[1, len(reference)])
    elif operation == "regression":
        _condition(response)
        coefficients = _decode(response["coefficients"])
        xt = _transpose(p["x"])
        # Fraction summation preserves the exact represented inputs in the
        # independent normal equations; no NumPy/SymPy solver is required.
        gram = [[sum(Fraction(x) * Fraction(y) for x, y in zip(a, b)) for b in xt] for a in xt]
        rhs = [[sum(Fraction(x) * Fraction(y[0]) for x, y in zip(a, p["y"]))] for a in xt]
        reference = _fraction_solve(gram, rhs)
        checks.append(_compare(coefficients, reference, "exact-rational least-squares reference"))
        fitted = _decode(response["fitted"])
        checks.append(_compare(fitted, _product(p["x"], coefficients), "regression fitted values"))
        output.update(coefficients=coefficients, fitted=fitted, rcond=response["rcond"], shape=[len(coefficients), 1])
    else:
        real, imaginary = _decode(response["real"]), _decode(response["imaginary"])
        n = len(p["values"])
        reference = [sum(value * cmath.exp(-2j * math.pi * k * t / n) for t, value in enumerate(p["values"])) for k in range(n)]
        checks.append(_compare(real, [[v.real for v in reference]], "independent O(n^2) DFT real"))
        checks.append(_compare(imaginary, [[v.imag for v in reference]], "independent O(n^2) DFT imaginary"))
        output.update(real=real[0], imaginary=imaginary[0], shape=[1, n])
    output.update(operation=operation, octave_version=response["octave_version"], execution=execution,
                  response_sha256=response_sha,
                  verification={"passed": True, "method": "independent Python arithmetic", "absolute_tolerance": ABS_TOL,
                                "relative_tolerance": REL_TOL, "checks": checks,
                                "scope": "Double-precision numerical agreement for this input; distinct from artifact integrity"})
    return output
