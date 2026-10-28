"""Optional Courier/SymPy adapters. Metadata never supplies executable code."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import importlib.util
from importlib import metadata
import json
import math
import os
from pathlib import Path
import statistics
import uuid

from .contracts import Capability, NacreError, fingerprint
from . import numerical_verify as check

OPERATIONS = {
    'matrix_product': 'octave.multiply', 'solve': 'octave.solve',
    'inverse': 'octave.inverse', 'qr': 'octave.qr', 'eigen': 'octave.eigen',
    'polynomial': 'octave.polynomial', 'regression': 'octave.regression', 'fft': 'octave.fft',
    'statistics': 'octave.statistics', 'numerical': 'octave.numerical_demo',
    'signal': 'octave.signal_demo', 'optimization': 'octave.optimization_demo', 'plot': 'octave.plot',
}


def get_capabilities():
    definitions = [
        Capability('engine.discover', {}, 'Record', 'read', 'engine-discovery', True,
                   description='Inspect installed Courier/SymPy and optional GENESIS-10 evidence; no workload executed'),
        Capability('engine.select', {'operation':'String','precision':'String','shape':'List','output':'String'}, 'Record', 'read', 'engine-discovery', True,
                   optional=('precision','shape','output'), description='Bounded binary64 Courier selector; probes runtime identity, never installs or falls back silently'),
        Capability('matrix.verify', {'a':'List','b':'List','result':'Record','operation':'String','atol':'Number','rtol':'Number'}, 'Record',
                   optional=('operation','atol','rtol'), retry_safe=True, description='Independent exact-rational product/solve reference, shape and tolerance verification'),
        Capability('symbolic.polynomial', {'coefficients':'List','action':'String'}, 'Record', 'read', 'sympy', True,
                   optional=('action',), description='Bounded univariate rational polynomial identity/derivative/integral with SymPy; coefficient representation only'),
    ]
    parameters = {
        'matrix_product': {'a':'List','b':'List'}, 'solve': {'a':'List','b':'List'},
        'inverse': {'a':'List'}, 'qr': {'a':'List'}, 'eigen': {'a':'List'},
        'polynomial': {'coefficients':'List','points':'List'}, 'regression': {'x':'List','y':'List'},
        'fft': {'values':'List'}, 'statistics': {'values':'List'},
        'numerical': {}, 'signal': {}, 'optimization': {}, 'plot': {},
    }
    for operation, name in OPERATIONS.items():
        definitions.append(Capability(name, {**parameters[operation], 'engine':'Record','timeout':'Number'}, 'Record',
            'write' if operation == 'plot' else 'read', 'octave', True if operation != 'plot' else False,
            optional=('engine','timeout'), description=f'GNU Octave through public Courier API: {operation}; independent bounded numerical checks',
            implementation='octave-courier:public-api-v0.1+nacre-numerical-v1'))
    return {item.name:item for item in definitions}


def _package(name):
    try:
        spec = importlib.util.find_spec(name)
        return spec is not None
    except (ImportError, ValueError):
        return False


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def availability():
    result = {}
    installed = _package('octave_courier')
    executable, reason = None, 'Octave Courier package is not installed'
    if installed:
        try:
            from octave_courier import discover
            executable, reason = str(discover()), ''
        except Exception as error:
            reason = str(error)
    for name in get_capabilities():
        if name.startswith('octave.') or name == 'engine.select':
            result[name] = {'available': installed and executable is not None, 'requires':['octave-courier>=0.1,<0.2','GNU Octave>=7'],
                            'executable':executable, 'reason':reason, 'scope':'Package/path discovery; not runtime or operation verification'}
        elif name == 'symbolic.polynomial':
            result[name] = {'available':_package('sympy'), 'requires':['sympy'], 'scope':'Import discovery only'}
        else:
            result[name] = {'available':True, 'requires':[], 'scope':'Portable inspection/independent verification'}
    return result


def dependency_fingerprints():
    result = {}
    for package in ('octave_courier', 'sympy'):
        if _package(package):
            spec = importlib.util.find_spec(package)
            root = Path(spec.origin).parent
            names = ('__init__.py','engine.py','discovery.py','worker.m') if package == 'octave_courier' else ('__init__.py',)
            result[package] = {name:_sha(root/name) for name in names if (root/name).is_file()}
    result['worker'] = _sha(Path(__file__).with_name('octave_operations.m'))
    result['OCTAVE_EXECUTABLE'] = os.environ.get('OCTAVE_EXECUTABLE')
    return result


def _repository_evidence():
    """Inspect configured GENESIS-10 records as evidence, never as code/routes."""
    value = os.environ.get('NACRE_GENESIS10_ROOT')
    if not value:
        return {'configured':False, 'records':[], 'scope':'No repository evidence configured'}
    path = Path(value).expanduser()/'CAPABILITY-REGISTRY.json'
    try:
        if path.stat().st_size > 20_000_000:
            raise ValueError('Registry exceeds 20 MB limit')
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        profiles = data.get('capabilities', data.get('repositories', []))
        if isinstance(profiles, dict): profiles = list(profiles.values())
        records = []
        for record in profiles:
            if any(term in json.dumps(record).lower() for term in ('nacre','octave-courier','nacre-octave')):
                records.append({'id':record.get('id'), 'last_verified':record.get('LastVerified'),
                                'scope':record.get('VerificationScope'), 'status':record.get('ExecutionStatus')})
        return {'configured':True,'path':str(path.resolve()),'sha256':_sha(path),'records':records,
                'scope':'Historical repository evidence only; current execution is checked independently'}
    except (OSError, ValueError, TypeError, AttributeError) as error:
        return {'configured':True,'records':[],'error':str(error),'scope':'Registry unavailable or malformed; no verified evidence inferred'}


def _engine(timeout=30, selected=None, operation=None):
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise NacreError('TIMEOUT', 'Numerical timeout must be finite in (0,120] seconds')
    try:
        from octave_courier import Octave, __version__
    except ImportError:
        raise NacreError('UNAVAILABLE','Install the independent Octave Courier v0.1 wheel to use numerical capabilities') from None
    if __version__.split('.')[:2] != ['0','1']:
        raise NacreError('COMPATIBILITY','This adapter requires Octave Courier 0.1.x public contracts')
    executable = None
    if selected is not None:
        if selected.get('engine') != 'octave-courier' or selected.get('operation') != operation:
            raise NacreError('ENGINE_SELECTION','Selected engine contract does not match the operation')
        executable = selected.get('executable')
        if not isinstance(executable,str) or not Path(executable).is_file() or _sha(executable) != selected.get('executable_sha256'):
            raise NacreError('ENGINE_SELECTION','Selected executable identity changed or is unavailable')
    engine = Octave(executable=executable, timeout=timeout)
    if selected is not None and engine.runtime_version != selected.get('octave_version'):
        raise NacreError('ENGINE_SELECTION','Selected runtime version changed')
    return engine


def _selection(args):
    operation = args['operation']
    if operation not in OPERATIONS:
        raise NacreError('UNAVAILABLE', f'No implemented engine for operation {operation!r}')
    if args.get('precision','binary64') != 'binary64':
        raise NacreError('PRECISION','Courier supports finite real binary64; exact/decimal/complex engines are not interchangeable')
    output = args.get('output', 'png' if operation == 'plot' else 'json')
    if output != ('png' if operation == 'plot' else 'json'):
        raise NacreError('OUTPUT_FORMAT','Requested output format has no compatible implementation')
    shape = args.get('shape',[])
    if not isinstance(shape,list) or (shape and (len(shape)!=2 or any(type(x) is not int or not 1<=x<=64 for x in shape))):
        raise NacreError('SHAPE','Requested shape must be two dimensions in 1..64')
    if shape and operation in ('solve','inverse','eigen') and shape[0] != shape[1]:
        raise NacreError('SHAPE',f'{operation} requires a square coefficient matrix')
    if shape and operation in ('solve','inverse') and shape[0] > 16:
        raise NacreError('LIMIT',f'{operation} independent rational verification is bounded to 16 rows')
    if shape and operation == 'regression' and (shape[0] < shape[1] or shape[1] > 16):
        raise NacreError('SHAPE','Regression requires rows >= columns and at most 16 coefficients')
    engine = _engine()
    return {'engine':'octave-courier','operation':operation,'capability':OPERATIONS[operation],
            'executable':str(engine.executable),'executable_sha256':_sha(engine.executable),'octave_version':engine.runtime_version,
            'courier_version':metadata.version('octave-courier'), 'precision':'binary64','output':output,'requested_shape':shape,
            'selection':{'candidates':1,'reason':'Implemented operation, finite-real contract, available public package and current runtime version probe',
                         'workload_verified':False, 'cost':'One version probe plus one fresh process per numerical call; no speed ranking',
                         'maximum_dimension':64,'parallel_policy':'Octave calls serialized per Nacre run; independent non-Octave nodes may overlap'},
            'repository_evidence':_repository_evidence()}


def _symbolic(args):
    try:
        import sympy
    except ImportError:
        raise NacreError('UNAVAILABLE','symbolic.polynomial requires an independently installed SymPy') from None
    values = args['coefficients']
    if not isinstance(values,list) or not 1 <= len(values) <= 17:
        raise NacreError('LIMIT','Polynomial requires 1..17 descending rational coefficients')
    coefficients = []
    for item in values:
        # Decimal/rational strings are parsed by Fraction, never sympify/eval.
        if type(item) not in (str,int) or len(str(item))>80:
            raise NacreError('DOMAIN','Symbolic polynomial coefficients must be bounded exact integers or rational/decimal strings')
        if isinstance(item,str) and 'e' in item.lower():
            # Fraction expands powers of ten before the rational magnitude check.
            # Bound the exponent first so a short token cannot request huge work.
            import re
            exponent = item.strip().lower().partition('e')[2]
            if not re.fullmatch(r'[+-]?[0-9](?:_?[0-9])*',exponent):
                raise NacreError('DOMAIN','Invalid rational coefficient exponent')
            if abs(int(exponent)) > 30:
                raise NacreError('LIMIT','Symbolic coefficient exponent magnitude exceeds 30')
        try: fraction = Fraction(item)
        except (ValueError, ZeroDivisionError):
            raise NacreError('DOMAIN','Invalid rational coefficient') from None
        if max(abs(fraction.numerator),fraction.denominator)>10**30:
            raise NacreError('LIMIT','Symbolic coefficient exceeds rational bound')
        coefficients.append(sympy.Rational(fraction.numerator,fraction.denominator))
    x = sympy.Symbol('x', real=True)
    polynomial = sum(c*x**(len(coefficients)-i-1) for i,c in enumerate(coefficients))
    action = args.get('action','differentiate')
    if action == 'differentiate': transformed = sympy.diff(polynomial,x)
    elif action == 'integrate': transformed = sympy.integrate(polynomial,x)
    elif action == 'identity': transformed = polynomial
    else: raise NacreError('DOMAIN','Supported polynomial actions: identity, differentiate, integrate')
    exact = sympy.Poly(transformed,x).all_coeffs()
    approximate = [float(c) for c in exact]
    if any(not math.isfinite(v) for v in approximate): raise NacreError('PRECISION','Polynomial coefficients exceed binary64')
    return {'engine':'sympy','version':sympy.__version__,'domain':'univariate real polynomial; degree <=16 input',
            'expression':str(transformed),'action':action,'coefficients':approximate,'exact_coefficients':[str(c) for c in exact],
            'conversion':'Rational to binary64 explicitly rounded; exact coefficients retained', 'integration_constant':0 if action=='integrate' else None}


def _verify(args):
    operation = args.get('operation','matrix_product')
    response = args['result']
    if not isinstance(response,dict) or 'result' not in response:
        raise NacreError('NUMERICAL_RESULT','Expected a numerical result record')
    options = {key:args.get(key,1e-10) for key in ('atol','rtol')}
    if operation == 'matrix_product': proof = check.verify_product(args['a'],args['b'],response['result'],**options)
    elif operation == 'solve': proof = check.compare(response['result'],check.solve_reference(args['a'],args['b']),**options)
    else: raise NacreError('UNAVAILABLE','Independent matrix verification supports matrix_product and solve')
    shape = response.get('shape')
    if not isinstance(shape,list) or len(shape)!=2 or any(type(dim) is not int for dim in shape) or shape != proof['shape']:
        raise NacreError('SHAPE','Declared response shape disagrees with actual matrix')
    return proof


def _invoke(name, args, context):
    if name == 'engine.discover':
        return {'operations':OPERATIONS, 'availability':availability(), 'repository_evidence':_repository_evidence(),
                'scope':'Implementation and dependency discovery; operation success must be verified on execution'}
    if name == 'engine.select': return _selection(args)
    if name == 'matrix.verify': return _verify(args)
    if name == 'symbolic.polynomial': return _symbolic(args)
    operation = next(op for op,cap in OPERATIONS.items() if cap == name)
    inputs = {k:v for k,v in args.items() if k not in ('engine','timeout')}
    # Validate shapes and exact-reference bounds before launching the engine.
    if operation == 'matrix_product':
        reference = check.product_reference(inputs['a'],inputs['b'])
        check.verify_product(inputs['a'],inputs['b'],[[0 for _ in reference[0]] for _ in reference])
    elif operation == 'solve':
        reference = check.solve_reference(inputs['a'],inputs['b'])
    elif operation == 'statistics': check.matrix(inputs['values'])
    engine = _engine(args.get('timeout',30),args.get('engine'),operation)
    selected = args.get('engine')
    if selected and selected.get('requested_shape') and operation in ('matrix_product','solve','inverse','qr','eigen','regression'):
        matrix_input = inputs['x'] if operation == 'regression' else inputs['a']
        if check.matrix(matrix_input) != selected['requested_shape']:
            raise NacreError('ENGINE_SELECTION','Input shape differs from requested selection shape')
    if operation == 'matrix_product':
        response = engine.matrix_product(inputs['a'],inputs['b'])
        response['verification'] = _verify({**inputs,'result':response})
    elif operation == 'solve':
        response = engine.solve(inputs['a'],inputs['b'])
        response['verification'] = _verify({**inputs,'result':response,'operation':'solve'})
    elif operation in ('statistics','numerical','signal','optimization'):
        response = engine.compute(operation,**inputs)
        actual = response['result']
        if operation == 'statistics':
            values = [v for row in inputs['values'] for v in row]
            expected = {'count':len(values),'mean':statistics.mean(values),'median':statistics.median(values),
                        'sample_variance':statistics.variance(values),'sample_std':statistics.stdev(values)}
            tolerances = {key:1e-10 for key in expected}
        elif operation == 'numerical':
            expected = {'integral_sin_0_pi':2,'integral_x2_0_1':1/3,'sqrt2_root':math.sqrt(2),'root_residual':0,'decay_at_one':math.exp(-1)}
            tolerances = {key:2e-8 for key in expected}
        elif operation == 'optimization':
            expected = {'location':3,'objective':7}; tolerances = {'location':1e-6,'objective':1e-10}
        else:
            expected = {'fft_real':[1,1,1,1],'fft_imag':[0,0,0,0],'fir_filter':[0.5,1,1,1],'convolution':[1,3,2]}
            tolerances = {}
        passed = all(actual.get(k)==v if isinstance(v,list) else math.isclose(actual.get(k,math.inf),v,rel_tol=1e-10,abs_tol=tolerances[k]) for k,v in expected.items())
        response['verification'] = {'passed':passed,'reference':'Python stdlib / analytical fixed-demo reference','expected':expected,
                                    'absolute_tolerances':tolerances,'relative_tolerance':1e-10,'scope':operation+' only; fixed demos accept no arbitrary expressions'}
    elif operation == 'plot':
        folder = Path(context['workspace']).resolve()/'outputs'/'plots'
        folder.mkdir(parents=True,exist_ok=True)
        output = folder/(uuid.uuid4().hex+'.png')
        response = engine.plot(output)
        response['artifact'] = {'$type':'Artifact','path':str(output),'sha256':_sha(output)}
        response['verification'] = {'passed':response['sha256']==_sha(output) and output.read_bytes()[:8]==b'\x89PNG\r\n\x1a\n',
                                    'scope':'PNG bytes, dimensions and hash; visual correctness requires separate inspection'}
    else:
        from .octave_operations import run
        response = run(engine,operation,inputs)
    if not response.get('verification',{}).get('passed'):
        raise NacreError('NUMERICAL_VERIFICATION',f'{operation} did not satisfy its independent numerical check')
    response['provenance'] = {'engine':'octave-courier','courier_version':metadata.version('octave-courier'),
                              'octave_version':engine.runtime_version,'executable':str(engine.executable),
                              'executable_sha256':_sha(engine.executable),'input_sha256':fingerprint(inputs),
                              'public_api':operation if operation in ('matrix_product','solve') else 'plot' if operation=='plot' else 'compute' if operation in ('statistics','numerical','signal','optimization') else 'run_script'}
    return response


def invoke(name,args,context):
    try:
        return _invoke(name,args,context)
    except NacreError: raise
    except ImportError as error:
        raise NacreError('UNAVAILABLE',str(error)) from None
    except Exception as error:
        # Keep Courier's public failure classes distinct without importing it for core users.
        kind = type(error).__name__
        code = {'OctaveNotFound':'UNAVAILABLE','OctaveTimeoutError':'TIMEOUT','OctaveExecutionError':'ENGINE_PROCESS',
                'ValidationError':'NUMERICAL_INPUT','OctaveError':'ENGINE_PROCESS'}.get(kind,'NUMERICAL_ERROR')
        raise NacreError(code,str(error),retryable=False) from None
