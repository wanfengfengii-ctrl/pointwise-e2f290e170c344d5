from ledger import InvalidInput, UnknownRecord
from register.revisions import load_revision, revise
from register.shared import get_shared
from register.shifts import get_shift
from sampling.design import freeze, load_design
from sampling.protocols import register_protocol
from tests.fixtures import LedgerFixture, STATION_TABLES, counts


class TestPreparation(LedgerFixture):
    def test_fixed_revision(self):
        first = self.design('甲班', {'a': (None, 1), 'b': (None, -1)}, {'rack': ('a',)}, {'rack': 1})
        original = load_design(self.station, first)
        second_revision = revise(self.station, '甲班', {'a': (None, 15)})
        second = freeze(self.station, '甲班', second_revision, 'v1', {'rack': ('a',)}, {'rack': 1})
        old_again = freeze(self.station, '甲班', original.revision_id, 'v1', {'rack': ('a',)}, {'rack': 1})
        self.assertNotEqual(original.revision_id, second_revision)
        self.assertEqual(load_revision(self.station, second_revision).previous_revision_id, original.revision_id)
        self.assertEqual(load_design(self.station, first), original)
        self.assertEqual(load_design(self.station, old_again).layers, original.layers)
        self.assertEqual(original.layers[0].specimens[0].observation.microns, 1)
        updated = load_design(self.station, second).layers[0].specimens[0]
        self.assertEqual(updated.observation.microns, 15)
        self.assertTrue(updated.abnormal)
        self.assertEqual([row.microns for row in load_revision(self.station, second_revision).observations], [15, -1])

    def test_private_scope(self):
        left = self.design('甲班', {'same': (None, -4)}, {'layer': ('same',)}, {'layer': 1})
        right = self.design('乙班', {'same': (None, 16)}, {'layer': ('same',)}, {'layer': 1})
        a = load_design(self.station, left).layers[0].specimens[0]
        b = load_design(self.station, right).layers[0].specimens[0]
        self.assertEqual(get_shift(self.station, '甲班').shift_id, '甲班')
        self.assertEqual((a.observation.microns, b.observation.microns), (-4, 16))
        self.assertNotEqual(a.observation.specimen.physical_key, b.observation.specimen.physical_key)
        self.assertEqual((a.observation.specimen.shift_id, b.observation.specimen.shift_id), ('甲班', '乙班'))

    def test_conflicting_revision(self):
        first = revise(self.station, '甲班', {'a': (None, 1), 'x': ('rack-x', 11)})
        original = load_revision(self.station, first)
        key = original.observations[1].specimen.shared_key
        self.assertEqual(get_shared(self.station, key).registration, 'rack-x')
        before = counts(self.station, *STATION_TABLES)
        with self.assertRaises(InvalidInput):
            revise(self.station, '甲班', {'a': (None, 18), 'new': ('rack-new', 10), 'x': (None, 0)})
        self.assertEqual(counts(self.station, *STATION_TABLES), before)
        self.assertEqual(load_revision(self.station, first), original)
        next_revision = revise(self.station, '甲班', {'x': ('rack-x', 0)})
        snapshot = load_revision(self.station, next_revision)
        self.assertEqual(snapshot.previous_revision_id, first)
        self.assertEqual([row.microns for row in snapshot.observations], [1, 0])

    def test_invalid_reading_rejects_entire_batch(self):
        before = counts(self.station, *STATION_TABLES)
        for bad in ((None, False), (None, 1.5), (None, None), (None,)):
            with self.subTest(bad=bad), self.assertRaises(InvalidInput):
                revise(self.station, '甲班', {'a': (None, 0), 'b': bad})
            self.assertEqual(counts(self.station, *STATION_TABLES), before)

    def test_protocol_pin(self):
        first = self.design('甲班', {'a': (None, 10)}, {'rack': ('a',)}, {'rack': 1})
        design = load_design(self.station, first)
        register_protocol(self.station, '甲班', 'v2', 11)
        second = freeze(self.station, '甲班', design.revision_id, 'v2', {'rack': ('a',)}, {'rack': 1})
        later = load_design(self.station, second)
        self.assertEqual((design.protocol_version, later.protocol_version), ('v1', 'v2'))
        self.assertTrue(design.layers[0].specimens[0].abnormal)
        self.assertFalse(later.layers[0].specimens[0].abnormal)
        self.assertEqual(load_design(self.station, first), design)
        register_protocol(self.station, '乙班', 'other', 10)
        before = counts(self.station, 'designs', 'protocols')
        with self.assertRaises(UnknownRecord):
            freeze(self.station, '甲班', design.revision_id, 'other', {'rack': ('a',)}, {'rack': 1})
        with self.assertRaises(InvalidInput):
            freeze(self.station, '乙班', design.revision_id, 'other', {'rack': ('a',)}, {'rack': 1})
        with self.assertRaises(InvalidInput):
            register_protocol(self.station, '甲班', 'v1', 8)
        self.assertEqual(counts(self.station, 'designs', 'protocols'), before)

    def test_overquota(self):
        revision = revise(self.station, '甲班', {'a': (None, 4)})
        register_protocol(self.station, '甲班', 'v1', 10)
        before = counts(self.station, 'designs', 'design_layers', 'frame_members')
        with self.assertRaises(InvalidInput):
            freeze(self.station, '甲班', revision, 'v1', {'rack': ('a',)}, {'rack': 2})
        self.assertEqual(counts(self.station, 'designs', 'design_layers', 'frame_members'), before)

    def test_duplicate_physical(self):
        revision = revise(self.station, '甲班', {'label-a': ('x', 1), 'label-b': ('x', 2)})
        register_protocol(self.station, '甲班', 'v1', 10)
        before = counts(self.station, 'designs', 'design_layers', 'frame_members')
        with self.assertRaisesRegex(InvalidInput, 'physical specimen'):
            freeze(self.station, '甲班', revision, 'v1', {'a': ('label-a',), 'b': ('label-b',)}, {'a': 1, 'b': 1})
        self.assertEqual(counts(self.station, 'designs', 'design_layers', 'frame_members'), before)

    def test_quota_boundary(self):
        revision = revise(self.station, '甲班', {'a': (None, 0), 'b': (None, 3)})
        register_protocol(self.station, '甲班', 'v1', 10)
        layers = {'idle': ('a',), 'full': ('b',), 'empty': ()}
        good = {'idle': 0, 'full': 1, 'empty': 0}
        design = freeze(self.station, '甲班', revision, 'v1', layers, good)
        quotas = load_design(self.station, design).quotas
        self.assertEqual({quota.layer_name: quota.quota for quota in quotas}, good)
        before = counts(self.station, 'designs')
        for invalid in (dict(good, empty=1), dict(good, idle=False), {'idle': 0, 'full': 1}):
            with self.subTest(quotas=invalid), self.assertRaises(InvalidInput):
                freeze(self.station, '甲班', revision, 'v1', layers, invalid)
        self.assertEqual(counts(self.station, 'designs'), before)
