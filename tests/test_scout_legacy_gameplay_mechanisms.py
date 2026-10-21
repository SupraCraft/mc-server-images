"""Pure synthetic negative/positive tests. No third-party world files."""
import copy
import json
import unittest

from tools.scout_legacy_gameplay_mechanisms import scout


def fixture():
    kinds = [
        ("0:0:0", "stone_pressure_plate"),
        ("1:0:0", "redstone_wire"),
        ("2:0:0", "command_block"),
        ("3:0:0", "sticky_piston"),
        ("4:0:0", "redstone_wire"),
    ]
    def e(source, target, edge_type):
        return {"source": source, "target": target, "edge_type": edge_type,
                "certainty": "adequate"}
    return {
        "schema": "supracraft-legacy-causal-machinery/1",
        "world_format": "legacy_anvil_pre_palette",
        "nodes": [
            {"node_id": i, "family": f, "roles": []}
            for i, f in kinds
        ],
        "edges": {
            "physical_adjacency_candidates": [
                {"a": "0:0:0", "b": "2:0:0",
                 "edge_type": "physical_adjacency_candidate"}
            ],
            "direct_redstone_edges": [
                e("0:0:0", "1:0:0", "legacy_sensor_direct_dust_power"),
                e("1:0:0", "2:0:0", "legacy_dust_downward_command_power"),
                e("1:0:0", "3:0:0", "legacy_dust_direct_component_power"),
                e("4:0:0", "3:0:0", "legacy_dust_direct_component_power"),
            ],
            "command_world_targets": [
                {"source": "2:0:0", "target": None, "target_position": [900, 50, 4],
                 "edge_type": "command_world_target"}
            ],
            "command_chain_candidates": [],
            "repeater_command_block_conduction_edges": [],
            "command_authored_redstone_edges": [],
            "container_comparator_reads": [],
            "trapped_chest_open_power_candidates": [],
        },
        "command": "/secretworld",
        "raw_actor": "private-test-actor",
    }


class CandidateScoutTests(unittest.TestCase):
    def test_composed_hypotheses_not_runtime_proof(self):
        result = scout(fixture(), version="1.8.8")
        found = {h["family"]: h for h in result["hypotheses"]}
        self.assertEqual(found["sensor_wire_command"]["structural_path_count"], 1)
        self.assertEqual(found["sensor_wire_actuator"]["structural_path_count"], 1)
        self.assertEqual(found["wire_command_world_target"]["structural_path_count"], 1)
        self.assertEqual(result["native_execution"], "NOT_RUN")
        self.assertTrue(all(not x["runtime_qualified"] for x in found.values()))

    def test_proximity_does_not_impersonate_causality(self):
        f = fixture()
        f["edges"]["direct_redstone_edges"] = []
        out = scout(f, version="1.8.8")
        self.assertTrue(all(x["structural_path_count"] == 0 for x in out["hypotheses"]))

    def test_wrong_direction_does_not_join(self):
        f = fixture()
        f["edges"]["direct_redstone_edges"][0]["source"] = "1:0:0"
        f["edges"]["direct_redstone_edges"][0]["target"] = "0:0:0"
        self.assertEqual(scout(f, version="1.8.8")["hypotheses"][0]["structural_path_count"], 0)

    def test_unqualified_version_fails_closed(self):
        with self.assertRaises(ValueError):
            scout(fixture(), version="26.3")

    def test_duplicate_node_fails_closed(self):
        f = fixture()
        f["nodes"].append(copy.deepcopy(f["nodes"][0]))
        with self.assertRaises(ValueError):
            scout(f, version="1.8.8")

    def test_unknown_edge_target_fails_closed(self):
        f = fixture()
        f["edges"]["direct_redstone_edges"][0]["target"] = "nonexistent"
        with self.assertRaises(ValueError):
            scout(f, version="1.8.8")

    def test_wrong_schema_fails_closed(self):
        f = fixture()
        f["schema"] = "other"
        with self.assertRaises(ValueError):
            scout(f, version="1.8.8")

    def test_unrecognized_edges_not_promoted(self):
        f = fixture()
        f["edges"]["direct_redstone_edges"][0]["edge_type"] = "invented_power"
        out = scout(f, version="1.8.8")
        self.assertEqual(out["unrecognized_edge_type_counts"]["invented_power"], 1)
        self.assertEqual(out["hypotheses"][0]["structural_path_count"], 0)

    def test_no_raw_source_coordinates_or_names_in_receipt(self):
        output = json.dumps(scout(fixture(), version="1.8.8"))
        for forbidden in ["0:0:0", "900", "/secretworld", "private-test-actor"]:
            self.assertNotIn(forbidden, output)

    def test_deterministic_readback(self):
        f = fixture()
        self.assertEqual(scout(f, version="1.8.8"), scout(f, version="1.8.8"))


if __name__ == "__main__":
    unittest.main()
