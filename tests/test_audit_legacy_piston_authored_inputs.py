"""Source-free adversarial qualification of original-world authored power hypotheses."""
import copy
import json
import unittest

from test_inspect_legacy_piston_snapshot_inputs import graph_fixture
from tools.rank_legacy_electromechanical_witnesses import rank
from tools.audit_legacy_piston_authored_inputs import audit


def fixture():
    g=graph_fixture()
    g["nodes"].append({
        "node_id":"50,70,50","position":[50,70,50],
        "family":"command_block",
        "command":{"verb":"setblock","authored_world_state_writes":[
            {"position":[0,71,0],"state_class":"redstone_block",
             "write_kind":"setblock"},
        ]},
    })
    sig=rank(g)["signatures"][0]["signature_sha256"]
    return g,sig


class AuthoredRedstonePowerTests(unittest.TestCase):
    def test_explicit_original_setblock_next_to_wire_is_only_static(self):
        g,sig=fixture()
        out=audit(g,sig)
        self.assertEqual(out["source_authored_relevant_write_counts"],
                         {"redstone_block_six_face_wire_contact":1})
        self.assertEqual(out["source_dynamic_input_classification"],
                         "SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT_STATIC_CANDIDATE")
        self.assertEqual(out["original_native_execution"],"NOT_RUN")
        self.assertFalse(out["gameplay_promoted"])

    def test_repeater_rear_position_is_distinct_named_contact(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["authored_world_state_writes"][0]["position"]=[0,70,0]
        out=audit(g,sig)
        self.assertEqual(out["source_authored_relevant_write_counts"],
                         {"redstone_block_repeater_rear_position":1})

    def test_far_target_is_not_source_input(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["authored_world_state_writes"][0]["position"]=[100,70,100]
        self.assertEqual(audit(g,sig)["source_authored_relevant_write_counts"],{})
        self.assertEqual(audit(g,sig)["source_dynamic_input_classification"],
                         "NO_COMPACT_SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT")

    def test_air_write_does_not_claim_power(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["authored_world_state_writes"][0]["state_class"]="air"
        out=audit(g,sig)
        self.assertEqual(out["source_authored_relevant_write_counts"],
                         {"air_six_face_wire_contact":1})
        self.assertEqual(out["source_dynamic_input_classification"],
                         "NO_COMPACT_SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT")

    def test_spoofed_command_writer_verb_rejected(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["verb"]="testforblock"
        with self.assertRaisesRegex(ValueError,"non-setblock"):
            audit(g,sig)

    def test_noncommand_node_cannot_introduce_authored_input(self):
        g,sig=fixture()
        g["nodes"][-1]["family"]="chest"
        out=audit(g,sig)
        self.assertEqual(out["source_authored_compact_setblock_write_count"],0)

    def test_unsupported_fill_is_unknown_not_silent_safe(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]={"verb":"fill",
                                 "authored_world_state_writes":[]}
        out=audit(g,sig)
        self.assertEqual(out["unsupported_fill_clone_execute_command_count"],1)
        self.assertEqual(out["source_dynamic_input_classification"],
                         "NO_COMPACT_SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT")
        self.assertIn("UNKNOWN",out["limitations"][2])

    def test_malformed_target_fails_closed(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["authored_world_state_writes"][0]["position"]=[True,71,0]
        with self.assertRaisesRegex(ValueError,"target"):
            audit(g,sig)

    def test_duplicate_authored_write_rejected(self):
        g,sig=fixture()
        a=g["nodes"][-1]["command"]["authored_world_state_writes"]
        a.append(copy.deepcopy(a[0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(g,sig)

    def test_reversible_location_and_command_not_exported(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]["body"]="PRIVATE WORLD AUTHOR STRING"
        s=json.dumps(audit(g,sig))
        for forbidden in ("0,71,0","50,70,50","PRIVATE WORLD AUTHOR STRING",
                          '"node_id"','"position"','"target_position"'):
            self.assertNotIn(forbidden,s)

    def test_fill_footprint_intersection_is_candidate_not_power(self):
        g,sig=fixture()
        cmd=g["nodes"][-1]
        cmd["command"]={"verb":"fill","authored_world_state_writes":[]}
        g["edges"]["command_world_targets"]=[
            {"source":cmd["node_id"],"target_kind":"region_start",
             "target_position":[0,71,0]},
            {"source":cmd["node_id"],"target_kind":"region_end",
             "target_position":[1,71,0]},
        ]
        out=audit(g,sig)
        self.assertEqual(out["spatial_write_footprint_candidate_overlaps"],
                         {"fill_candidate_wire_contact_overlap":1})
        self.assertEqual(out["resolved_spatial_write_footprints"],
                         {"fill_resolved_target_footprint":1})
        self.assertEqual(out["actual_redstone_power"],"NOT_OBSERVED")

    def test_clone_destination_intersection_is_unknown_material(self):
        g,sig=fixture()
        cmd=g["nodes"][-1]
        cmd["command"]={"verb":"clone","authored_world_state_writes":[]}
        g["edges"]["command_world_targets"]=[
            {"source":cmd["node_id"],"target_kind":"source_start",
             "target_position":[100,64,100]},
            {"source":cmd["node_id"],"target_kind":"source_end",
             "target_position":[102,64,102]},
            {"source":cmd["node_id"],"target_kind":"destination",
             "target_position":[0,71,0]},
        ]
        out=audit(g,sig)
        self.assertEqual(out["spatial_write_footprint_candidate_overlaps"],
                         {"clone_candidate_wire_contact_overlap":1})
        self.assertFalse(out["gameplay_promoted"])

    def test_distant_fill_intersection_not_inferred(self):
        g,sig=fixture()
        cmd=g["nodes"][-1]
        cmd["command"]={"verb":"fill","authored_world_state_writes":[]}
        g["edges"]["command_world_targets"]=[
            {"source":cmd["node_id"],"target_kind":"region_start",
             "target_position":[100,60,100]},
            {"source":cmd["node_id"],"target_kind":"region_end",
             "target_position":[102,63,102]},
        ]
        out=audit(g,sig)
        self.assertEqual(out["spatial_write_footprint_candidate_overlaps"],{})
        self.assertEqual(out["resolved_spatial_write_footprints"],
                         {"fill_resolved_target_footprint":1})

    def test_duplicate_fill_role_is_unresolved_not_joined(self):
        g,sig=fixture()
        cmd=g["nodes"][-1]
        cmd["command"]={"verb":"fill","authored_world_state_writes":[]}
        g["edges"]["command_world_targets"]=[
            {"source":cmd["node_id"],"target_kind":"region_start",
             "target_position":[0,71,0]},
            {"source":cmd["node_id"],"target_kind":"region_start",
             "target_position":[1,71,0]},
            {"source":cmd["node_id"],"target_kind":"region_end",
             "target_position":[2,71,0]},
        ]
        out=audit(g,sig)
        self.assertEqual(out["unresolved_spatial_commands"],
                         {"fill_unresolved_bounds":1})
        self.assertEqual(out["spatial_write_footprint_candidate_overlaps"],{})

    def test_fractional_and_boolean_target_bounds_are_not_rounded(self):
        for inval in (True,0.5):
            with self.subTest(inval=inval):
                g,sig=fixture()
                cmd=g["nodes"][-1]
                cmd["command"]={"verb":"fill","authored_world_state_writes":[]}
                g["edges"]["command_world_targets"]=[
                    {"source":cmd["node_id"],"target_kind":"region_start",
                     "target_position":[inval,71,0]},
                    {"source":cmd["node_id"],"target_kind":"region_end",
                     "target_position":[2,71,0]},
                ]
                self.assertEqual(audit(g,sig)["unresolved_spatial_commands"],
                                 {"fill_unresolved_bounds":1})

    def test_spatial_source_coordinates_omitted_from_public_output(self):
        g,sig=fixture()
        cmd=g["nodes"][-1]
        cmd["command"]={"verb":"fill","authored_world_state_writes":[]}
        g["edges"]["command_world_targets"]=[
            {"source":cmd["node_id"],"target_kind":"region_start",
             "target_position":[0,71,0]},
            {"source":cmd["node_id"],"target_kind":"region_end",
             "target_position":[1,71,0]},
        ]
        output=json.dumps(audit(g,sig))
        for private in ("50,70,50","0,71,0",'"target_position"','"node_id"'):
            self.assertNotIn(private,output)

    def test_unsupported_schema_rejected(self):
        g,sig=fixture()
        g["schema"]="unknown"
        with self.assertRaisesRegex(ValueError,"unaccepted"):
            audit(g,sig)

    def test_wrong_signature_rejected(self):
        g,_=fixture()
        with self.assertRaises(ValueError):
            audit(g,"a"*64)


if __name__=="__main__":
    unittest.main()
