"""Source-free four-channel control provenance and bounded downstream tests."""
import copy
import hashlib
import json
import unittest

from tools.trace_legacy_core_ui_controls import trace


def node(x,y,z,family,raw=None,**opts):
    result=dict(node_id=f"{x},{y},{z}",position=[x,y,z],family=family,**opts)
    if raw is not None:
        result["command"]=dict(verb=raw.split()[0].lstrip("/").lower(),
                               sha256=hashlib.sha256(raw.encode()).hexdigest())
    return result


def specimen():
    click='tellraw @p {"text":"Move","extra":[{"text":"Left","clickEvent":{"action":"run_command","value":"/setblock 20 65 20 redstone_block"}}]}'
    power='setblock 30 65 20 minecraft:redstone_block'
    reset='setblock 20 65 20 air'
    downstream='summon Blaze ~ ~1 ~'
    nodes=[
        node(10,65,20,"command_block",click),
        node(19,65,20,"command_block",power),
        node(15,65,20,"command_block",reset),
        node(29,65,20,"command_block",downstream),
        node(21,65,20,"repeater_off",metadata_semantics={"facing_vector":[-1,0,0]}),
    ]
    commands={n["node_id"]:raw for n,raw in zip(nodes,[click,power,reset,downstream])
              if n["family"]=="command_block"}
    graph=dict(schema="supracraft-legacy-causal-machinery/1",nodes=nodes,
               family_counts={"command_block":4,"repeater_off":1},
               edges={
                   "direct_redstone_edges":[],
                   "command_chain_candidates":[],
                   "command_authored_redstone_edges":[
                       dict(source="19,65,20",target="29,65,20",
                            edge_type="legacy_setblock_redstone_block_direct_command_power",
                            authored_target_position=[30,65,20])
                   ],
               })
    return graph,commands


