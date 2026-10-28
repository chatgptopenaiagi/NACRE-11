"""Independent bounded finite-real checks; no numerical engine dependency."""
from fractions import Fraction
import math
from .contracts import NacreError

MAX_DIMENSION = 64


def matrix(value, name='matrix', *, input_contract=True):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_DIMENSION:
        raise NacreError('NUMERICAL_INPUT', f'{name} requires 1..64 rows')
    width = None
    for row in value:
        if not isinstance(row, list) or not 1 <= len(row) <= MAX_DIMENSION:
            raise NacreError('NUMERICAL_INPUT', f'{name} requires 1..64 columns')
        width = len(row) if width is None else width
        if width != len(row):
            raise NacreError('SHAPE', f'{name} must be rectangular')
        for item in row:
            if type(item) not in (int, float) or (input_contract and isinstance(item, int) and abs(item) > 2**53):
                raise NacreError('PRECISION', f'{name} accepts finite real binary64 values; integers must be within +/-2^53')
            try:
                finite = math.isfinite(item)
                # Octave JSON emits integral doubles without a decimal point.
                # These result tokens may exceed 2^53 while still representing
                # a finite binary64 exactly; do not apply the input safety bound.
                representable = not isinstance(item,int) or int(float(item)) == item
            except (OverflowError,ValueError):
                finite = representable = False
            if not finite:
                raise NacreError('PRECISION', f'{name} rejects NaN/infinity')
            if not representable:
                raise NacreError('PRECISION', f'{name} integer token is not exactly representable as binary64')
    return [len(value), width]


def tolerance(atol=1e-10, rtol=1e-10):
    for value in (atol, rtol):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e-4:
            raise NacreError('TOLERANCE', 'Absolute/relative tolerances must be finite in [0, 0.0001]')
    return float(atol), float(rtol)


def product_reference(a, b):
    sa, sb = matrix(a, 'a'), matrix(b, 'b')
    if sa[1] != sb[0]:
        raise NacreError('SHAPE', 'matrix_product requires a.columns == b.rows')
    return [[sum((Fraction(x)*Fraction(y) for x,y in zip(row,col)), Fraction(0))
             for col in zip(*b)] for row in a]


def compare(actual, expected, *, atol=1e-10, rtol=1e-10, exact=False):
    """Compare each binary64 value to an independent exact rational reference."""
    tolerance(atol, rtol)
    shape = matrix(actual, 'result', input_contract=False)
    if shape != [len(expected), len(expected[0])]:
        raise NacreError('SHAPE', 'Result dimensions disagree with independent reference')
    maximum, passed = Fraction(0), True
    for actual_row, expected_row in zip(actual, expected):
        for value, ref in zip(actual_row, expected_row):
            ref = Fraction(ref)
            difference = abs(Fraction(value)-ref)
            maximum = max(maximum, difference)
            bound = Fraction(0) if exact else Fraction(atol)+Fraction(rtol)*abs(ref)
            passed = passed and difference <= bound
    try:
        maximum_float = float(maximum)
    except OverflowError:
        maximum_float = None
    return {'passed': passed, 'shape': shape, 'policy': 'exact' if exact else 'absolute_plus_relative',
            'atol': 0 if exact else atol, 'rtol': 0 if exact else rtol,
            'maximum_absolute_error': maximum_float, 'reference': 'Python fractions.Fraction on exact input values'}


def verify_product(a, b, result, *, atol=1e-10, rtol=1e-10):
    reference = product_reference(a, b)
    # Exactness is promised only when every absolute accumulation fits binary64.
    integer = all(type(x) is int for row in a+b for x in row)
    safe = integer and all(sum(abs(x*y) for x,y in zip(row,col)) <= 2**53 for row in a for col in zip(*b))
    if integer and not safe:
        raise NacreError('PRECISION', 'Integer product accumulation exceeds exact binary64 range; use an exact engine')
    return compare(result, reference, atol=atol, rtol=rtol, exact=safe)


def solve_reference(a, b):
    sa, sb = matrix(a, 'a'), matrix(b, 'b')
    if sa[0] != sa[1] or sa[0] != sb[0]:
        raise NacreError('SHAPE', 'solve requires square a and matching b.rows')
    if sa[0] > 16:
        raise NacreError('LIMIT', 'Independent rational solve is bounded to 16 rows')
    n, width = sa[0], sb[1]
    work = [[Fraction(v) for v in left+right] for left,right in zip(a,b)]
    for column in range(n):
        pivot = max(range(column,n), key=lambda row: abs(work[row][column]))
        if not work[pivot][column]:
            raise NacreError('SINGULAR', 'Coefficient matrix is singular')
        work[column], work[pivot] = work[pivot], work[column]
        divisor = work[column][column]
        work[column] = [x/divisor for x in work[column]]
        for row in range(n):
            if row != column:
                factor = work[row][column]
                work[row] = [x-factor*y for x,y in zip(work[row],work[column])]
    return [row[n:n+width] for row in work]
