import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from probe_active4x_two_rivers_w2 import compose_expansion

BASE = ROOT / "probes/active4x/two-rivers-v0.1.json"
W2 = ROOT / "probes/active4x/two-rivers-w2-expansion-v0.1.json"


class TwoRiversExpansionW2Tests(unittest.TestCase):
    def load(self):
        base = json.loads(BASE.read_text(encoding="utf-8"))["scenario"]
        w2 = json.loads(W2.read_text(encoding="utf-8"))
        return base, w2

    def test_stoneford_decision_composes_to_stone_granary_task(self):
        scenario, w2 = self.load()
        expansion = next(
            row for row in w2["expansions"]
            if row["settlement_id"] == "stoneford"
        )
        plan = compose_expansion(
            scenario, expansion, w2["shared_construction_engine"]
        )
        self.assertTrue(plan["admitted"])
        self.assertEqual(plan["decision_receipt"]["selected"]["action"], "build_granary")
        self.assertEqual(
            plan["material_lowering"]["selected_block"],
            "minecraft:stone_bricks",
        )
        self.assertEqual(
            plan["task"]["construction_engine"],
            "resource_gated_bounded_actuation",
        )

    def test_kilnreach_decision_composes_to_brickworks_task(self):
        scenario, w2 = self.load()
        expansion = next(
            row for row in w2["expansions"]
            if row["settlement_id"] == "kilnreach"
        )
        plan = compose_expansion(
            scenario, expansion, w2["shared_construction_engine"]
        )
        self.assertTrue(plan["admitted"])
        self.assertEqual(
            plan["decision_receipt"]["selected"]["action"],
            "expand_brickworks",
        )
        self.assertEqual(
            plan["material_lowering"]["selected_block"],
            "minecraft:bricks",
        )

    def test_missing_civilization_capability_fails_closed(self):
        scenario, w2 = self.load()
        expansion = json.loads(json.dumps(w2["expansions"][0]))
        expansion["selected_candidate"][
            "requires_civilization_capabilities"
        ].append("impossible_technology")
        plan = compose_expansion(
            scenario, expansion, w2["shared_construction_engine"]
        )
        self.assertFalse(plan["admitted"])
        self.assertIn(
            "impossible_technology",
            plan["missing"]["civilization_capabilities"],
        )

    def test_no_second_construction_engine(self):
        scenario, w2 = self.load()
        for expansion in w2["expansions"]:
            plan = compose_expansion(
                scenario, expansion, w2["shared_construction_engine"]
            )
            self.assertEqual(
                plan["task"]["construction_engine"],
                "resource_gated_bounded_actuation",
            )


if __name__ == "__main__":
    unittest.main()
