import unittest
from tools.qualify_next_release_snapshot import CanaryRefused, choose_snapshot, normalized_snapshot_name

class CanaryTests(unittest.TestCase):
    def test_normalized_snapshot_identity(self):
        self.assertEqual(normalized_snapshot_name('26.4 Snapshot 3'),'26.4-snapshot-3')
    def test_refuse_26_5_series(self):
        with self.assertRaises(CanaryRefused):
            choose_snapshot({'latest':{'snapshot':'26.5-snapshot-1'},'versions':[]})

if __name__ == '__main__':
    unittest.main()
