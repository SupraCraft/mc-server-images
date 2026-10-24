"""Source-free Redstone clone input-root tests, including adversarial negatives."""
import copy
import json
import unittest

from test_inspect_legacy_piston_clone_modes import fixture as clone_fixture
from tools.audit_legacy_clone_input_power_roots import (
    audit, select_upstream_wire_positions, collect_neighborhoods,
    classify_snapshot, classify_authored_write_contacts,
)


def fixture():
    g,sig,_=clone_fixture()
    g["nodes"].extend([
        {"node_id":"50,71,50","position":[50,71,50],"family":"redstone_wire"},
        {"node_id":"51,71,50","position":[51,71,50],"family":"redstone_wire"},
    ])
    g["edges"]["direct_redstone_edges"]=[
        {"source":"50,71,50","target":"50,70,50",
         "edge_type":"legacy_dust_downward_command_power"},
        {"source":"51,71,50","target":"50,71,50",
         "edge_type":"legacy_dust_horizontal_connection"},
    ]
    return g,sig


class ClonePowerRootTests(unittest.TestCase):
    def test_typed_wire_roots_are_bounded(self):
        g,sig=fixture()
        positions,ports=select_upstream_wire_positions(g,sig)
        self.assertEqual(ports,1)
        self.assertEqual(positions,{(50,71,50),(51,71,50)})
        self.assertLessEqual(len(collect_neighborhoods(positions)),12)

    def test_saved_zero_wire_metadata_is_not_called_running_off(self):
        g,sig=fixture()
        p={(50,71,50):(55,0),(51,71,50):(55,0)}
        a=audit(g,sig,p)
        self.assertEqual(a["saved_upstream_wire_status_counts"],
                         {"saved_wire_power_metadata_zero":2})
        self.assertEqual(a["runtime_wire_power"],"NOT_OBSERVED")
        self.assertFalse(a["gameplay_promoted"])

    def test_saved_nonzero_wire_metadata_is_not_liveness_proof(self):
        g,sig=fixture()
        result=audit(g,sig,{(50,71,50):(55,15),(51,71,50):(55,4)})
        self.assertEqual(result["saved_upstream_wire_status_counts"],
                         {"saved_wire_power_metadata_nonzero":2})
        self.assertEqual(result["runtime_command_activation"],"NOT_OBSERVED")

    def test_nearby_torch_redstone_block_are_only_saved_contacts(self):
        g,sig=fixture()
        w,_=select_upstream_wire_positions(g,sig)
        neighbors=collect_neighborhoods(w)
        state={p:(0,0) for p in neighbors}
        state.update({p:(55,0) for p in w})
        state[(50,72,50)]=(76,0)
        state[(51,72,50)]=(152,0)
        result=audit(g,sig,state)
        self.assertEqual(result["saved_neighbor_class_counts"]["saved_lit_redstone_torch_contact"],1)
        self.assertEqual(result["saved_neighbor_class_counts"]["saved_redstone_block_contact"],1)
        self.assertEqual(result["runtime_command_activation"],"NOT_OBSERVED")

    def test_far_forged_wire_connection_not_walked(self):
        g,sig=fixture()
        g["nodes"].append({"node_id":"999,71,999","position":[999,71,999],
                           "family":"redstone_wire"})
        g["edges"]["direct_redstone_edges"].append({
            "source":"999,71,999","target":"50,71,50",
            "edge_type":"legacy_dust_horizontal_connection"})
        self.assertEqual(len(select_upstream_wire_positions(g,sig)[0]),2)

    def test_malformed_source_authored_write_rejected(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]={"verb":"setblock","authored_world_state_writes":[
            {"position":[True,71,50],"state_class":"redstone_block",
             "write_kind":"setblock"}]}
        with self.assertRaisesRegex(ValueError,"untrusted authored target"):
            audit(g,sig,{})

    def test_exact_compact_authored_contact_is_static_candidate_only(self):
        g,sig=fixture()
        g["nodes"][-1]["command"]={"verb":"setblock","authored_world_state_writes":[
            {"position":[50,72,50],"state_class":"redstone_block",
             "write_kind":"setblock"}]}
        out=audit(g,sig,{})
        self.assertEqual(out["compact_writes_at_or_near_clone_input"],
                         {"redstone_block_adjacent_upstream_wire":1})
        self.assertEqual(out["runtime_wire_power"],"NOT_OBSERVED")

    def test_no_unresolved_wire_assumed_air(self):
        g,sig=fixture()
        out=audit(g,sig,{})
        self.assertEqual(out["unresolved_upstream_wire_states"],2)
        self.assertEqual(out["resolved_six_face_neighbor_positions"],0)

    def test_invalid_schema_or_duplicate_identity_rejected(self):
        g,sig=fixture()
        g["schema"]="spoof"
        with self.assertRaisesRegex(ValueError,"unaccepted"):
            audit(g,sig,{})
        g,sig=fixture()
        g["nodes"].append(copy.deepcopy(g["nodes"][-1]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(g,sig,{})

    def test_no_privileged_coordinates_or_commands_in_aggregate(self):
        g,sig=fixture()
        g["nodes"][0]["command"]={"body":"AUTHOR_PRIVATE"}
        output=json.dumps(audit(g,sig,{}))
        for secret in ("50,71,50","51,71,50","AUTHOR_PRIVATE",
                       '"position"','"node_id"','"target_position"'):
            self.assertNotIn(secret,output)


if __name__=="__main__":
    unittest.main()
