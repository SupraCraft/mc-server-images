import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_soak_w6 import SoakSimulation, evaluate_soak_bounds

BASE = ROOT / "probes/active4x/two-rivers-v0.1.json"
W6 = ROOT / "probes/active4x/two-rivers-w6-soak-v0.1.json"


class TwoRiversSoakW6Tests(unittest.TestCase):
    def load(self):
        base = json.loads(BASE.read_text(encoding="utf-8"))["scenario"]
        w6 = json.loads(W6.read_text(encoding="utf-8"))
        return base, w6

    def test_24h_and_72h_all_branches_stay_within_bounds(self):
        scenario, w6 = self.load()
        for horizon in w6["horizons"]:
            for branch in w6["branches"]:
                with self.subTest(horizon=horizon, branch=branch):
                    soak = SoakSimulation(scenario, branch).soak_result(horizon)
                    checks = evaluate_soak_bounds(soak, w6["bounds"])
                    self.assertTrue(all(checks.values()), checks)

    def test_replay_is_equal_after_72h(self):
        scenario, _ = self.load()
        for branch in ("none", "sabotage_kilnreach_route"):
            with self.subTest(branch=branch):
                a = SoakSimulation(scenario, branch).soak_result(72)
                b = SoakSimulation(scenario, branch).soak_result(72)
                self.assertEqual(
                    a["result"]["deterministic_digest"],
                    b["result"]["deterministic_digest"],
                )
                self.assertEqual(a["metrics"], b["metrics"])

    def test_actor_demand_is_bounded_by_in_transit_cargo(self):
        scenario, w6 = self.load()
        soak = SoakSimulation(scenario, "none").soak_result(72)
        self.assertLessEqual(
            soak["metrics"]["max_in_transit_cargo"],
            w6["bounds"]["max_promoted_actor_demand"],
        )

    def test_trade_rate_cannot_exceed_decision_reviews(self):
        scenario, w6 = self.load()
        soak = SoakSimulation(scenario, "none").soak_result(72)
        self.assertLessEqual(
            soak["metrics"]["contract_count"],
            soak["metrics"]["kilnreach_decision_count"],
        )


if __name__ == "__main__":
    unittest.main()
