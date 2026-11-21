from fractions import Fraction
import json

from analysis.risk import publish
from report.retrieve import read
from tests.fixtures import LedgerFixture


def _ratios(record):
    probability = record.zero_probability
    return {
        'status': record.status,
        'condition_mass': f'{record.condition_mass.numerator}/{record.condition_mass.denominator}',
        'zero_probability': None if probability is None else f'{probability.numerator}/{probability.denominator}',
    }


class TestRisk(LedgerFixture):
    def test_shared_condition(self):
        left, right = self.main_pair()
        self.detach()
        reports = {m: publish(self.center, left, right, m) for m in (2, 1, 3)}
        m2 = reports[2].record
        self.assertEqual(
            m2.zero_probability, Fraction(1, 3),
            f'CONDITIONAL_MISS_MISMATCH m=2 actual={m2.zero_probability} expected=1/3',
        )
        self.assertEqual(m2.condition_mass, Fraction(3, 4))
        self.assertEqual(m2.status, 'reachable')
        self.assertEqual(reports[1].record.condition_mass, Fraction(1, 4))
        self.assertEqual(reports[1].record.zero_probability, Fraction(0))
        self.assertEqual(reports[1].record.status, 'reachable')
        self.assertEqual(reports[3].record.condition_mass, Fraction(0))
        self.assertIsNone(reports[3].record.zero_probability)
        self.assertEqual(reports[3].record.status, 'unreachable')
        archive = read(self.center, m2.report_id)
        self.assertEqual(archive, reports[2])
        self.assertEqual([parent.receipt_id for parent in archive.parents], [left, right])
        expected = {'status': 'reachable', 'condition_mass': '3/4', 'zero_probability': '1/3'}
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v5',
            'input': {'left': ['x abnormal', 'a normal'], 'right': ['x abnormal', 'b normal'], 'draws': [1, 1], 'm': 2},
            'expected': expected,
            'actual': _ratios(m2),
            'downstream_expected': {'result': expected, 'parents': [left, right]},
            'downstream_actual': {'result': _ratios(archive.record), 'parents': [p.receipt_id for p in archive.parents]},
            'code_paths': ['exchange/issue.py', 'exchange/intake.py', 'analysis/mass.py', 'analysis/overlap.py', 'report/retrieve.py'],
            'oracle': 'Four equally likely pairs. Drop (x,x) for m=2. Only (a,b) is clean.',
        }, sort_keys=True))

    def test_disjoint_condition(self):
        left, right = self.main_pair('y')
        self.detach()
        result = publish(self.center, left, right, 2).record
        self.assertEqual((result.status, result.condition_mass, result.zero_probability), ('reachable', Fraction(1), Fraction(1, 4)))
        self.assertEqual(publish(self.center, left, right, 1).record.status, 'unreachable')

    def test_unequal_class_mass(self):
        left = self.design(
            '甲班', {'x': ('x', 10), 'y': ('y', 0), 'bad': (None, 10), 'good': (None, 0)},
            {'rack': ('x', 'y', 'bad', 'good')}, {'rack': 2},
        )
        right = self.design('乙班', {'other-y': ('y', 0)}, {'rack': ('other-y',)}, {'rack': 1})
        a, b = self.ship(left), self.ship(right)
        self.detach()
        signed = publish(self.center, a, b, 2)
        self.assertEqual(signed.record.status, 'reachable')
        self.assertEqual(signed.record.condition_mass, Fraction(1, 2))
        self.assertEqual(signed.record.zero_probability, Fraction(1, 3))
        self.assertEqual(read(self.center, signed.record.report_id), signed)

    def test_zero_quota_and_local_flags(self):
        left = self.design(
            '甲班', {'local-x': ('x', 10), 'a': (None, 0)},
            {'idle': ('local-x',), 'active': ('a',)}, {'idle': 0, 'active': 1}, threshold=11,
        )
        right = self.design('乙班', {'own-x': ('x', 10)}, {'active': ('own-x',)}, {'active': 1}, threshold=10)
        a, b = self.ship(left), self.ship(right)
        self.detach()
        result = publish(self.center, a, b, 2).record
        self.assertEqual((result.status, result.condition_mass, result.zero_probability), ('reachable', Fraction(1), Fraction(0)))

    def test_layer_independence(self):
        left = self.design(
            '甲班', {'x': ('x', 10), 'a': (None, 0), 'y': ('y', 0), 'b': (None, 10)},
            {'lower': ('x', 'a'), 'upper': ('y', 'b')}, {'lower': 1, 'upper': 1},
        )
        right = self.design('乙班', {'X': ('x', 0), 'Y': ('y', 0)}, {'rack': ('X', 'Y')}, {'rack': 1})
        a, b = self.ship(left), self.ship(right)
        self.detach()
        result = publish(self.center, a, b, 2).record
        self.assertEqual(result.condition_mass, Fraction(1, 2))
        self.assertEqual(result.zero_probability, Fraction(1, 4))

    def test_empty_draws(self):
        left = self.design('甲班', {'a': (None, 10)}, {'empty': ()}, {'empty': 0})
        right = self.design('乙班', {'b': (None, 10)}, {'unused': ('b',)}, {'unused': 0})
        a, b = self.ship(left), self.ship(right)
        self.detach()
        result = publish(self.center, a, b, 0).record
        self.assertEqual((result.status, result.condition_mass, result.zero_probability), ('reachable', Fraction(1), Fraction(1)))
