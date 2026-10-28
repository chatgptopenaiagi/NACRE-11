"""Regression checks for independently reviewed numerical boundaries."""
import importlib.util
import unittest
from unittest.mock import patch

from nacre import numerical
from nacre import api, numerical_verify
from nacre.contracts import NacreError

class NumericalAuditTests(unittest.TestCase):
    def test_integral_binary64_output_is_distinct_from_input_integer_contract(self):
        self.assertTrue(numerical_verify.verify_product([[1e8]],[[1e8]],[[10**16]])['passed'])
        with self.assertRaises(NacreError):
            numerical_verify.matrix([[10**16]])
        for invalid in (2**53+1,10**400):
            with self.subTest(invalid=invalid),self.assertRaises(NacreError):
                numerical_verify.matrix([[invalid]],input_contract=False)

    @unittest.skipUnless(importlib.util.find_spec('sympy'),'SymPy optional')
    def test_exponent_rejected_before_fraction_expansion(self):
        with patch.object(numerical,'Fraction',side_effect=AssertionError('must reject before expansion')) as fraction:
            for token in ('1e100000000','1e-100000000','1e1_000','1e+31','1e-31'):
                with self.subTest(token=token), self.assertRaises(NacreError) as caught:
                    numerical._symbolic({'coefficients':[token]})
                self.assertEqual(caught.exception.code,'LIMIT')
            fraction.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('sympy'),'SymPy optional')
    def test_bounded_scientific_coefficient_retains_exact_value(self):
        result=numerical._symbolic({'coefficients':['1e-3','2E+2'],'action':'identity'})
        self.assertEqual(result['exact_coefficients'],['1/1000','200'])

    def test_declared_matrix_shape_requires_exact_integer_dimensions(self):
        for shape in ([True,True],[1.0,1.0],['1','1'],[1],None):
            with self.subTest(shape=shape), self.assertRaises(NacreError) as caught:
                numerical.invoke('matrix.verify',{'a':[[2]],'b':[[3]],'result':{'result':[[6]],'shape':shape}}, {})
            self.assertEqual(caught.exception.code,'SHAPE')

    def test_selector_rejects_operation_specific_shape_before_runtime(self):
        cases=[('solve',[17,17]),('inverse',[17,17]),('solve',[2,3]),('inverse',[2,3]),
               ('eigen',[2,3]),('regression',[2,3]),('regression',[20,17])]
        with patch.object(numerical,'_engine',side_effect=AssertionError('must not launch')) as engine:
            for operation,shape in cases:
                with self.subTest(operation=operation,shape=shape),self.assertRaises(NacreError):
                    numerical.invoke('engine.select',{'operation':operation,'shape':shape},{})
            engine.assert_not_called()

if __name__=='__main__': unittest.main()
