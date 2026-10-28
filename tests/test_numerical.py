"""Optional adapter, independent numerical policy and real-engine acceptance."""
from fractions import Fraction
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from nacre import api, numerical
from nacre import numerical_verify as check
from nacre.contracts import NacreError


class NumericalPolicyTests(unittest.TestCase):
    def test_matrix_shapes_and_nonfinite(self):
        for value in ([],[[]],[[1],[2,3]],[[True]],[[float('nan')]],[[float('inf')]],[[2**53+1]],[[1j]],[["1.2"]]):
            with self.subTest(value=value), self.assertRaises(NacreError): check.matrix(value)
        self.assertEqual(check.matrix([[1,2,3]]),[1,3])
        self.assertEqual(check.matrix([[1],[2]]),[2,1])

    def test_product_reference_and_result_corruption(self):
        a,b=[[1,2],[3,4]],[[5,6],[7,8]]
        self.assertTrue(check.verify_product(a,b,[[19,22],[43,50]])['passed'])
        self.assertFalse(check.verify_product(a,b,[[19,23],[43,50]])['passed'])
        with self.assertRaises(NacreError): check.verify_product([[2**53]],[[2]],[[0]])
        with self.assertRaises(NacreError): check.product_reference([[1,2]],[[1,2]])

    def test_relative_tolerance_and_exact_float_reference(self):
        reference=check.product_reference([[0.1]],[[0.2]])
        self.assertEqual(reference[0][0],Fraction(0.1)*Fraction(0.2))
        self.assertTrue(check.compare([[0.020000000001]],reference)['passed'])
        self.assertFalse(check.compare([[0.03]],reference)['passed'])
        for bad in (-1,float('nan'),1,True):
            with self.assertRaises(NacreError): check.compare([[1]],[[1]],atol=bad)

    def test_solve_reference(self):
        self.assertEqual(check.solve_reference([[3,1],[1,2]],[[9],[8]]),[[2],[3]])
        with self.assertRaises(NacreError): check.solve_reference([[1,2],[2,4]],[[3],[6]])
        with self.assertRaises(NacreError): check.solve_reference([[1,2]],[[3]])

    def test_core_without_optional_engine(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(numerical,'_package',return_value=False):
            self.assertEqual(api.execute('emit 42;',workspace=folder)['emitted'],[42])
            self.assertFalse(api.discover()['availability']['octave.multiply']['available'])

    def test_missing_engine_is_structured(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'OCTAVE_EXECUTABLE':str(Path(folder)/'missing')}):
            result=api.execute('task n: Record <- octave.multiply(a=[[1]],b=[[2]]);',workspace=folder)
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['error']['code'],'UNAVAILABLE')

    def test_selection_rejects_incompatible_request_before_engine(self):
        with patch.object(numerical,'_engine',side_effect=AssertionError('must not launch')):
            for args in ({'operation':'unknown'},{'operation':'solve','precision':'decimal'},
                         {'operation':'plot','output':'svg'},{'operation':'solve','shape':[0,2]}):
                with self.subTest(args=args), self.assertRaises(NacreError): numerical.invoke('engine.select',args,{})

    def test_shape_and_reference_failure_are_distinct(self):
        a={'a':[[2]],'b':[[3]],'result':{'shape':[1,1],'result':[[7]]}}
        self.assertFalse(numerical.invoke('matrix.verify',a,{})['passed'])
        a['result']['shape']=[2,1]
        with self.assertRaises(NacreError) as caught: numerical.invoke('matrix.verify',a,{})
        self.assertEqual(caught.exception.code,'SHAPE')

    def test_selected_identity_cannot_silently_fallback(self):
        selected={'engine':'octave-courier','operation':'matrix_product','executable':'missing','executable_sha256':'0'*64}
        if importlib.util.find_spec('octave_courier'):
            with self.assertRaises(NacreError) as caught: numerical._engine(selected=selected,operation='matrix_product')
            self.assertEqual(caught.exception.code,'ENGINE_SELECTION')

    def test_invalid_timeout(self):
        for value in (0,-1,121,float('inf'),True):
            with self.assertRaises(NacreError): numerical._engine(timeout=value)

    @unittest.skipUnless(importlib.util.find_spec('sympy'),'SymPy optional')
    def test_symbolic_domain_and_polynomial(self):
        result=numerical.invoke('symbolic.polynomial',{'coefficients':[3,0,2,1]}, {})
        self.assertEqual(result['exact_coefficients'],['9','0','2'])
        for values in (["__import__('os')"],[0.1],["1/0"],list(range(20))):
            with self.assertRaises(NacreError): numerical.invoke('symbolic.polynomial',{'coefficients':values},{})


