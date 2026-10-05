import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_sim import Active4XSimulation, run_intervention_matrix


SCENARIO = ROOT / "probes/active4x/two-rivers-v0.1.json"


class TwoRiversActive4XTests(unittest.TestCase):
    def load(self):
        return json.loads(SCENARIO.read_text(encoding="utf-8"))["scenario"]

    def test_baseline_has_trade_and_contested_resource_activity(self):
        result = Active4XSimulation(self.load(), "none").run()
        self.assertTrue(result["balance"]["passed"])
        self.assertEqual(
            result["first_decisions"]["kilnreach"],
            "seek_food_trade",
        )
        self.assertEqual(
            result["first_decisions"]["stoneford"],
            "claim_iron_ford",
        )
        self.assertTrue(
            any(x["kind"] == "trade_contract_created" for x in result["ledger"])
        )
        self.assertTrue(
            any(x["kind"] == "trade_contract_fulfilled" for x in result["ledger"])
        )

    def test_player_interventions_change_later_autonomous_decisions(self):
        scenario = self.load()
        matrix = run_intervention_matrix(
            scenario,
            [
                "none",
                "feed_kilnreach",
                "supply_stoneford_bricks",
                "sabotage_kilnreach_route",
            ],
        )
        signatures = {
            name: tuple(sorted(result["first_decisions"].items()))
            for name, result in matrix.items()
        }
        self.assertEqual(len(set(signatures.values())), 4)
        self.assertEqual(
            matrix["feed_kilnreach"]["first_decisions"]["kilnreach"],
            "claim_iron_ford",
        )
        self.assertEqual(
            matrix["supply_stoneford_bricks"]["first_decisions"]["stoneford"],
            "build_granary",
        )
        self.assertEqual(
            matrix["sabotage_kilnreach_route"]["first_decisions"]["kilnreach"],
            "secure_route",
        )

    def test_replay_is_deterministic(self):
        scenario = self.load()
        first = Active4XSimulation(scenario, "none").run()
        second = Active4XSimulation(scenario, "none").run()
        self.assertEqual(
            first["deterministic_digest"],
            second["deterministic_digest"],
        )
        self.assertEqual(first["state"], second["state"])
        self.assertEqual(first["ledger"], second["ledger"])

    def test_all_intervention_branches_conserve_resources(self):
        matrix = run_intervention_matrix(self.load())
        for name, result in matrix.items():
            with self.subTest(intervention=name):
                self.assertTrue(result["balance"]["passed"])

    def test_world_progresses_without_player_input(self):
        result = Active4XSimulation(self.load(), "none").run()
        production = [x for x in result["ledger"] if x["kind"] == "production_completed"]
        consumption = [x for x in result["ledger"] if x["kind"] == "consumption"]
        decisions = [x for x in result["ledger"] if x["kind"] == "decision_committed"]
        self.assertGreaterEqual(len(production), 8)
        self.assertGreaterEqual(len(consumption), 12)
        self.assertGreaterEqual(len(decisions), 6)

    def test_unknown_intervention_fails_closed(self):
        with self.assertRaises(ValueError):
            Active4XSimulation(self.load(), "magic_branch")


if __name__ == "__main__":
    unittest.main()
