"""Source-free adversarial qualification of original-world authored power hypotheses."""
import copy
import json
import unittest

from tests.test_inspect_legacy_piston_snapshot_inputs import graph_fixture
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
        self.assertIn("remain UNKNOWN",out["limitations"][1])

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
