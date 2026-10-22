"""Synthetic, redacted original-world directed probe selection controls."""
import copy
import json
import unittest
from tools.select_legacy_directed_sensor_probe import choose
from test_scout_legacy_gameplay_mechanisms import fixture as legacy_fixture


def fixture():
    graph = legacy_fixture()
    for node in graph["nodes"]:
        node["position"] = [int(x) for x in node["node_id"].split(",")]
    return graph


class DirectedProbeTests(unittest.TestCase):
    def test_realistic_directed_press_plate_selected(self):
        selection, public = choose(fixture())
        self.assertEqual(selection["selected_count"], 1)
        self.assertEqual(selection["sensor_mode"], "pressure_plates")
        self.assertEqual(public["sensor_family"], "stone_pressure_plate")
        self.assertEqual(public["direct_command_candidate_count"], 1)
        self.assertTrue(public["player_occupancy_required"])
        self.assertFalse(public["native_runtime_qualified"])

    def test_undirected_adjacency_not_accepted(self):
        f=fixture()
        f["edges"]["direct_redstone_edges"]=[]
        with self.assertRaises(ValueError):
            choose(f)

    def test_out_of_version_schema_refused(self):
        f=fixture()
        f["schema"]="not-real"
        with self.assertRaises(ValueError):
            choose(f)

    def test_unpowered_plate_guard(self):
        f=fixture()
        f["nodes"][0]["legacy_metadata"]=1
        with self.assertRaises(ValueError):
            choose(f)

    def test_read_only_not_world_effect(self):
        f=fixture()
        f["edges"]["command_world_targets"][0]["verb"]="testforblock"
        _,public=choose(f)
        self.assertEqual(public["candidate_commands_with_direct_world_effect"],0)

    def test_summary_hides_exact_coordinates_and_raw_commands(self):
        f=fixture()
        selection,public=choose(f)
        self.assertEqual(selection["selected"][0]["node_id"],"0,1,0")
        summary=json.dumps(public)
        for text in ("0,1,0","900","/secretworld","private-test-actor","position"):
            self.assertNotIn(text, summary)

    def test_deterministic(self):
        f=fixture()
        self.assertEqual(choose(f),choose(copy.deepcopy(f)))


if __name__ == "__main__":
    unittest.main()
