"""H98 first-run temporal CLAP fixture contract; no model inference in tests."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "interview_clap_temporal_h98.py"
spec = importlib.util.spec_from_file_location("h98_temporal", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FrozenTemporalTests(unittest.TestCase):
    def test_fixed_plan_and_model(self):
        m.validate_plan()
        self.assertEqual(m.MODEL_REVISION, "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a")
        self.assertEqual(m.WEIGHTS_SHA256, "1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb")
        self.assertEqual(len(m.PAIRS), 4)
        self.assertEqual(m.SR, 48000)
        self.assertEqual(m.SEGMENT_SECONDS, 2)

    @unittest.skipUnless(importlib.util.find_spec("numpy") is not None,
                         "optional NumPy: dedicated H98 audio job pins and runs this test")
    def test_exact_audio_counterfactuals_are_deterministic(self):
        import numpy as np
        first, second = m.fixtures(), m.fixtures()
        self.assertEqual(len(first), 8)
        hashes = set()
        by_pair = {}
        for a, b in zip(first, second):
            self.assertEqual(a["id"], b["id"])
            self.assertTrue(np.array_equal(a["wave"], b["wave"]))
            self.assertEqual(a["wave"].dtype, np.float32)
            self.assertEqual(len(a["wave"]), m.SR * m.SEGMENT_SECONDS * 2)
            self.assertLessEqual(float(np.max(np.abs(a["wave"]))), 1.0)
            digest = hashlib.sha256(a["wave"].tobytes()).hexdigest()
            self.assertNotIn(digest, hashes)
            hashes.add(digest)
            by_pair.setdefault(a["pair"], []).append(a)
        self.assertEqual(len(hashes), 8)
        for pair, (a, b) in by_pair.items():
            self.assertEqual(a["reference"], "first_a")
            self.assertEqual(b["reference"], "first_b")
            self.assertEqual(a["first_sound"], b["second_sound"])
            self.assertEqual(a["second_sound"], b["first_sound"])
            self.assertTrue(np.array_equal(a["wave"][:m.SR * m.SEGMENT_SECONDS],
                                           b["wave"][m.SR * m.SEGMENT_SECONDS:]))
            self.assertTrue(np.array_equal(a["wave"][m.SR * m.SEGMENT_SECONDS:],
                                           b["wave"][:m.SR * m.SEGMENT_SECONDS]))
            self.assertEqual(a["captions"], b["captions"])

    def test_prompts_frozen_distinct(self):
        for key,a,b,p1,p2 in m.PAIRS:
            self.assertNotEqual(p1,p2)
            self.assertIn("followed by",p1)
            self.assertIn("followed by",p2)


if __name__ == "__main__":
    unittest.main()
