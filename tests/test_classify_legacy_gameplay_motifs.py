#!/usr/bin/env python3
"""Independent, source-free hard negatives for legacy gameplay motif discovery."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "tools/classify_legacy_gameplay_motifs.py"
spec = importlib.util.spec_from_file_location("legacy_gameplay_motifs", MODULE)
motifs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motifs)


def fixture():
    return {
        "schema": "supracraft-legacy-causal-machinery/1",
        "nodes": [
            {"node_id": "10,64,10", "family": "stone_pressure_plate", "command": {"secret": "do not publish"}},
            {"node_id": "11,64,10", "family": "redstone_wire", "position": [11, 64, 10]},
            {"node_id": "12,64,10", "family": "sticky_piston"},
            {"node_id": "50,64,50", "family": "chest"},
        ],
        "edges": {
            "physical_adjacency_candidates": [
                {"a": "10,64,10", "b": "11,64,10", "certainty": "weak"},
                {"a": "11,64,10", "b": "12,64,10", "certainty": "weak"},
            ],
            "oriented_signal_candidates": [
                {"source": "11,64,10", "target": "12,64,10", "certainty": "adequate"},
            ],
        },
    }


class LegacyGameplayMotifTests(unittest.TestCase):
    def test_mixed_mechanical_electrical_sensor_remains_unqualified(self):
        result = motifs.inventory(fixture())
        self.assertEqual(result["connected_candidate_count"], 1)
        self.assertEqual(result["signature_count"], 1)
        candidate = result["patterns"][0]
        self.assertTrue(candidate["cross_domain"])
        self.assertEqual(candidate["classification"], "STATIC_CANDIDATE_ONLY")
        self.assertFalse(candidate["runtime_proven"])
        self.assertFalse(candidate["uplift_accepted"])
        self.assertEqual(candidate["candidate_edge_types"], {"oriented_signal_candidates": 1})

    def test_no_coordinates_or_command_payload_leak(self):
        output = json.dumps(motifs.inventory(fixture()))
        for sensitive in ("10,64,10", "11,64,10", "[11, 64, 10]", "do not publish"):
            self.assertNotIn(sensitive, output)

    def test_node_and_edge_order_do_not_change_signature(self):
        first = fixture()
        second = copy.deepcopy(first)
        second["nodes"].reverse()
        second["edges"]["physical_adjacency_candidates"].reverse()
        self.assertEqual(motifs.inventory(first), motifs.inventory(second))

    def test_duplicate_id_rejected(self):
        g = fixture()
        g["nodes"].append(copy.deepcopy(g["nodes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            motifs.inventory(g)

    def test_unknown_endpoint_rejected(self):
        g = fixture()
        g["edges"]["physical_adjacency_candidates"][0]["b"] = "missing"
        with self.assertRaisesRegex(ValueError, "endpoint"):
            motifs.inventory(g)

    def test_rejects_summary_only_input(self):
        g = fixture()
        del g["edges"]["physical_adjacency_candidates"]
        g["largest_components"] = [{"component_id": 0}]
        with self.assertRaisesRegex(ValueError, "full adjacency"):
            motifs.inventory(g)

    def test_rejects_version_mismatched_schema(self):
        g = fixture()
        g["schema"] = "supracraft-legacy-causal-machinery/2"
        with self.assertRaisesRegex(ValueError, "schema"):
            motifs.inventory(g)

    def test_no_proven_causality_from_adjacency(self):
        g = fixture()
        g["edges"].pop("oriented_signal_candidates")
        candidate = motifs.inventory(g)["patterns"][0]
        self.assertEqual(candidate["candidate_edge_types"], {})
        self.assertFalse(candidate["runtime_proven"])
        self.assertTrue(candidate["cross_domain"])

    def test_unknown_block_family_is_not_discarded(self):
        g = fixture()
        g["nodes"][2]["family"] = "custom_mystery_block"
        candidate = motifs.inventory(g)["patterns"][0]
        self.assertEqual(candidate["domains"]["unknown"], 1)
        self.assertIn("custom_mystery_block", candidate["families"])

    def test_empty_graph_yields_no_invented_patterns(self):
        g = fixture()
        g["nodes"] = []
        g["edges"] = {"physical_adjacency_candidates": []}
        result = motifs.inventory(g)
        self.assertEqual(result["patterns"], [])
        self.assertEqual(result["signature_count"], 0)


if __name__ == "__main__":
    unittest.main()
