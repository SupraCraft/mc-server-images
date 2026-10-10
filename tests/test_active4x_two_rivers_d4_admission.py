import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_active4x_two_rivers_d4_admission import assess, HIL_CHECKS, REHEARSAL_CHECKS


def hil_receipt():
    return {
        "schema": "supracraft.active4x-two-rivers-d3-hil-result/v0.1",
        "deployment_stage": "D3_stock_client_hil", "result": "PASS",
        "minecraft": {"edition": "java", "version": "26.3", "stock_client_attested": True},
        "human_legibility_attested": True, "world_scan": False, "player": "ActualStockClient",
        "checks": {k: True for k in HIL_CHECKS}, "actor": {"result": "delivered"},
        "director": {"apply": {"accepted": True, "revision": 1}, "state": {"revision": 1}},
    }


def rehearsal_receipt():
    return {
        "schema": "supracraft.active4x-two-rivers-d3-rehearsal/v0.1",
        "deployment_stage": "D3_automated_rehearsal", "result": "PASS",
        "world_scan": False, "stock_client_hil_required": True,
        "checks": {k: True for k in REHEARSAL_CHECKS},
        "interaction_client": {"result": "PASS", "minecraft": {"edition": "java", "version": "26.3"}, "caravan": {"seen": True, "min_distance": 12.94}},
        "caravan_actor": {"result": "delivered", "amount": 4},
        "director": {"state": {"revision": 1}},
    }


class AdmissionTests(unittest.TestCase):
    def inspect(self, hil, rehearsal):
        with tempfile.TemporaryDirectory() as t:
            hp, rp = Path(t) / "hil.json", Path(t) / "rehearsal.json"
            if hil is not None:
                hp.write_text(json.dumps(hil))
            if rehearsal is not None:
                rp.write_text(json.dumps(rehearsal))
            return assess(hp, rp)

    def test_missing_human_evidence_holds(self):
        x = self.inspect(None, rehearsal_receipt())
        self.assertEqual(x["decision"], "HOLD")
        self.assertIn("hil:missing_or_invalid_json", x["reasons"])

    def test_synthetic_valid_fixture_only_eligible_for_review(self):
        x = self.inspect(hil_receipt(), rehearsal_receipt())
        self.assertEqual(x["decision"], "EVIDENCE_READY_FOR_REVIEW")

    def test_missing_human_attestation_holds(self):
        h = hil_receipt()
        h["human_legibility_attested"] = False
        self.assertEqual(self.inspect(h, rehearsal_receipt())["decision"], "HOLD")

    def test_original_checks_cannot_be_relaxed(self):
        h = hil_receipt()
        h["checks"]["logout_rejoin"] = False
        self.assertEqual(self.inspect(h, rehearsal_receipt())["decision"], "HOLD")

    def test_bot_name_cannot_count_as_human(self):
        h = hil_receipt()
        h["player"] = "TwoRiversHIL"
        self.assertIn("hil:distinct_stock_player", self.inspect(h, rehearsal_receipt())["reasons"])

    def test_wrong_client_version_holds(self):
        h = hil_receipt()
        h["minecraft"]["version"] = "26.2"
        self.assertEqual(self.inspect(h, rehearsal_receipt())["decision"], "HOLD")

    def test_nonfinite_or_far_caravan_holds(self):
        r = rehearsal_receipt()
        r["interaction_client"]["caravan"]["min_distance"] = float("nan")
        self.assertIn("rehearsal:caravan_proximity", self.inspect(hil_receipt(), r)["reasons"])
        r["interaction_client"]["caravan"]["min_distance"] = 100
        self.assertIn("rehearsal:caravan_proximity", self.inspect(hil_receipt(), r)["reasons"])

    def test_falsified_rehearsal_check_holds(self):
        r = rehearsal_receipt()
        r["checks"]["construction_obstruction_path"] = False
        self.assertEqual(self.inspect(hil_receipt(), r)["decision"], "HOLD")


if __name__ == "__main__":
    unittest.main()
