"""Synthetic only: original Anvil source never loaded during tests."""
import copy
import json
import unittest

from tools.inspect_legacy_piston_snapshot_inputs import (
    inspect, select_component_wires, summarize_contacts,
)
from tools.rank_legacy_electromechanical_witnesses import rank


def graph_fixture():
    return {
        "schema":"supracraft-legacy-causal-machinery/1",
        "nodes":[
            {"node_id":"0,70,0","position":[0,70,0],"family":"redstone_wire"},
            {"node_id":"1,70,0","position":[1,70,0],"family":"repeater_off",
             "metadata_semantics":{"facing_vector":[-1,0,0]}},
            {"node_id":"2,70,0","position":[2,70,0],"family":"sticky_piston",
             "metadata_semantics":{"facing_vector":[1,0,0]}},
        ],
        "edges":{
            "physical_adjacency_candidates":[
                {"a":"0,70,0","b":"1,70,0"},
                {"a":"1,70,0","b":"2,70,0"},
            ],
            "direct_redstone_edges":[],
            "oriented_signal_candidates":[
                {"source":"0,70,0","target":"1,70,0",
                 "edge_type":"oriented_rear_input_candidate"},
                {"source":"1,70,0","target":"2,70,0",
                 "edge_type":"oriented_front_output_candidate"},
            ],
        },
    }


class OriginalSnapshotSourceTests(unittest.TestCase):
    def inputs(self):
        g=graph_fixture()
        sig=rank(g)["signatures"][0]["signature_sha256"]
        return g,sig

    def test_original_signature_selects_one_wire_component(self):
        g,sig=self.inputs()
        self.assertEqual(select_component_wires(g,sig),[((0,70,0),)])

    def test_snapshot_source_is_only_contact_not_power_proof(self):
        g,sig=self.inputs()
        r=inspect(g,sig,{(0,71,0):152,(0,69,0):76})
        self.assertEqual(r["component_count"],1)
        self.assertEqual(r["saved_six_face_contact_samples"],6)
        self.assertEqual(r["source_class_contact_counts"]["saved_redstone_block_contact"],1)
        self.assertEqual(r["source_class_contact_counts"]["saved_lit_redstone_torch_contact"],1)
        self.assertEqual(r["actual_power_transfer"],"NOT_OBSERVED")
        self.assertFalse(r["causal_power_or_motion_proven"])

    def test_no_saved_block_contacts_does_not_claim_no_mechanism(self):
        g,sig=self.inputs()
        r=inspect(g,sig,{})
        self.assertEqual(r["saved_adjacent_redstone_block_contacts"],0)
        self.assertEqual(r["unresolved_snapshot_contact_samples"],6)
        self.assertEqual(r["saved_direct_block_source_status"],
                         "NO_SAVED_ADJACENT_REDSTONE_BLOCK_IN_SAMPLED_SIX_FACES")
        self.assertEqual(r["original_version_native_execution"],"NOT_RUN")

    def test_adjacent_ordinary_material_not_a_power_source(self):
        g,sig=self.inputs()
        r=inspect(g,sig,{(1,70,0):93,(0,69,0):1})
        self.assertFalse(r["source_class_contact_counts"])
        self.assertEqual(r["saved_adjacent_redstone_block_contacts"],0)

    def test_forged_distant_physical_component_rejected(self):
        g,sig=self.inputs()
        g["edges"]["physical_adjacency_candidates"][0]["b"]="2,70,0"
        with self.assertRaisesRegex(ValueError,"physical adjacency"):
            select_component_wires(g,sig)

    def test_wrong_signature_rejected(self):
        g,_=self.inputs()
        with self.assertRaises(ValueError):
            select_component_wires(g,"f"*64)

    def test_no_coordinate_command_or_world_content_leak(self):
        g,sig=self.inputs()
        g["nodes"].append({"node_id":"99,70,99","family":"chest",
                           "command":{"body":"SOURCE_SECRET"}})
        saved={(0,71,0):152}
        report=json.dumps(inspect(g,sig,saved))
        for token in ("0,70,0","99,70,99","SOURCE_SECRET",'"node_id"','"position"'):
            self.assertNotIn(token,report)

    def test_aggregate_repeatability_when_component_order_changes(self):
        wires=[((0,70,0),),((100,70,0),)]
        saved={(0,71,0):152,(100,69,0):152}
        self.assertEqual(summarize_contacts(wires,saved),
                         summarize_contacts(list(reversed(wires)),saved))


if __name__=="__main__":
    unittest.main()