class SourceClickTraceTests(unittest.TestCase):
    def test_click_has_exact_ports_and_source_author_air_off(self):
        graph,commands=specimen()
        out=trace(graph,commands)
        self.assertEqual(out["authored_click_actions_matching_absolute_redstone_setblock"],1)
        self.assertEqual(out["distinct_clicked_redstone_target_count"],1)
        self.assertEqual(out["clicked_target_source_feature_counts"]["targets_has_direct_command_port"],1)
        self.assertEqual(out["clicked_target_source_feature_counts"]["targets_has_oriented_diode_rear_port"],1)
        self.assertEqual(out["clicked_target_source_feature_counts"]["targets_has_independent_air_writer"],1)
        self.assertEqual(out["original_air_reset_writers_per_clicked_target_total"],1)
        self.assertEqual(out["source_reachable_summon_entity_classes_occurrences"].get("summon_blaze",0),1)
        self.assertFalse(out["gameplay_primitive_promoted"])
        self.assertEqual(out["original_java_188_execution"],"NOT_RUN")
        raw=json.dumps(out)
        for secret in ("20,65,20","30,65,20",'"node_id"','"position"',"Move","Left"):
            self.assertNotIn(secret,raw)

    def test_wrong_direction_diode_not_a_qualified_rear_port(self):
        graph,commands=specimen()
        graph["nodes"][-1]["metadata_semantics"]["facing_vector"]=[1,0,0]
        out=trace(graph,commands)
        self.assertNotIn("targets_has_oriented_diode_rear_port",
                         out["clicked_target_source_feature_counts"])

    def test_missing_air_reset_stays_unknown(self):
        graph,commands=specimen()
        commands["15,65,20"]="setblock 20 65 20 redstone_block"
        graph["nodes"][2]["command"]["sha256"]=hashlib.sha256(
            commands["15,65,20"].encode()).hexdigest()
        out=trace(graph,commands)
        self.assertEqual(out["unresolved_join_reason_counts"]["no_original_air_reset_writer"],1)
        self.assertNotIn("targets_has_independent_air_writer",
                         out["clicked_target_source_feature_counts"])

    def test_relative_clicked_target_never_uses_source_command_origin(self):
        graph,commands=specimen()
        val='tellraw @p {"clickEvent":{"action":"run_command","value":"/setblock ~ ~ ~ redstone_block"}}'
        commands["10,65,20"]=val
        graph["nodes"][0]["command"]["sha256"]=hashlib.sha256(val.encode()).hexdigest()
        out=trace(graph,commands)
        self.assertEqual(out["distinct_clicked_redstone_target_count"],0)
        self.assertEqual(out["unresolved_join_reason_counts"],
                         {"no_author_clickable_setblock_redstone_input":1})

    def test_literal_dialogue_command_text_not_a_click(self):
        graph,commands=specimen()
        val='tellraw @p {"text":"do /setblock 20 65 20 redstone_block"}'
        commands["10,65,20"]=val
        graph["nodes"][0]["command"]["sha256"]=hashlib.sha256(val.encode()).hexdigest()
        self.assertEqual(trace(graph,commands)["distinct_clicked_redstone_target_count"],0)

    def test_forged_graph_edge_cannot_infer_reachable_actor(self):
        graph,commands=specimen()
        graph["edges"]["command_authored_redstone_edges"][0]["authored_target_position"]=[40,65,20]
        with self.assertRaisesRegex(ValueError,"exact original"):
            trace(graph,commands)

    def test_source_sha_mismatch_fails(self):
        graph,commands=specimen()
        commands["15,65,20"]="setblock 20 65 20 secret_cuboid"
        with self.assertRaisesRegex(ValueError,"partial/forged"):
            trace(graph,commands)

    def test_duplicate_node_identity_fails(self):
        graph,commands=specimen()
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        with self.assertRaises(ValueError):
            trace(graph,commands)

    def test_duplicate_buttons_on_same_target_are_distinct_authored_actions(self):
        graph,commands=specimen()
        click=commands["10,65,20"]
        graph["nodes"].append(node(11,65,20,"command_block",click))
        commands["11,65,20"]=click
        out=trace(graph,commands)
        self.assertEqual(out["distinct_clicked_redstone_target_count"],1)
        self.assertEqual(out["authored_click_actions_matching_absolute_redstone_setblock"],2)
        self.assertEqual(out["unique_source_authoring_commands_with_matching_click_controls"],2)

    def test_diode_output_front_to_actor_requires_recorded_oriented_edge(self):
        graph,commands=specimen()
        spawned="summon Blaze 28 70 20"
        graph["nodes"].append(node(22,65,20,"command_block",spawned))
        commands["22,65,20"]=spawned
        graph["edges"]["oriented_signal_candidates"]=[
            {"source":"21,65,20","target":"22,65,20",
             "edge_type":"oriented_front_output_candidate"}]
        out=trace(graph,commands)
        self.assertEqual(out["clicked_targets_with_diode_geometry_candidate_blaze_summon"],1)
        self.assertEqual(out["diode_source_geometry_downstream_verb_counts_occurrences"],{"summon":1})
        self.assertEqual(out["diode_source_geometry_downstream_ports"],
                         {"front_adjacent_command_candidate":1})
        graph["edges"]["oriented_signal_candidates"]=[]
        out=trace(graph,commands)
        self.assertEqual(out["clicked_targets_with_diode_geometry_candidate_blaze_summon"],0)

    def test_diode_wrong_front_edge_does_not_count_nearby_actor(self):
        graph,commands=specimen()
        spawned="summon Blaze 28 70 20"
        graph["nodes"].append(node(22,65,20,"command_block",spawned))
        commands["22,65,20"]=spawned
        graph["edges"]["oriented_signal_candidates"]=[
            {"source":"21,65,20","target":"19,65,20",
             "edge_type":"oriented_front_output_candidate"}]
        out=trace(graph,commands)
        self.assertEqual(out["clicked_targets_with_diode_geometry_candidate_blaze_summon"],0)

    def test_diode_front_dust_path_requires_strict_real_edges(self):
        graph,commands=specimen()
        spawn="summon ArmorStand 35 65 20"
        graph["nodes"].append(node(23,65,20,"command_block",spawn))
        graph["nodes"].append(node(22,65,20,"redstone_wire"))
        commands["23,65,20"]=spawn
        graph["edges"]["oriented_signal_candidates"]=[
            {"source":"21,65,20","target":"22,65,20",
             "edge_type":"oriented_front_output_candidate"}]
        graph["edges"]["direct_redstone_edges"]=[
            {"source":"22,65,20","target":"23,65,20",
             "edge_type":"legacy_dust_direct_component_power"}]
        out=trace(graph,commands)
        self.assertEqual(out["diode_source_geometry_downstream_ports"],{"front_wire_candidate":1})
        self.assertEqual(out["diode_source_geometry_downstream_summon_entity_counts_occurrences"],
                         {"summon_armorstand":1})
        graph["edges"]["direct_redstone_edges"][0]["edge_type"]="physical_adjacency_candidate"
        out=trace(graph,commands)
        self.assertEqual(out["diode_source_geometry_downstream_summon_entity_counts_occurrences"],{})

    def test_not_all_actor_spawns_are_reachable_from_controller(self):
        graph,commands=specimen()
        extra="summon ArmorStand 15 70 10"
        graph["nodes"].append(node(80,65,20,"command_block",extra))
        commands["80,65,20"]=extra
        out=trace(graph,commands)
        self.assertEqual(out["source_reachable_summon_entity_classes_occurrences"].get("summon_armorstand",0),0)

    def test_no_unverified_long_path_or_accidental_runtimes(self):
        graph,commands=specimen()
        graph["edges"]["command_authored_redstone_edges"]=[]
        out=trace(graph,commands)
        self.assertEqual(out["source_power_reach_maximum_hops"],0)
        self.assertEqual(out["creator_reported_blaze_control_relation"],
                         "NOT_ESTABLISHED_UNLESS_EXACT_SCENE_JOIN")


if __name__=="__main__":
    unittest.main()
