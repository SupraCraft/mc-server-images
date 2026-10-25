"""Source-only adversarial typed sensor→command route qualification."""
import copy
import json
import unittest

from tools.rank_legacy_typed_sensor_command_witnesses import rank


def node(family, pos, **extra):
    n={"node_id":",".join(str(v) for v in pos),"position":list(pos),"family":family}
    n.update(extra)
    return n


def edge(a,b,k):
    return {"source":",".join(str(v) for v in a),
            "target":",".join(str(v) for v in b),
            "edge_type":k}


def fixture():
    s=(0,70,0);w=(1,70,0); w2=(2,70,0); c=(2,69,0)
    n=[node("wooden_button",s),node("redstone_wire",w),
       node("redstone_wire",w2),node("command_block",c)]
    es=[
        edge(s,w,"legacy_sensor_direct_dust_power"),
        edge(w,w2,"legacy_dust_horizontal_connection"),
        edge(w2,c,"legacy_dust_downward_command_power"),
    ]
    return {"schema":"supracraft-legacy-causal-machinery/1",
            "nodes":n,"edges":{"direct_redstone_edges":es}}


class SensorCommandWitnessTests(unittest.TestCase):
    def test_exact_sensor_wire_to_command_route_counts_as_static_candidate(self):
        out=rank(fixture())
        self.assertEqual(out["accepted_sensor_command_path_counts"],
                         {"wire_path_wooden_button":1})
        self.assertEqual(out["source_sensor_count"],1)
        self.assertEqual(out["target_command_count"],1)
        self.assertEqual(out["runtime_native_sensor_activation"],"NOT_RUN")
        self.assertFalse(out["gameplay_promoted"])

    def test_reverse_wire_edge_does_not_bridge(self):
        g=fixture()
        g["edges"]["direct_redstone_edges"][1]=edge((2,70,0),(1,70,0),
                                             "legacy_dust_horizontal_connection")
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_reverse_wire_command_edge_does_not_bridge(self):
        g=fixture()
        g["edges"]["direct_redstone_edges"][2]=edge((2,69,0),(2,70,0),
                                              "legacy_dust_downward_command_power")
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_fake_long_distance_named_edge_is_not_a_path(self):
        g=fixture()
        g["nodes"][2]["node_id"]="101,70,0"
        g["nodes"][2]["position"]=[101,70,0]
        g["edges"]["direct_redstone_edges"][1]=edge((1,70,0),(101,70,0),
                                             "legacy_dust_horizontal_connection")
        g["edges"]["direct_redstone_edges"][2]=edge((101,70,0),(2,69,0),
                                              "legacy_dust_downward_command_power")
        o=rank(g)
        self.assertEqual(o["accepted_path_count"],0)
        self.assertGreaterEqual(o["rejected_typed_edge_counts"]["invalid_typed_port_or_orientation"],1)

    def test_unsupported_sensor_family_does_not_create_an_input(self):
        g=fixture()
        g["nodes"][0]["family"]="chest"
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_button_exact_support_command_direct_candidate(self):
        g={"schema":"supracraft-legacy-causal-machinery/1","nodes":[
            node("wooden_button",(0,70,0),
                 metadata_semantics={"support_vector":[1,0,0]}),
            node("command_block",(1,70,0))],
           "edges":{"direct_redstone_edges":[
               edge((0,70,0),(1,70,0),"legacy_button_attached_support_power")]}}
        r=rank(g)
        self.assertEqual(r["accepted_sensor_command_path_counts"],
                         {"direct_support_wooden_button":1})
        self.assertEqual(r["source_sensor_count"],1)

    def test_wrong_button_support_vector_is_rejected(self):
        g={"schema":"supracraft-legacy-causal-machinery/1","nodes":[
            node("stone_button",(0,70,0),
                 metadata_semantics={"support_vector":[-1,0,0]}),
            node("command_block",(1,70,0))],
           "edges":{"direct_redstone_edges":[
               edge((0,70,0),(1,70,0),"legacy_button_attached_support_power")]}}
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_pressure_plate_requires_support_down_direction(self):
        g={"schema":"supracraft-legacy-causal-machinery/1","nodes":[
            node("stone_pressure_plate",(0,70,0),
                 metadata_semantics={"support_vector":[0,-1,0]}),
            node("command_block",(0,69,0))],
           "edges":{"direct_redstone_edges":[
               edge((0,70,0),(0,69,0),"legacy_pressure_plate_support_power")]}}
        self.assertEqual(rank(g)["accepted_sensor_command_path_counts"],
                         {"direct_support_stone_pressure_plate":1})
        g["nodes"][0]["metadata_semantics"]["support_vector"]=[0,1,0]
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_same_level_wire_to_command_only_on_horizontal_face(self):
        g=fixture()
        g["nodes"][-1]["node_id"]="3,70,0"
        g["nodes"][-1]["position"]=[3,70,0]
        g["edges"]["direct_redstone_edges"][2]=edge((2,70,0),(3,70,0),
                                               "legacy_dust_direct_component_power")
        self.assertEqual(rank(g)["accepted_path_count"],1)
        g["edges"]["direct_redstone_edges"][2]=edge((2,70,0),(3,70,0),
                                               "legacy_dust_downward_command_power")
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_generic_proximity_edges_are_ignored(self):
        g=fixture()
        g["edges"]["direct_redstone_edges"]=[]
        g["edges"]["physical_adjacency_candidates"]=[
          {"a":"0,70,0","b":"1,70,0"},
          {"a":"1,70,0","b":"2,70,0"},
          {"a":"2,70,0","b":"2,69,0"},
        ]
        self.assertEqual(rank(g)["accepted_path_count"],0)

    def test_duplicate_node_id_fails_closed(self):
        g=fixture()
        g["nodes"].append(copy.deepcopy(g["nodes"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            rank(g)

    def test_forged_source_coordinates_fails_closed(self):
        g=fixture()
        g["nodes"][0]["position"]=[200,70,0]
        with self.assertRaisesRegex(ValueError,"unverifiable"):
            rank(g)

    def test_missing_named_direct_edges_fails_closed(self):
        g=fixture()
        del g["edges"]["direct_redstone_edges"]
        with self.assertRaisesRegex(ValueError,"collection missing"):
            rank(g)

    def test_public_aggregate_redacts_original_positions_and_commands(self):
        g=fixture()
        g["nodes"][-1]["command"]={"body":"PRIVATE ORIGINAL AUTHOR COMMAND"}
        o=json.dumps(rank(g))
        for secret in ("0,70,0","2,69,0","PRIVATE ORIGINAL AUTHOR COMMAND",
                       '"node_id"','"position"','"target_position"'):
            self.assertNotIn(secret,o)

    def test_source_schema_rejected(self):
        g=fixture()
        g["schema"]="unknown"
        with self.assertRaisesRegex(ValueError,"unaccepted"):
            rank(g)


if __name__=="__main__":
    unittest.main()
