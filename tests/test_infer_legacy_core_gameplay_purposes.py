"""Source-free exact full-corpus purpose-hypothesis regression and red-team tests."""
import copy
import hashlib
import json
import unittest

from tools.infer_legacy_core_gameplay_purposes import (
    material_class, typed_routes, source_intent,
)


def node(family, pos, **opts):
    return dict(node_id=",".join(str(v) for v in pos), position=list(pos), family=family, **opts)


def edge(a, b, kind):
    return dict(source=a, target=b, edge_type=kind)


def specimen(button_command="setblock 20 66 20 minecraft:air", plate_command="setblock 20 66 20 minecraft:stone"):
    sensor=node("wooden_button",(0,66,0),metadata_semantics={"support_vector":[1,0,0]})
    command=node("command_block",(1,66,0),command={
        "sha256":hashlib.sha256(button_command.encode()).hexdigest(),"verb":"setblock"})
    plate=node("wooden_pressure_plate",(8,66,0),metadata_semantics={"support_vector":[0,-1,0]})
    second=node("command_block",(8,65,0),command={
        "sha256":hashlib.sha256(plate_command.encode()).hexdigest(),"verb":"setblock"})
    nodes=[sensor,command,plate,second]
    graph={"schema":"supracraft-legacy-causal-machinery/1","nodes":nodes,"edges":{
        "direct_redstone_edges":[
            edge(sensor["node_id"],command["node_id"],"legacy_button_attached_support_power"),
            edge(plate["node_id"],second["node_id"],"legacy_pressure_plate_support_power"),
        ],
        "command_world_targets":[
            dict(source=command["node_id"],target_position=[20,66,20],target_kind="point",edge_type="command_world_target"),
            dict(source=second["node_id"],target_position=[20,66,20],target_kind="point",edge_type="command_world_target"),
        ]}}
    return graph,{command["node_id"]:button_command,second["node_id"]:plate_command}


class FullPurposeInferenceTests(unittest.TestCase):
    def test_all_source_routes_group_into_possible_place_remove_reset(self):
        graph, raw=specimen()
        out=source_intent(graph,raw)
        self.assertEqual(out["directed_source_witness_count"],2)
        self.assertEqual(out["original_command_block_count"],2)
        self.assertEqual(out["original_commands_fingerprint_matched"],2)
        self.assertEqual(out["shared_target_source_hypothesis_counts"],
                         {"place_remove_or_reset_hypothesis":1})
        self.assertEqual(out["qualified_routes_to_shared_setblock_targets"],2)
        self.assertFalse(out["gameplay_primitive_promoted"])
        for secret in ("20,66,20","1,66,0","minecraft:air",'"node_id"','"position"','"command"'):
            self.assertNotIn(secret,json.dumps(out))

    def test_identical_edge_projection_does_not_create_mechanism(self):
        graph,raw=specimen()
        graph["edges"]["direct_redstone_edges"].append(
            copy.deepcopy(graph["edges"]["direct_redstone_edges"][0]))
        self.assertEqual(source_intent(graph,raw)["directed_source_witness_count"],2)

    def test_malformed_facing_is_not_a_route(self):
        graph,raw=specimen()
        graph["nodes"][0]["metadata_semantics"]["support_vector"]=[-1,0,0]
        out=source_intent(graph,raw)
        self.assertEqual(out["directed_source_witness_count"],1)
        self.assertEqual(out["original_command_block_count"],2)

    def test_graph_duplicate_node_fails_closed(self):
        graph,raw=specimen()
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            typed_routes(graph)

    def test_missing_orig_command_not_fabricated(self):
        graph,raw=specimen()
        raw.pop("1,66,0")
        out=source_intent(graph,raw)
        self.assertEqual(out["unresolved_source_analysis_counts"],
                         {"original_command_text_sha_or_tile_missing":1})
        self.assertEqual(out["route_inference_strength_counts"]["unverified_original_command"],1)

    def test_command_sha_validation_stays_in_read_workcell(self):
        graph,raw=specimen()
        raw["1,66,0"]="setblock 20 66 20 minecraft:tnt"
        out=source_intent(graph,raw)
        self.assertEqual(out["original_commands_fingerprint_matched"],1)
        self.assertEqual(out["route_inference_strength_counts"]["unverified_original_command"],1)

    def test_nonlocal_unknown_verb_stays_unknown(self):
        graph,raw=specimen()
        unknown="customplugin do_unsafe_stuff"
        graph["nodes"][1]["command"]={"sha256":hashlib.sha256(unknown.encode()).hexdigest(),
                                       "verb":"customplugin"}
        raw["1,66,0"]=unknown
        out=source_intent(graph,raw)
        self.assertEqual(out["route_inference_strength_counts"]["undetermined_authored_purpose"],1)
        self.assertNotIn("customplugin",json.dumps(out))

    def test_typed_reverse_edge_does_not_create_route(self):
        graph,raw=specimen()
        graph["edges"]["direct_redstone_edges"][0]["source"]="1,66,0"
        graph["edges"]["direct_redstone_edges"][0]["target"]="0,66,0"
        self.assertEqual(source_intent(graph,raw)["directed_source_witness_count"],1)

    def test_missing_source_edge_collection_fails_closed(self):
        graph,raw=specimen()
        del graph["edges"]["direct_redstone_edges"]
        with self.assertRaisesRegex(ValueError,"collection missing"):
            source_intent(graph,raw)

    def test_material_input_never_exposed(self):
        self.assertEqual(material_class("minecraft:air"),"air_removal_candidate")
        self.assertEqual(material_class("152"),"redstone_power_source_candidate")
        self.assertEqual(material_class("minecraft:tnt"),"hazard_or_volatile_block_candidate")
        self.assertEqual(material_class("minecraft:stone"),"structural_block_placement_candidate")
        self.assertEqual(material_class("secret_custom_block"),"other_block_material_unclassified")

    def test_power_on_off_reclassifies_without_executing(self):
        graph,raw=specimen("setblock 20 66 20 minecraft:redstone_block")
        out=source_intent(graph,raw)
        self.assertEqual(out["shared_target_source_hypothesis_counts"],
                         {"multi_state_reconfiguration_hypothesis":1})
        self.assertEqual(out["runtime_authored_command_execution"],"NOT_OBSERVED")

    def test_static_hypothesis_not_player_knowledge(self):
        graph,raw=specimen()
        out=source_intent(graph,raw)
        self.assertEqual(out["original_player_intent"],"NOT_PROVEN")
        self.assertEqual(out["minecraft_26_3_equivalence"],"NOT_RUN")
        self.assertEqual(out["runtime_source_actuation"],"NOT_RUN")


if __name__=="__main__":
    unittest.main()
