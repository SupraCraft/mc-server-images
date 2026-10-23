"""Source-free typed clone trigger input and reversed/remote hard negatives."""
import copy
import json
import unittest

from test_inspect_legacy_piston_clone_modes import fixture as clone_fixture
from tools.audit_legacy_piston_clone_triggers import audit


def fixture():
    return clone_fixture()


class CloneTriggerStaticTests(unittest.TestCase):
    def test_no_named_input_does_not_pretend_activation(self):
        g,sig,_=fixture()
        o=audit(g,sig)
        self.assertEqual(o["candidate_clone_count"],1)
        self.assertEqual(o["clones_with_typed_incoming"],0)
        self.assertEqual(o["source_trigger_classification"],
                         "NO_SUPPORTED_TYPED_CLONE_ACTIVATION_INPUT")
        self.assertEqual(o["runtime_clone_command_execution"],"NOT_OBSERVED")

    def test_named_wire_above_clone_is_static_candidate(self):
        g,sig,_=fixture()
        g["nodes"].append({"node_id":"50,71,50","position":[50,71,50],
                           "family":"redstone_wire"})
        g["edges"]["direct_redstone_edges"]=[
            {"source":"50,71,50","target":"50,70,50",
             "edge_type":"legacy_dust_downward_command_power"}]
        o=audit(g,sig)
        self.assertEqual(o["named_typed_incoming_edge_counts"],
                         {"legacy_dust_downward_command_power":1})
        self.assertEqual(o["named_reachable_upstream_wire_count"],1)
        self.assertEqual(o["source_trigger_classification"],
                         "NAMED_DIRECT_CLONE_POWER_STATIC_CANDIDATE")
        self.assertFalse(o["gameplay_promoted"])

    def test_sensor_connected_through_named_wire_is_still_static(self):
        g,sig,_=fixture()
        g["nodes"].extend([
            {"node_id":"50,71,50","position":[50,71,50],
             "family":"redstone_wire"},
            {"node_id":"51,71,50","position":[51,71,50],
             "family":"wooden_button"}])
        g["edges"]["direct_redstone_edges"]=[
            {"source":"50,71,50","target":"50,70,50",
             "edge_type":"legacy_dust_downward_command_power"},
            {"source":"51,71,50","target":"50,71,50",
             "edge_type":"legacy_sensor_direct_dust_power"}]
        o=audit(g,sig)
        self.assertEqual(o["named_reachable_sensor_count"],1)
        self.assertEqual(o["source_trigger_classification"],
                         "NAMED_LOCAL_SENSOR_TO_CLONE_STATIC_CANDIDATE")
        self.assertEqual(o["runtime_wire_power"],"NOT_OBSERVED")

    def test_reversed_wire_to_clone_edge_rejected(self):
        g,sig,_=fixture()
        g["nodes"].append({"node_id":"50,71,50","position":[50,71,50],
                           "family":"redstone_wire"})
        g["edges"]["direct_redstone_edges"]=[
            {"source":"50,70,50","target":"50,71,50",
             "edge_type":"legacy_dust_downward_command_power"}]
        self.assertEqual(audit(g,sig)["clones_with_typed_incoming"],0)

    def test_distant_forged_wire_edge_rejected(self):
        g,sig,_=fixture()
        g["nodes"].append({"node_id":"90,90,90","position":[90,90,90],
                           "family":"redstone_wire"})
        g["edges"]["direct_redstone_edges"]=[
            {"source":"90,90,90","target":"50,70,50",
             "edge_type":"legacy_dust_downward_command_power"}]
        o=audit(g,sig)
        self.assertEqual(o["clones_with_typed_incoming"],0)
        self.assertEqual(o["rejected_or_unrecognized_incoming_rows"],1)

    def test_unsupported_typed_edge_does_not_count_as_trigger(self):
        g,sig,_=fixture()
        g["nodes"].append({"node_id":"50,71,50","position":[50,71,50],
                           "family":"redstone_wire"})
        g["edges"]["direct_redstone_edges"]=[
            {"source":"50,71,50","target":"50,70,50",
             "edge_type":"invented_redstone_shortcut"}]
        o=audit(g,sig)
        self.assertEqual(o["clones_with_typed_incoming"],0)
        self.assertEqual(o["rejected_or_unrecognized_incoming_rows"],1)

    def test_sensor_in_wrong_orientation_fails_to_reach_command(self):
        g,sig,_=fixture()
        g["nodes"].extend([
            {"node_id":"50,71,50","position":[50,71,50],
             "family":"redstone_wire"},
            {"node_id":"99,99,99","position":[99,99,99],
             "family":"lever"}])
        g["edges"]["direct_redstone_edges"]=[
            {"source":"50,71,50","target":"50,70,50",
             "edge_type":"legacy_dust_downward_command_power"},
            {"source":"99,99,99","target":"50,71,50",
             "edge_type":"legacy_sensor_direct_dust_power"}]
        self.assertEqual(audit(g,sig)["named_reachable_sensor_count"],0)

    def test_duplicate_node_identity_rejected(self):
        g,sig,_=fixture()
        g["nodes"].append(copy.deepcopy(g["nodes"][-1]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            audit(g,sig)

    def test_unsupported_graph_schema_rejected(self):
        g,sig,_=fixture()
        g["schema"]="unqualified"
        with self.assertRaisesRegex(ValueError,"unaccepted"):
            audit(g,sig)

    def test_dangling_other_source_not_classified_as_trigger(self):
        g,sig,_=fixture()
        g["edges"]["direct_redstone_edges"]=[
            {"source":"bogus","target":"50,70,50",
             "edge_type":"legacy_dust_direct_component_power"}]
        self.assertEqual(audit(g,sig)["named_typed_incoming_edge_counts"],{})

    def test_public_aggregate_redacts_source_positions_and_commands(self):
        g,sig,_=fixture()
        g["nodes"][-1]["command"]["body"]="AUTHOR_SECRET"
        output=json.dumps(audit(g,sig))
        for token in ("50,70,50","100,70,100","AUTHOR_SECRET",
                      '"node_id"','"position"','"target_position"'):
            self.assertNotIn(token,output)


if __name__=="__main__":
    unittest.main()
