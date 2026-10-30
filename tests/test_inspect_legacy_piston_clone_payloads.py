"""Synthetic clone source material join, no original map or command execution."""
import copy
import json
import unittest

from test_inspect_legacy_piston_snapshot_inputs import graph_fixture
from tools.rank_legacy_electromechanical_witnesses import rank
from tools.inspect_legacy_piston_clone_payloads import (
    inspect, map_clone_material_source_positions, classify_materials
)


def fixture():
    g=graph_fixture()
    cid="50,70,50"
    g["nodes"].append({"node_id":cid,"position":[50,70,50],
                       "family":"command_block",
                       "command":{"verb":"clone","authored_world_state_writes":[]}})
    g["edges"]["command_world_targets"]=[
        {"source":cid,"target_kind":"source_start","target_position":[100,70,100]},
        {"source":cid,"target_kind":"source_end","target_position":[102,70,100]},
        {"source":cid,"target_kind":"destination","target_position":[0,71,0]},
    ]
    return g,rank(g)["signatures"][0]["signature_sha256"]


class CloneSourceMaterialTests(unittest.TestCase):
    def test_clone_maps_saved_source_cell_and_retains_unknown(self):
        g,sig=fixture()
        pairs=map_clone_material_source_positions(g,sig)
        self.assertEqual(pairs,[("50,70,50",(100,70,100))])
        o=inspect(g,sig,{(100,70,100):152})
        self.assertEqual(o["saved_source_material_class_counts"],{"redstone_block":1})
        self.assertEqual(o["clone_could_place_power_source_static_only"],
                         "SAVED_REDSTONE_BLOCK_SOURCE_CANDIDATE")
        self.assertEqual(o["clone_command_execution"],"NOT_OBSERVED")
        self.assertFalse(o["gameplay_promoted"])

    def test_non_redstone_clone_source_not_promoted(self):
        g,sig=fixture()
        o=inspect(g,sig,{(100,70,100):1})
        self.assertEqual(o["saved_source_material_class_counts"],
                         {"other_saved_block_id":1})
        self.assertEqual(o["clone_could_place_power_source_static_only"],
                         "NO_SAVED_REDSTONE_BLOCK_IN_MAPPED_CLONE_CELLS")

    def test_unresolved_source_cell_is_not_assumed_air(self):
        g,sig=fixture()
        o=inspect(g,sig,{})
        self.assertEqual(o["unresolved_source_cell_samples"],1)
        self.assertEqual(o["resolved_source_cell_samples"],0)
        self.assertEqual(o["saved_source_material_class_counts"],{})

    def test_clone_destination_far_from_contacts_is_not_counted(self):
        g,sig=fixture()
        g["edges"]["command_world_targets"][2]["target_position"]=[300,71,300]
        self.assertEqual(map_clone_material_source_positions(g,sig),[])

    def test_duplicate_clone_role_is_unresolved(self):
        g,sig=fixture()
        g["edges"]["command_world_targets"].append(
            copy.deepcopy(g["edges"]["command_world_targets"][2]))
        self.assertEqual(map_clone_material_source_positions(g,sig),[])

    def test_fractional_clone_bounds_cannot_match(self):
        g,sig=fixture()
        g["edges"]["command_world_targets"][0]["target_position"]=[100.5,70,100]
        self.assertEqual(map_clone_material_source_positions(g,sig),[])

    def test_non_clone_or_non_command_cannot_supply_material(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["verb"]="testforblock"
        self.assertEqual(map_clone_material_source_positions(g,sig),[])
        g["nodes"][-1]["command"]["verb"]="clone"
        g["nodes"][-1]["family"]="chest"
        self.assertEqual(map_clone_material_source_positions(g,sig),[])

    def test_saved_air_is_not_power_source(self):
        g,sig=fixture()
        out=inspect(g,sig,{(100,70,100):0})
        self.assertEqual(out["saved_source_material_class_counts"],{"air":1})
        self.assertEqual(out["clone_could_place_power_source_static_only"],
                         "NO_SAVED_REDSTONE_BLOCK_IN_MAPPED_CLONE_CELLS")

    def test_source_coordinates_and_commands_absent_from_public_output(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["body"]="AUTHOR_SECRET"
        s=json.dumps(inspect(g,sig,{(100,70,100):152}))
        for private in ("100,70,100","50,70,50","AUTHOR_SECRET",
                        '"position"','"node_id"','"target_position"'):
            self.assertNotIn(private,s)

    def test_malformed_source_graph_rejected(self):
        g,sig=fixture()
        g["schema"]="incompatible"
        with self.assertRaisesRegex(ValueError,"unaccepted"):
            inspect(g,sig,{(100,70,100):152})

    def test_extraneous_saved_block_not_falsely_sampled(self):
        out=classify_materials([("a",(1,2,3))],{(1,2,3):55,(9,8,7):152})
        self.assertEqual(out["saved_source_material_class_counts"],
                         {"redstone_wire":1})


if __name__=="__main__":
    unittest.main()