@unittest.skipUnless(os.environ.get('NACRE_TEST_OCTAVE')=='1','Set NACRE_TEST_OCTAVE=1 for real Octave integration')
class LiveNumericalTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.context={'workspace':Path(self.folder.name)}

    def test_actual_program_and_receipt(self):
        source='task e: Record <- engine.select(operation="matrix_product"); task p: Record <- octave.multiply(a=[[1,2],[3,4]],b=[[5,6],[7,8]],engine=e); task v: Record <- matrix.verify(a=[[1,2],[3,4]],b=[[5,6],[7,8]],result=p); verify v.passed; emit p.result;'
        result=api.execute(source,workspace=self.folder.name)
        self.assertEqual(result['status'],'passed',result.get('error'))
        self.assertEqual(result['emitted'],[[[19,22],[43,50]]])
        self.assertTrue(result['results']['p']['provenance']['executable_sha256'])
        saved=api.save_receipt(result,self.folder.name)
        self.assertTrue(api.verify_receipt(saved['receipt'],self.folder.name)['verified'])

    def test_scalar_vector_non_square_and_solve(self):
        for a,b,expected in (([[2]],[[3]],[[6]]),([[1,2,3]],[[2],[3],[4]],[[20]]),([[1],[2]],[[3,4]],[[3,4],[6,8]])):
            result=numerical.invoke('octave.multiply',{'a':a,'b':b},self.context)
            self.assertEqual(result['result'],expected)
        result=numerical.invoke('octave.solve',{'a':[[3,1],[1,2]],'b':[[9],[8]]},self.context)
        self.assertTrue(result['verification']['passed'])

    def test_demos_statistics_plot(self):
        for name,args in (('statistics',{'values':[[1,2,3,4,5]]}),('numerical_demo',{}),('signal_demo',{}),('optimization_demo',{}),('plot',{})):
            result=numerical.invoke('octave.'+name,args,self.context)
            self.assertTrue(result['verification']['passed'])

    def test_real_timeout_process_failure_and_recovery(self):
        with self.assertRaises(NacreError) as caught:
            numerical.invoke('octave.multiply',{'a':[[1]],'b':[[2]],'timeout':0.000001},self.context)
        self.assertEqual(caught.exception.code,'TIMEOUT')
        with self.assertRaises(NacreError) as caught:
            numerical.invoke('octave.solve',{'a':[[1,1],[1,1.0000000000000002]],'b':[[1],[2]]},self.context)
        self.assertEqual(caught.exception.code,'ENGINE_PROCESS')
        self.assertEqual(numerical.invoke('octave.multiply',{'a':[[1]],'b':[[2]]},self.context)['result'],[[2]])

    def test_external_nodes_rerun_on_resume(self):
        checkpoint=Path(self.folder.name)/'checkpoint.json'
        source='task p: Record <- octave.multiply(a=[[1]],b=[[2]]); emit p.result;'
        first=api.execute(source,workspace=self.folder.name,checkpoint=checkpoint)
        second=api.execute(source,workspace=self.folder.name,checkpoint=checkpoint,resume=True)
        self.assertEqual(first['status'],second['status'])
        self.assertEqual(second['status'],'passed')
        self.assertFalse(any(e['event']=='cache_hit' and e.get('node')=='p' for e in second['events']))


if __name__=='__main__': unittest.main()
