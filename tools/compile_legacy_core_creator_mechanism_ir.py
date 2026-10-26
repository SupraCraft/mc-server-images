#!/usr/bin/env python3
"""Compile only independently verified aggregate CORE evidence to auditable IR.

Source-free consumer: it does not open commands, NBT, world regions, original
coordinates, actor identities or physical world data. The IR is a source-only
hypothesis contract, never an assertion of game execution or 26.3 parity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

SCHEMA="supracraft-legacy-core-mechanism-hypotheses-ir/1"
STORY="supracraft-core-188-creator-scenes-static/1"
CONTROL="supracraft-core-188-click-control-slices-aggregate/1"
PIN_WORLD="61092508c78f5dbe36b03a9d0bdb202c5ddfe71f1aada58d62ae81ae93f5a998"
PIN_GRAPH="5a5c25a31e2bcdec1f2d7d18cc4dedfc87c5a43e53cab4529e5bcdac0452efb5"


def compile_ir(story,control):
    for name,value,expected in (("story",story,STORY),("controller",control,CONTROL)):
        if value.get("schema")!=expected:
            raise ValueError(name+" schema mismatch")
        if value.get("source_world_sha256")!=PIN_WORLD or value.get("source_graph_sha256")!=PIN_GRAPH:
            raise ValueError(name+" immutable original source pin mismatch")
        if value.get("gameplay_promoted") is not False and value.get("gameplay_primitive_promoted") is not False:
            raise ValueError(name+" attempted gameplay promotion")
    if story["original_commands_sha_verified"]!=1445 or control["source_sha_verified_command_count"]!=1445:
        raise ValueError("incomplete original source command census")
    if story["original_java_188_native"]!="NOT_RUN" or control["original_java_188_execution"]!="NOT_RUN":
        raise ValueError("source-only IR cannot ingest native claims")
    if story["qualified_sensor_to_command_route_count"]!=90:
        raise ValueError("strict original typed witness regression")
    channels=control["clicked_target_source_feature_counts"]
    clicks=control["authored_click_actions_matching_absolute_redstone_setblock"]
    targets=control["distinct_clicked_redstone_target_count"]
    if targets!=4 or clicks!=13 or channels.get("targets_has_independent_air_writer")!=targets:
        raise ValueError("four-channel original control source contract mismatch")
    stages=control["diode_source_geometry_stage_count_histogram_by_clicked_target"]
    if sum(stages.values())!=targets:
        raise ValueError("incomplete original controller stage histogram")
    if sum(control["diode_source_geometry_downstream_verb_counts_occurrences"].values())<targets:
        raise ValueError("missing source-authored terminal command witness")
    source=story["source_command_family_counts"]
    routes=story["qualified_sensor_to_scene_command_path_counts"]
    shared=story["distinct_strict_sensor_shared_scene_role_counts"]
    join=story["command_static_links"]["bounded_source_command_class_join_counts"]
    saved=story["saved_actor_inventory_evidence"]
    geometry=story.get("chess_source_effect_target_geometry")
    if geometry is not None:
        if (geometry.get("shared_scene_or_control_flow")!="NOT_ESTABLISHED_BY_SPATIAL_OVERLAP"
            or geometry.get("particle_emission_and_spawn")!="NOT_OBSERVED"
            or geometry.get("geometry_proof")!="COMMAND_AUTHORED_EFFECT_COORDINATES_ONLY"):
            raise ValueError("unsupported chess gameplay admission from geometry")
        if (sum(geometry["source_effect_to_spawn_nearest_distance_bands"].values())>
            geometry["source_smoke_particle_effect_targets_resolved"]):
            raise ValueError("source chess geometric effect denominator mismatch")

    controller={
        "label":"Four-channel Redstone chat interface",
        "inference_tier":"EXACT_TYPED_ORIGINAL_SOURCE_PROGRAM_SKELETON",
        "input":{"kind":"authored_clickable_json_setblock","action_count":clicks},
        "state":{"kind":"four_absolute_redstone_power_targets","distinct_targets":targets},
        "timing":{"kind":"saved_repeater_metadata_not_elapsed_time",
                  "stage_count_histogram":stages,
                  "delay_redstone_ticks_histogram":control[
                      "diode_source_geometry_saved_delay_redstone_ticks_histogram_by_clicked_target"]},
        "output":{"kind":"source_terminal_verbs_not_actuated",
                  "verb_counts":control["diode_source_geometry_downstream_verb_counts_occurrences"]},
        "feedback":{"kind":"source_authored_tellraw_candidate",
                    "immediate_feedback_count":control[
                        "source_reachable_player_feedback_command_counts_occurrences"].get("tellraw",0)},
        "reset":{"kind":"same_target_air_writer_source_candidate",
                 "target_count":channels.get("targets_has_independent_air_writer",0)},
        "proposed_purpose":"UNKNOWN_NOT_PROVED_BLAZE_POSSESSION",
        "unverified":["command_permission","tick_activation_and_repeater_locking",
                      "actual_entity_teleport_binding","original_v1_4_playability"],
        "native":"NOT_RUN",
    }
    finale={
        "label":"Dr. H finale and ending progression",
        "inference_tier":"CREATOR_EXTERNAL_SPEC_WITH_DISJOINT_SOURCE_COMPONENTS",
        "input":{"kind":"qualified_typed_sensor_paths_into_dr_h_referencing_commands",
                 "dr_h_referencing_command_paths":routes.get("typed_sensor_to_dr_h_author_text_cue",0),
                 "entity_removal_paths":routes.get("typed_sensor_to_entity_kill",0),
                 "same_strict_sensor_for_both":shared.get("dr_h_text_and_entity_kill",0)},
        "state":{"kind":"possible_actor_presence_gate_not_exclusively_attributed",
                 "global_presence_test_commands":source.get("entity_presence_gate",0),
                 "shared_named_presence_kill_signatures":story[
                      "entity_named_selector_potential_shared_presence_kill_signatures"]},
        "output":{"kind":"author_reported_actor_death_skull_and_branch_UNVERIFIED",
                  "global_kill_commands":source.get("entity_kill",0),
                  "global_skull_token_actions":source.get("skull_token_in_action",0)},
        "feedback":{"kind":"story_reference_in_original_command_body",
                    "source_commands_with_dr_h_reference":source.get("dr_h_author_text_cue",0)},
        "reset":{"kind":"unknown","verified":False},
        "source_story_chain_proven":False,
        "same_sensor_actor_type_comparison":story.get("same_sensor_original_actor_type_compatibility",{}),
        "exact_directed_join_classes":{k:v for k,v in join.items() if k in
             {"dr_h_cue_to_presence_gate","presence_gate_to_skull_action_token",
              "presence_gate_to_dialogue"}},
        "unverified":["author_release_version","actor_identity","clock_timing",
                      "early_kill_failure","good_bad_ending_branch"],
        "native":"NOT_RUN",
    }
    chess={
        "label":"Chess heads and smoke hint",
        "inference_tier":"AUTHOR_EXTERNAL_SPEC_PLUS_SOURCE_ARMOR_STAND_HEAD_ACTION",
        "input":{"kind":"hint_interaction_not_exactly_joined",
                 "smoke_hint_typed_sensor_paths":routes.get(
                     "typed_sensor_to_smoke_hint_candidate",0)},
        "state":{"kind":"dynamically_spawned_armor_stand_skull_action",
                 "skull_bearing_armor_stand_summon_commands":source.get(
                     "armor_stand_summon_with_skull_token",0),
                 "saved_armor_stand_count":saved.get("saved_armor_stand_instances",0)},
        "output":{"kind":"smoke_particle_source_candidates",
                  "original_smoke_particle_commands":source.get("smoke_hint_candidate",0)},
        "feedback":{"kind":"source_chess_story_cue",
                    "commands_with_chess_reference":source.get("chess_author_text_cue",0)},
        "reset":{"kind":"unknown","verified":False},
        "exact_chess_puzzle_source_chain_proven":False,
        "original_summon_snbt_item_count_evidence":story.get("armorstand_original_summon_snbt_shape_counts",{}),
        "original_source_effect_target_geometry":geometry or {"evidence":"UNAVAILABLE_NOT_INFERRED"},
        "original_saved_skull_count_zero_claim":"NOT_INFERRED_FROM_MISSING_EQUIPMENT",
        "unverified":["skull_pickup_count_zero_behavior","hint_and_piece_matching",
                      "source_version_parity","actual_puzzle_winning_condition"],
        "native":"NOT_RUN",
    }
    result={
        "schema":SCHEMA,
        "source_world_sha256":PIN_WORLD,
        "source_graph_sha256":PIN_GRAPH,
        "project":"SupraCraft CORE original Java 1.8.8",
        "author_license":"UnlikelyWaffle / CC-BY-SA-4.0",
        "scope":"THREE_CREATOR_GROUNDED_SOURCE_STATIC_HYPOTHESES_NOT_ALL_GAMEPLAY",
        "mechanisms":{
            "clickable_redstone_controller":controller,
            "dr_h_finale":finale,
            "chess_head_hint":chess,
        },
        "mechanism_count":3,
        "proven_gameplay_mechanism_count":0,
        "original_native":"NOT_RUN",
        "modern_263_parity":"NOT_RUN",
        "semantic_admission":"NOT_ADMITTED",
        "source_custody":"ORIGINAL_EPHEMERAL__AGGREGATES_ONLY",
        "release_match":"PINNED_V1_4__PUBLIC_LATER_V1_4_1_UNRESOLVED",
        "status":"DRAFT_SOURCE_STATIC_HYPOTHESES",
    }
    serialized=json.dumps(result,sort_keys=True)
    for key in ('"command"','"position"','"node_id"','"target_position"',
                '"CustomName"','"selector"','"objective"','"value"'):
        if key in serialized:raise ValueError("privacy boundary fail")
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--story",type=Path,required=True)
    p.add_argument("--controller",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise SystemExit("refuse overwrite")
    story=json.loads(args.story.read_text())
    control=json.loads(args.controller.read_text())
    result=compile_ir(story,control)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("CORE_SAFE_CREATOR_MECHANISM_IR",json.dumps({
        "schema":SCHEMA,"count":result["mechanism_count"],
        "controller_inputs":result["mechanisms"]["clickable_redstone_controller"]["input"]["action_count"],
        "dr_h_reference_sensor_routes":result["mechanisms"]["dr_h_finale"]["input"]["dr_h_referencing_command_paths"],
        "chess_dynamic_head_actions":result["mechanisms"]["chess_head_hint"]["state"]["skull_bearing_armor_stand_summon_commands"],
        "native":"NOT_RUN",
    },sort_keys=True))

if __name__=="__main__":
    main()
