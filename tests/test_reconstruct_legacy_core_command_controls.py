"""Synthetic historical CORE command-disassembly oracles; no original world."""
from __future__ import annotations
import hashlib
import json
import unittest

from tools.reconstruct_legacy_core_command_controls import (
    click_controls, scoreboard_access, selector_reads, nested_execute,
    reconstruct, summarize_subprograms
)


def make_graph(raw_commands):
    nodes=[]
    raw={}
    for i,command in enumerate(raw_commands):
        origin=(10+i,65,20)
        cid=",".join(str(v) for v in origin)
        nodes.append({
            "node_id":cid,"family":"command_block","position":list(origin),
            "command":{"sha256":hashlib.sha256(command.encode()).hexdigest(),
                       "verb":command.strip().lstrip("/").split()[0].lower()},
        })
        raw[cid]=command
    return {
        "schema":"supracraft-legacy-causal-machinery/1",
        "nodes":nodes,
        "family_counts":{"command_block":len(nodes),"redstone_wire":2,"repeater_off":1,
                         "wooden_button":1},
        "edges":{"direct_redstone_edges":[],"command_chain_candidates":[]}
    },raw


class LegacyCommandControlsTests(unittest.TestCase):
    def test_exact_scoreboard_writer_reader_join(self):
        g,r=make_graph([
            "scoreboard players set @p privateQuest 1",
            "scoreboard players test @a privateQuest 1 9"
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["source_command_count"],2)
        self.assertEqual(out["scoreboard_state_objectives_with_exact_read_write"],1)
        self.assertEqual(out["scoreboard_exact_cross_command_possible_edges"],1)
        self.assertNotIn("privateQuest",json.dumps(out))
        self.assertFalse(out["gameplay_promoted"])

    def test_cross_command_different_objectives_do_not_join(self):
        g,r=make_graph([
            "scoreboard players set @p objectiveA 1",
            "scoreboard players test @p objectiveB 1 9"
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["scoreboard_exact_cross_command_possible_edges"],0)

    def test_selector_is_real_state_read_not_just_verb(self):
        g,r=make_graph([
            "scoreboard players add @p innerValue 1",
            "tp @a[score_innerValue_min=3] 7 66 7"
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["scoreboard_exact_cross_command_possible_edges"],1)
        self.assertEqual(out["source_state_read_commands"],1)

    def test_dialogue_literal_score_tag_is_not_a_selector(self):
        g,r=make_graph([
            "scoreboard players add @p Trap 1",
            'tellraw @p {"text":"hint: score_Trap_min=2"}'
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["scoreboard_exact_cross_command_possible_edges"],0)

    def test_exact_setblock_writer_to_testforblock_read(self):
        g,r=make_graph([
            "setblock ~10 ~1 ~ minecraft:redstone_block",
            "testforblock 20 66 20 minecraft:redstone_block"
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["block_states_written_and_tested_exact_point_count"],1)
        self.assertEqual(out["block_state_exact_cross_command_possible_edges"],1)

    def test_wrong_point_is_not_linked(self):
        g,r=make_graph([
            "setblock ~10 ~1 ~ minecraft:redstone_block",
            "testforblock 20 66 21 minecraft:redstone_block"
        ])
        out=reconstruct(g,r)
        self.assertEqual(out["block_state_exact_cross_command_possible_edges"],0)

    def test_nested_clickable_json_is_an_authored_player_control(self):
        msg='tellraw @p {"text":"Look", "extra":[{"text":"Go","clickEvent":{"action":"run_command","value":"/scoreboard players set @p privateFlag 1"}}]}'
        g,r=make_graph([msg,"scoreboard players test @p privateFlag 1 2"])
        out=reconstruct(g,r)
        self.assertEqual(out["source_clickable_chat_counts"]["action_run_command"],1)
        self.assertEqual(out["source_clickable_chat_counts"]["run_verb_scoreboard"],1)
        self.assertEqual(out["source_chat_to_scoreboard_candidate_counts"]["click_score_reference_matched_existing_objective"],1)
        self.assertEqual(out["click_event_execution"],"NOT_RUN")
        self.assertNotIn("privateFlag",json.dumps(out))
        self.assertNotIn("Look",json.dumps(out))

    def test_malformed_tellraw_does_not_fabricate_controls(self):
        g,r=make_graph(["tellraw @p {bad json"])
        out=reconstruct(g,r)
        self.assertEqual(out["source_clickable_chat_counts"]["tellraw_malformed_json"],1)
        self.assertNotIn("action_run_command",out["source_clickable_chat_counts"])

    def test_click_url_not_source_execution(self):
        g,r=make_graph(['tellraw @p {"text":"Site","clickEvent":{"action":"open_url","value":"https://private.invalid/"}}'])
        out=reconstruct(g,r)
        self.assertEqual(out["source_clickable_chat_counts"]["action_open_url"],1)
        self.assertEqual(out["source_chat_to_scoreboard_candidate_counts"],{})
        self.assertNotIn("private.invalid",json.dumps(out))

    def test_nested_original_execute_detect_static_only(self):
        self.assertEqual(nested_execute(
            "execute @e[type=ArmorStand] ~ ~ ~ detect ~ ~-1 ~ stone 0 scoreboard players set @p A 1".split()),
            ("detect","scoreboard"))
        self.assertEqual(nested_execute("execute @e ~ ~ ~".split()),
                         ("malformed_or_short",None))

    def test_scoreboard_op_target_is_write_and_rhs_is_read(self):
        reader,writer=scoreboard_access(
            "scoreboard players operation @p target += @e[type=ArmorStand] donor".split())
        self.assertEqual(reader,{"target","donor"})
        self.assertEqual(writer,{"target"})

    def test_source_command_hash_mismatch_is_hard_refusal(self):
        g,r=make_graph(["scoreboard players set @p Z 1"])
        r["10,65,20"]="scoreboard players set @p Z 999"
        with self.assertRaisesRegex(ValueError,"partial/forged"):
            reconstruct(g,r)

    def test_unrecognized_source_features_do_not_promote_story(self):
        g,r=make_graph(["summon Blaze 0 60 0", "gamemode spectator @p",
                         "effect @p speed 5 1"])
        out=reconstruct(g,r)
        status=out["author_claim_source_feature_status"]["creator_blaze_potion_click_control"]
        self.assertEqual(status["source_candidate_feature_families_unresolved"],["click_run_command"])
        self.assertEqual(status["candidate_relation"],"SOURCE_FEATURE_INVENTORY_ONLY_NO_VERIFIED_SCENE_JOIN")
        self.assertFalse(status["native_runtime_verified"])

    def test_command_chain_requires_known_command_endpoints(self):
        g,r=make_graph(["say A","say B"])
        g["edges"]["command_chain_candidates"].extend([
            {"source":"10,65,20","target":"11,65,20","edge_type":"conditional_predecessor_success_dependency"},
            {"source":"11,65,20","target":"foreign_3","edge_type":"conditional_predecessor_success_dependency"},
            {"source":"10,65,20","target":"11,65,20","edge_type":"physical_adjacency_candidate"}])
        out=reconstruct(g,r)
        self.assertEqual(out["source_direct_command_chain_candidate_edges"],1)

    def test_duplicate_graph_identifiers_fail_closed(self):
        g,r=make_graph(["say A"])
        g["nodes"].append(g["nodes"][0])
        with self.assertRaises(ValueError):
            reconstruct(g,r)

    def test_exact_static_subprograms_partition_by_dependency_not_proximity(self):
        nodes={"A","B","C","D","E"}
        links={("A","B","redstone_power"),("B","C","block_state_test"),
               ("D","E","scoreboard_objective")}
        out=summarize_subprograms(nodes,{"A"},links)
        self.assertEqual(out["source_connected_instruction_groups"],2)
        self.assertEqual(out["linked_instruction_count"],5)
        self.assertEqual(out["largest_source_link_group_instruction_count"],3)
        self.assertEqual(out["groups_with_known_direct_sensor_command_path"],1)
        self.assertEqual(out["groups_without_known_direct_sensor_command_path"],1)
        self.assertEqual(out["source_group_size_bands"],{"size2":1,"size3_to_5":1})
        self.assertEqual(out["source_directed_cycles_candidate_count"],0)
        self.assertNotIn('"A"',json.dumps(out))

    def test_source_directional_cycles_do_not_imply_runtime_clock(self):
        out=summarize_subprograms({"A","B","C"},set(),{
            ("A","B","scoreboard_objective"),
            ("B","A","redstone_power"),
            ("B","C","block_state_test")})
        self.assertEqual(out["source_directed_cycles_candidate_count"],1)
        self.assertEqual(out["source_instruction_nodes_in_cycles"],2)
        self.assertIn("NO_ACTIVATION_OR_PURPOSE",out["graph_semantics"])

    def test_unqualified_dependency_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"unqualified"):
            summarize_subprograms({"A","B"},set(),{("A","B","same_chunk_proximity")})
        with self.assertRaisesRegex(ValueError,"unverified"):
            summarize_subprograms({"A"},set(),{("A","OTHER","redstone_power")})

    def test_disjoint_commands_do_not_fabricate_group(self):
        out=summarize_subprograms({"A","B"},set(),set())
        self.assertEqual(out["source_connected_instruction_groups"],0)
        self.assertEqual(out["linked_instruction_count"],0)
        self.assertEqual(out["largest_source_link_group_instruction_count"],0)

    def test_click_setblock_absolute_reaches_neighbor_command_port_only_as_candidate(self):
        click='tellraw @p {"text":"Power", "clickEvent":{"action":"run_command","value":"/setblock 12 65 20 minecraft:redstone_block"}}'
        g,r=make_graph([click,"say Response"])
        out=reconstruct(g,r)
        self.assertEqual(out["source_click_to_world_static_candidate_counts"],
                         {"click_material_redstone_power_source_candidate":1,
                          "click_power_target_adjacent_legacy_command":1,
                          "click_run_setblock":1,
                          "click_setblock_absolute_point":1,
                          "click_target_adjacent_legacy_command":1,
                          "distinct_absolute_click_targets":1})
        self.assertEqual(out["original_native"],"NOT_RUN")

    def test_click_world_absolute_target_shared_with_authored_writer(self):
        click='tellraw @p {"text":"Power", "clickEvent":{"action":"run_command","value":"/setblock 40 65 40 minecraft:air"}}'
        g,r=make_graph([click,"setblock 40 65 40 minecraft:redstone_block"])
        out=reconstruct(g,r)
        self.assertEqual(
            out["source_click_to_world_static_candidate_counts"]["click_exact_target_also_written_by_command_block"],1)
        self.assertEqual(
            out["source_click_to_world_static_candidate_counts"]["click_material_air_removal_candidate"],1)

    def test_click_power_and_other_author_command_air_share_reset_target(self):
        click='tellraw @p {"text":"Activate","clickEvent":{"action":"run_command","value":"/setblock 40 65 40 minecraft:redstone_block"}}'
        g,r=make_graph([click,"setblock 40 65 40 minecraft:air"])
        d=reconstruct(g,r)["source_click_to_world_static_candidate_counts"]
        self.assertEqual(d["distinct_clicked_targets_with_authored_air_reset_candidate"],1)
        self.assertNotIn("distinct_clicked_targets_with_authored_power_writer",d)
        self.assertEqual(d["click_exact_target_also_written_by_command_block"],1)

    def test_click_relative_target_must_not_borrow_command_block_origin(self):
        click='tellraw @p {"text":"Power", "clickEvent":{"action":"run_command","value":"/setblock ~ ~ ~ minecraft:redstone_block"}}'
        g,r=make_graph([click,"say Response"])
        out=reconstruct(g,r)
        self.assertEqual(out["source_click_to_world_static_candidate_counts"],
                         {"click_run_setblock":1,
                          "click_setblock_non_absolute_or_incomplete":1})

    def test_click_air_at_command_neighbor_is_not_power_signal(self):
        click='tellraw @p {"text":"Off", "clickEvent":{"action":"run_command","value":"/setblock 12 65 20 air"}}'
        g,r=make_graph([click,"say Response"])
        out=reconstruct(g,r)
        d=out["source_click_to_world_static_candidate_counts"]
        self.assertEqual(d["click_target_adjacent_legacy_command"],1)
        self.assertNotIn("click_power_target_adjacent_legacy_command",d)

    def test_exact_authored_redstone_power_into_command_is_static_edge(self):
        g,r=make_graph(["setblock 12 65 20 minecraft:redstone_block","say Activated"])
        g["edges"]["command_authored_redstone_edges"]=[
            {"source":"10,65,20","target":"11,65,20",
             "edge_type":"legacy_setblock_redstone_block_direct_command_power",
             "authored_target_position":[12,65,20]}]
        out=reconstruct(g,r)
        self.assertEqual(out["source_authored_power_dependency_total"],1)
        self.assertEqual(out["source_authored_power_dependency_counts"],
                         {"legacy_setblock_redstone_block_direct_command_power":1})
        self.assertEqual(out["original_native"],"NOT_RUN")

    def test_forged_power_edge_fails_closed(self):
        g,r=make_graph(["setblock 12 65 20 redstone_block","say Activated"])
        g["edges"]["command_authored_redstone_edges"]=[
            {"source":"10,65,20","target":"11,65,20",
             "edge_type":"legacy_setblock_redstone_block_direct_command_power",
             "authored_target_position":[13,65,20]}]
        with self.assertRaisesRegex(ValueError,"exact original"):
            reconstruct(g,r)

    def test_exact_redstone_diode_rear_edge_requires_orientation(self):
        g,r=make_graph(["setblock 13 65 20 152"])
        g["nodes"].append({
            "node_id":"12,65,20","position":[12,65,20],
            "family":"repeater_off","metadata_semantics":{"facing_vector":[1,0,0]}
        })
        g["edges"]["command_authored_redstone_edges"]=[
            {"source":"10,65,20","target":"12,65,20",
             "edge_type":"legacy_setblock_redstone_block_diode_rear_input",
             "authored_target_position":[13,65,20]}]
        self.assertEqual(reconstruct(g,r)["source_authored_power_dependency_total"],1)
        g["nodes"][-1]["metadata_semantics"]["facing_vector"]=[-1,0,0]
        with self.assertRaisesRegex(ValueError,"diode rear"):
            reconstruct(g,r)

    def test_selector_parsing_rejects_spoofed_words(self):
        self.assertEqual(selector_reads('say score_secret_min=9'),set())
        self.assertEqual(selector_reads('tp @p[score_secret_min=9] ~ ~ ~'),{"secret"})
        self.assertEqual(selector_reads('tp @a[score_alpha=1,score_beta_min=4] ~ ~ ~'),
                         {"alpha","beta"})


if __name__=="__main__":
    unittest.main()
