"""Predeclared H97 visual controls; no model is invoked in this test."""
import importlib.util
from pathlib import Path
import unittest

MOD = Path(__file__).resolve().parents[1] / "tools" / "interview_siglip_counterfactual_h97.py"
spec = importlib.util.spec_from_file_location("h97_visual", MOD)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class FrozenVisualPlanTests(unittest.TestCase):
    def test_fixed_cardinality_and_pairs(self):
        v.validate_plan()
        self.assertEqual(len(v.CASES), 8)
        self.assertEqual([c[0] for c in v.CASES], [
            "h01", "h02", "v01", "v02", "h03", "h04", "v03", "v04"])
    def test_counterfactuals_swap_centers_only(self):
        for i in range(0, 8, 2):
            a,b=v.CASES[i:i+2]
            self.assertEqual(a[1],b[1])
            self.assertEqual(a[3],b[4])
            self.assertEqual(a[4],b[3])
            self.assertNotEqual(a[2],b[2])
    def test_model_revision_and_weight_digest_frozen(self):
        self.assertEqual(v.REVISION, "d9049814fd748f55717e7f6e8e330574f955bd0a")
        self.assertEqual(v.WEIGHTS_SHA256, "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8")


if __name__ == "__main__":
    unittest.main()
