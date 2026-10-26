"""Source-free, privacy-aware IR assembly hard negatives from attributed aggregates."""
import copy
import json
import unittest

from tools.compile_legacy_core_creator_mechanism_ir import (
    compile_ir, PIN_WORLD, PIN_GRAPH, STORY, CONTROL, SCHEMA
)


def fixtures():
    base=dict(source_world_sha256=PIN_WORLD,source_graph_sha256=PIN_GRAPH)
    story=dict(base, schema=STORY, original_commands_sha_verified=1445,
               original_java_188_native="NOT_RUN",gameplay_promoted=False,
               qualified_sensor_to_command_route_count=90,
               source_command_family_counts={
                   "entity_presence_gate":30,"entity_kill":43,
                   "dr_h_author_text_cue":48,"chess_author_text_cue":1,
                   "armor_stand_summon_with_skull_token":8,
                   "smoke_hint_candidate":5,"skull_token_in_action":11},
               qualified_sensor_to_scene_command_path_counts={
                   "typed_sensor_to_dr_h_author_text_cue":2,
                   "typed_sensor_to_entity_kill":2},
               distinct_strict_sensor_shared_scene_role_counts={
                   "dr_h_text_and_entity_kill":0},
               entity_named_selector_potential_shared_presence_kill_signatures=0,
               command_static_links={"bounded_source_command_class_join_counts":{}},
               saved_actor_inventory_evidence={"saved_armor_stand_instances":952})
    control=dict(base,schema=CONTROL,source_sha_verified_command_count=1445,
                 original_java_188_execution="NOT_RUN",gameplay_primitive_promoted=False,
                 clicked_target_source_feature_counts={"targets_has_independent_air_writer":4},
                 authored_click_actions_matching_absolute_redstone_setblock=13,
                 distinct_clicked_redstone_target_count=4,
                 diode_source_geometry_stage_count_histogram_by_clicked_target={
                     "9":2,"16":1,"18":1},
                 diode_source_geometry_saved_delay_redstone_ticks_histogram_by_clicked_target={
                     "36":2,"64":1,"72":1},
                 diode_source_geometry_downstream_verb_counts_occurrences={
                     "tellraw":3,"tp":1},
                 source_reachable_player_feedback_command_counts_occurrences={
                     "tellraw":4})
    return story,control


class MechanismIrTests(unittest.TestCase):
    def test_three_source_only_mechanisms_human_agent_automation(self):
        s,c=fixtures()
        ir=compile_ir(s,c)
        self.assertEqual(ir["schema"],SCHEMA)
        self.assertEqual(ir["mechanism_count"],3)
        self.assertEqual(ir["proven_gameplay_mechanism_count"],0)
        self.assertEqual(ir["original_native"],"NOT_RUN")
        self.assertEqual(ir["semantic_admission"],"NOT_ADMITTED")
        self.assertEqual(ir["mechanisms"]["clickable_redstone_controller"]["timing"]
                         ["stage_count_histogram"],{"9":2,"16":1,"18":1})
        self.assertEqual(ir["mechanisms"]["dr_h_finale"]["input"]["author_dialogue_paths"],2)
        self.assertEqual(ir["mechanisms"]["chess_head_hint"]["state"]
                         ["skull_bearing_armor_stand_summon_commands"],8)
        raw=json.dumps(ir)
        self.assertNotIn('"node_id"',raw)
        self.assertNotIn('"selector"',raw)
        self.assertNotIn('"target_position"',raw)

    def test_pinned_source_custody_rejects_mismatched_world(self):
        s,c=fixtures()
        c["source_world_sha256"]="deadbeef"
        with self.assertRaisesRegex(ValueError,"pin mismatch"):
            compile_ir(s,c)

    def test_wrong_schema_rejected(self):
        s,c=fixtures()
        s["schema"]="invented"
        with self.assertRaisesRegex(ValueError,"schema mismatch"):
            compile_ir(s,c)

    def test_native_or_promotion_does_not_enter_source_only_ir(self):
        s,c=fixtures()
        s["original_java_188_native"]="RUN"
        with self.assertRaisesRegex(ValueError,"native"):
            compile_ir(s,c)
        s,c=fixtures()
        c["gameplay_primitive_promoted"]=True
        with self.assertRaisesRegex(ValueError,"promotion"):
            compile_ir(s,c)

    def test_wrong_source_census_prevents_ir_publication(self):
        s,c=fixtures()
        s["qualified_sensor_to_command_route_count"]=89
        with self.assertRaisesRegex(ValueError,"witness"):
            compile_ir(s,c)

    def test_four_channels_cannot_be_fabricated_from_three(self):
        s,c=fixtures()
        c["distinct_clicked_redstone_target_count"]=3
        with self.assertRaisesRegex(ValueError,"four-channel"):
            compile_ir(s,c)

    def test_full_per_target_repeater_histogram_required(self):
        s,c=fixtures()
        c["diode_source_geometry_stage_count_histogram_by_clicked_target"]={"9":2,"16":1}
        with self.assertRaisesRegex(ValueError,"histogram"):
            compile_ir(s,c)

    def test_global_story_counts_do_not_prove_dr_h_or_chess_execution(self):
        s,c=fixtures()
        s["source_command_family_counts"]["dr_h_author_text_cue"]=500
        s["source_command_family_counts"]["smoke_hint_candidate"]=500
        ir=compile_ir(s,c)
        self.assertFalse(ir["mechanisms"]["dr_h_finale"]["source_story_chain_proven"])
        self.assertFalse(ir["mechanisms"]["chess_head_hint"]["exact_chess_puzzle_source_chain_proven"])
        self.assertFalse(ir["mechanisms"]["chess_head_hint"]["reset"]["verified"])


if __name__=="__main__":
    unittest.main()
