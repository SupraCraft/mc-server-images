import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_sim import Active4XSimulation
from active4x_trade_w1 import TradeDisruptionSimulation, scenario_with_trade_disruption


BASE = ROOT / "probes/active4x/two-rivers-v0.1.json"
OVERLAY = ROOT / "probes/active4x/two-rivers-w1-trade-v0.1.json"


class TwoRiversTradeW1Tests(unittest.TestCase):
    def load(self):
        base = json.loads(BASE.read_text(encoding="utf-8"))["scenario"]
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
        return base, overlay

    def test_baseline_contract_fulfills(self):
        base, _ = self.load()
        result = Active4XSimulation(base, "none").run()
        self.assertTrue(
            any(row.get("status") == "fulfilled" for row in result["state"]["contracts"].values())
        )

    def test_disruption_breaches_contract_and_conserves_resources(self):
        base, overlay = self.load()
        scenario = scenario_with_trade_disruption(base, overlay)
        result = TradeDisruptionSimulation(
            scenario, "disrupt_first_grain_caravan"
        ).run()
        self.assertTrue(result["balance"]["passed"])
        self.assertTrue(
            any(row.get("status") == "breached" for row in result["state"]["contracts"].values())
        )
        self.assertTrue(
            any(row["kind"] == "cargo_disrupted" for row in result["ledger"])
        )
        self.assertFalse(
            any(
                row["kind"] == "trade_contract_fulfilled"
                for row in result["ledger"]
            )
        )

    def test_disruption_changes_later_kilnreach_decision(self):
        base, overlay = self.load()
        scenario = scenario_with_trade_disruption(base, overlay)
        result = TradeDisruptionSimulation(
            scenario, "disrupt_first_grain_caravan"
        ).run()
        kiln = [
            row["selected"]["action"]
            for row in result["decisions"]
            if row["settlement_id"] == "kilnreach"
        ]
        self.assertGreaterEqual(len(kiln), 2)
        self.assertEqual(kiln[0], "seek_food_trade")
        self.assertEqual(kiln[1], "secure_route")

    def test_replay_equal(self):
        base, overlay = self.load()
        scenario = scenario_with_trade_disruption(base, overlay)
        a = TradeDisruptionSimulation(
            scenario, "disrupt_first_grain_caravan"
        ).run()
        b = TradeDisruptionSimulation(
            scenario, "disrupt_first_grain_caravan"
        ).run()
        self.assertEqual(a["deterministic_digest"], b["deterministic_digest"])


if __name__ == "__main__":
    unittest.main()
