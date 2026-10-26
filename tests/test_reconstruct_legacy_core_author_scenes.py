"""No-world/source-free adversarial oracles for original CORE finale/chess recovery."""
import hashlib
import json
import unittest

from tools.reconstruct_legacy_core_author_scenes import (
    SCHEMA, analyze, source_command_families, source_selector_signature,
    inspect_saved_scene_chunk, source_exact_join_audit, summarize_shared_strict_input_roots,
    classify_legacy_kill_subject, shared_dr_h_sensor_effects,
    _kill_type_filter, same_sensor_actor_type_compatibility,
    _read_item_shape, armorstand_summon_item_shapes
)


def fixture(commands):
    nodes=[]
    raw={}
    for i,txt in enumerate(commands):
        ident=f"{10+i},65,20"
        nodes.append({"node_id":ident,"position":[10+i,65,20],
                      "family":"command_block",
                      "command":{"sha256":hashlib.sha256(txt.encode()).hexdigest(),
                                 "verb":txt.lstrip("/").split()[0].lower()}})
        raw[ident]=txt
    graph={"schema":"supracraft-legacy-causal-machinery/1",
           "nodes":nodes,"family_counts":{"command_block":len(nodes)},
           "edges":{"direct_redstone_edges":[],"command_authored_redstone_edges":[],
                    "command_chain_candidates":[]}}
    return graph,raw


class LegacySourceCreatorSceneTests(unittest.TestCase):
    def test_author_dr_h_cue_is_not_proven_runtime(self):
        graph,raw=fixture(['tellraw @p {"text":"Dr. H finale"}'])
        d=analyze(graph,raw)
        self.assertEqual(d["schema"],SCHEMA)
        self.assertEqual(d["creator_story_cue_command_counts"]["dr_h_cue_commands"],1)
        self.assertEqual(d["dr_h_finale"]["clock_actual_behavior"],"NOT_OBSERVED")
        self.assertEqual(d["command_static_links"]["bounded_source_command_class_join_counts"],{})
        self.assertFalse(d["gameplay_promoted"])
        self.assertNotIn("Dr. H finale",json.dumps(d))

    def test_chess_dialogue_is_not_a_skull_or_hinted_logic_edge(self):
        graph,raw=fixture([
            'tellraw @p {"text":"Chess checkmate next"}',
            "particle smoke 12 65 20 0 0 0 0 1"
        ])
        d=analyze(graph,raw)
        self.assertEqual(d["creator_story_cue_command_counts"]["chess_cue_commands"],1)
        self.assertEqual(d["source_command_family_counts"]["smoke_hint_candidate"],1)
        self.assertEqual(d["command_static_links"]["bounded_source_command_class_join_counts"],{})
        self.assertEqual(d["chess"]["player_hint_activation"],"NOT_OBSERVED")

    def test_shared_named_selector_does_not_prove_same_live_actor(self):
        graph,raw=fixture([
            "testfor @e[name=Dr_H,type=Villager]",
            "kill @e[name=Dr_H,type=Villager]",
        ])
        d=analyze(graph,raw)
        self.assertEqual(d["entity_named_selector_potential_shared_presence_kill_signatures"],1)
        self.assertEqual(d["command_static_links"]["exact_source_directed_command_edge_count"],0)
        self.assertIn("NOT_VERIFIED",d["dr_h_finale"]["presence_dialogue_skull_and_death_chain"])

    def test_only_strict_source_graph_edges_make_scene_class_path(self):
        graph,raw=fixture([
            "testfor @e[name=Dr_H]",
            'summon Item ~ ~ ~ {Item:{id:"minecraft:skull",Count:1b}}',
        ])
        graph["edges"]["command_chain_candidates"]=[{
            "source":"10,65,20","target":"11,65,20",
            "edge_type":"conditional_predecessor_success_dependency"}]
        d=analyze(graph,raw)
        self.assertEqual(
            d["command_static_links"]["bounded_source_command_class_join_counts"],
            {"presence_gate_to_skull_action_token":1})
        self.assertEqual(d["command_static_links"]["actual_command_execution"],"NOT_OBSERVED")
        graph["edges"]["command_chain_candidates"]=[]
        self.assertEqual(analyze(graph,raw)["command_static_links"][
            "bounded_source_command_class_join_counts"],{})

    def test_forged_edge_noncommand_endpoint_never_joins(self):
        graph,raw=fixture(["testfor @e[name=DrH]",'say "Dr H"'])
        graph["edges"]["command_chain_candidates"]=[
            {"source":"10,65,20","target":"unknown_id",
             "edge_type":"conditional_predecessor_success_dependency"}]
        d=analyze(graph,raw)
        self.assertEqual(d["command_static_links"]["source_graph_rejection_counts"],
                         {"unqualified_or_noncommand_endpoint":1})
        self.assertEqual(d["command_static_links"]["bounded_source_command_class_join_counts"],{})

    def test_non_vanilla_source_keyword_mention_not_skull_action(self):
        self.assertNotIn("skull_token_in_action",
                         source_command_families('tellraw @p {"text":"skull chess"}'))
        self.assertIn("skull_token_in_action",
                      source_command_families("give @p minecraft:skull 1"))
        self.assertNotIn("smoke_hint_candidate",
                         source_command_families("particle reddust 1 1 1 0 0 0 0 1"))

    def test_selector_name_is_only_extracted_in_entity_selector(self):
        self.assertEqual(source_selector_signature("tellraw @p name=Dr_H"),set())
        self.assertEqual(source_selector_signature("testfor @e[name=Secret,type=Blaze]"),
                         {("Secret","blaze")})
        self.assertEqual(source_selector_signature("testfor @e[type=Blaze]"),set())

    def test_188_saved_armorstand_zero_count_skull_is_explicit_state(self):
        level={"Entities":[
            {"id":"ArmorStand","CustomName":"PRIVATE_CHESS","Equipment":[
                {"id":397,"Count":0},{"id":1,"Count":2}]},
            {"id":"ArmorStand","Equipment":[{"id":397,"Count":1}]},
            {"id":"Villager","CustomName":"PRIVATE_VILLAGER"}
        ],"TileEntities":[{"id":"Skull","Owner":"PRIVATE"},
                          {"id":"Sign","Text1":"PRIVATE STORY"}]}
        d=dict(inspect_saved_scene_chunk(level))
        self.assertEqual(d["saved_armor_stand_instances"],2)
        self.assertEqual(d["saved_armor_stands_with_zero_count_skull"],1)
        self.assertEqual(d["saved_armor_stand_zero_count_skull_slots"],1)
        self.assertEqual(d["saved_armor_stands_with_skull_equipment"],2)
        self.assertEqual(d["saved_skull_block_tile_entities"],1)
        self.assertEqual(d["saved_signs_author_text_redacted"],1)
        self.assertNotIn("PRIVATE",json.dumps(d))

    def test_armorstand_not_assumed_chess_from_global_snapshot(self):
        g,r=fixture(["summon ArmorStand ~ ~ ~", "particle smoke ~ ~ ~ 0 0 0 0 1"])
        out=analyze(g,r,{"saved_armor_stand_instances":952})
        self.assertEqual(out["chess"]["head_armorstand_and_smoke_puzzle"],
                         "NOT_VERIFIED_BY_GLOBAL_COMPONENT_PRESENCE")
        self.assertEqual(out["command_static_links"]["bounded_source_command_class_join_counts"],{})

    def test_smoke_hint_has_qualified_original_button_input_only_with_typed_edge(self):
        graph,raw=fixture(["particle smoke 10 65 20 0 0 0 0 1"])
        graph["nodes"].append({"node_id":"10,64,20","position":[10,64,20],
                               "family":"wooden_button",
                               "metadata_semantics":{"support_vector":[0,1,0]}})
        graph["edges"]["direct_redstone_edges"]=[{
            "source":"10,64,20","target":"10,65,20",
            "edge_type":"legacy_button_attached_support_power"}]
        out=analyze(graph,raw)
        self.assertEqual(out["qualified_sensor_to_scene_command_path_counts"],
                         {"typed_sensor_to_smoke_hint_candidate":1,
                          "typed_sensor_to_particle_feedback":1})
        self.assertEqual(out["qualified_sensor_to_command_route_count"],1)
        graph["edges"]["direct_redstone_edges"][0]["edge_type"]="physical_adjacency_candidate"
        out=analyze(graph,raw)
        self.assertEqual(out["qualified_sensor_to_scene_command_path_counts"],{})

    def test_dynamic_armorstand_skull_and_zero_count_are_source_syntax_only(self):
        c=source_command_families(
            'summon ArmorStand ~ ~ ~ {Equipment:[{id:"minecraft:skull",Count:0b}]}')
        self.assertIn("armor_stand_summon_with_skull_token",c)
        self.assertIn("armor_stand_summon_with_zero_count_token",c)
        c=source_command_families("summon ArmorStand ~ ~ ~")
        self.assertNotIn("armor_stand_summon_with_skull_token",c)

    def test_alternate_armoritems_supported_without_claiming_original_version(self):
        level={"Entities":[{"id":"ArmorStand","ArmorItems":[{"id":"minecraft:skull",
                         "Count":0}]}],"TileEntities":[]}
        d=dict(inspect_saved_scene_chunk(level))
        self.assertEqual(d["saved_armor_stands_with_alternate_armoritems"],1)
        self.assertEqual(d["saved_armor_stand_zero_count_skull_slots"],1)

    def test_distinct_verified_sensor_identity_shared_roles_only(self):
        classes={"c1":{"dr_h_author_text_cue"}, "c2":{"entity_kill"},
                 "c3":{"entity_kill"}, "c4":{"smoke_hint_candidate"},
                 "c5":{"summon_armorstand","armor_stand_summon_with_skull_token"}}
        routes=[("s1","c1","direct_support"),("s1","c2","direct_support"),
                ("s2","c3","direct_support"),("s2","c4","direct_support"),
                ("s3","c5","wire_path")]
        x=summarize_shared_strict_input_roots(routes,classes)
        self.assertEqual(x["dr_h_text_and_entity_kill"],1)
        self.assertEqual(x["smoke_hint_and_armor_stand_spawn"],0)
        self.assertEqual(x["chess_text_and_armor_stand_skull_spawn"],0)
        self.assertNotIn("s1",json.dumps(x))

    def test_summoned_skull_missing_count_is_not_proof_of_zero_count(self):
        raw='summon ArmorStand ~ ~ ~ {Equipment:[{id:"minecraft:skull"}]}'
        c=source_command_families(raw)
        self.assertIn("armor_stand_summon_with_skull_token",c)
        self.assertIn("armor_stand_summon_skull_without_explicit_any_count",c)
        self.assertNotIn("armor_stand_summon_with_zero_count_token",c)

    def test_dr_h_shared_sensor_kill_subject_type_only_no_entity_identity(self):
        d={
            "c1":(None,'tellraw @p {"text":"Dr. H"}',
                  ["tellraw","@p",'{"text":"Dr. H"}']),
            "c2":(None,"kill @e[type=Villager,name=PRIVATE]",
                  ["kill","@e[type=Villager,name=PRIVATE]"]),
        }
        labels={"c1":{"dr_h_author_text_cue"},"c2":{"entity_kill"}}
        obs=shared_dr_h_sensor_effects(
            [("sensor1","c1","direct_support"),
             ("sensor1","c2","direct_support")],labels,d)
        self.assertEqual(obs,{
            "shared_sensor_count":1,
            "dr_h_cue_verb_tellraw":1,
            "removal_target_entity_selector_with_name_filter":1})
        self.assertNotIn("PRIVATE",json.dumps(obs))
        self.assertNotIn("sensor1",json.dumps(obs))

    def test_shared_original_source_actor_summon_not_falsely_labeled_dialogue(self):
        verified={
            "a":(None,"summon Villager ~ ~ ~ {CustomName:Dr.H}",
                 ["summon","Villager","~","~","~","{CustomName:Dr.H}"]),
            "b":(None,"kill @e[type=Villager]",
                 ["kill","@e[type=Villager]"])
        }
        grouped=shared_dr_h_sensor_effects(
            [("root","a","direct_support"),("root","b","direct_support")],
            {"a":{"dr_h_author_text_cue"},"b":{"entity_kill"}},verified)
        self.assertEqual(grouped["dr_h_cue_verb_summon"],1)
        self.assertEqual(grouped["removal_target_entity_selector_with_type_filter"],1)
        self.assertNotIn("Dr.H",json.dumps(grouped))

    def test_kill_subject_shape_no_names(self):
        self.assertEqual(classify_legacy_kill_subject(["kill"]),
                         "implicit_executor_self")
        self.assertEqual(classify_legacy_kill_subject(
            ["kill","@e[type=Zombie,r=10]"]),"entity_selector_with_type_filter")
        self.assertEqual(classify_legacy_kill_subject(
            ["kill","@e[r=10]"]),"entity_selector_other_filters")
        self.assertEqual(classify_legacy_kill_subject(
            ["kill","@p"]),"nearest_player_selector")
        self.assertEqual(classify_legacy_kill_subject(
            ["kill","PRIVATE_PERSON"]),"literal_target_not_disclosed")

    def test_shared_dr_h_exact_positive_actor_type_matches_without_claiming_actor(self):
        verified={
            "spawn":(None,"summon Villager ~ ~ ~ {CustomName:Secret}",
                     ["summon","Villager","~","~","~","{CustomName:Secret}"]),
            "kill":(None,"kill @e[type=minecraft:Villager]",
                    ["kill","@e[type=minecraft:Villager]"])}
        labels={"spawn":{"dr_h_author_text_cue"},"kill":{"entity_kill"}}
        routes=[("sensor","spawn","direct_support"),
                ("sensor","kill","direct_support")]
        out=same_sensor_actor_type_compatibility(routes,labels,verified)
        self.assertEqual(out["source_spawn_and_kill_type_compatible"],1)
        self.assertEqual(out["summon_original_custom_name_field_present"],1)
        self.assertEqual(out["shared_input_groups_with_summon_and_kill"],1)
        self.assertNotIn("Villager",json.dumps(out))
        self.assertNotIn("Secret",json.dumps(out))

    def test_shared_sensor_type_mismatch_and_negated_kill_are_distinct(self):
        v={
            "a":(None,"summon Villager ~ ~ ~",["summon","Villager"]),
            "b":(None,"kill @e[type=Blaze]",["kill","@e[type=Blaze]"])}
        labels={"a":{"dr_h_author_text_cue"},"b":{"entity_kill"}}
        roots=[("s","a","direct_support"),("s","b","direct_support")]
        out=same_sensor_actor_type_compatibility(roots,labels,v)
        self.assertEqual(out["source_spawn_and_kill_type_disjoint"],1)
        v["b"]=(None,"kill @e[type=!Villager]",["kill","@e[type=!Villager]"])
        out=same_sensor_actor_type_compatibility(roots,labels,v)
        self.assertEqual(out["source_type_join_UNRESOLVED"],1)
        self.assertEqual(out["paired_kill_selector_negated_or_empty_type"],1)

    def test_different_sensor_is_not_same_actor_control(self):
        verified={"a":(None,"summon Villager",["summon","Villager"]),
                  "b":(None,"kill @e[type=Villager]",["kill","@e[type=Villager]"])}
        out=same_sensor_actor_type_compatibility(
            [("s1","a","direct_support"),("s2","b","direct_support")],
            {"a":{"dr_h_author_text_cue"},"b":{"entity_kill"}},verified)
        self.assertEqual(out,{})

    def test_malformed_kill_selector_fails_to_unresolved_without_guessing(self):
        self.assertEqual(_kill_type_filter(["kill","@e[type=Villager"])[1],
                         "not_bounded_entity_selector")
        self.assertEqual(_kill_type_filter(["kill","@e[type=!Blaze]"])[1],
                         "negated_or_empty_type")
        self.assertEqual(_kill_type_filter(["kill","@e[name=secret]"])[1],
                         "no_type_filter")

    def test_skull_nbt_decoded_compound_missing_vs_zero_vs_positive(self):
        self.assertEqual(_read_item_shape({"id":"minecraft:skull"})[0],
                         "skull_without_count_tag")
        self.assertEqual(_read_item_shape({"id":"minecraft:skull","Count":0})[0],
                         "skull_explicit_zero_count")
        self.assertEqual(_read_item_shape({"id":397,"Count":2})[0],
                         "skull_explicit_positive_count")
        self.assertEqual(_read_item_shape({"id":"minecraft:stone","Count":0})[0],
                         "other_item")

    def test_injected_snbt_parser_tracks_equipment_skull_missing_count(self):
        calls=[]
        def parser(snbt):
            calls.append(snbt)
            return {"Equipment":[{"id":"minecraft:skull"},{"id":"minecraft:stone","Count":2}]}
        cmd='summon ArmorStand ~ ~ ~ {Equipment:[{id:"minecraft:skull"}]}'
        out=armorstand_summon_item_shapes(cmd,parser)
        self.assertEqual(out["source_snbt_parsed_equipment"],1)
        self.assertEqual(out["equipment_slot_skull_without_count_tag"],1)
        self.assertEqual(out["equipment_skull_slot_seen"],1)
        self.assertTrue(calls[0].startswith("{Equipment:"))
        self.assertNotIn("minecraft:skull",json.dumps(out))

    def test_malformed_source_snbt_not_promoted_to_absent_skull(self):
        def broken(snbt):raise ValueError("unsupported source")
        out=armorstand_summon_item_shapes(
            'summon ArmorStand ~ ~ ~ {Equipment:[}',broken)
        self.assertEqual(out["source_snbt_parse_unresolved"],1)
        self.assertEqual(out["source_snbt_parser_error_class_ValueError"],1)
        self.assertEqual(out["source_snbt_payload_square_brackets_unbalanced"],1)
        self.assertNotIn("no_parsed_skull_slot",out)

    def test_source_snbt_parser_error_diagnostics_are_nonreversible(self):
        def failed(payload):
            raise ValueError("Private: {Equipment:[{id:secret}]} -- private coords")
        out=armorstand_summon_item_shapes(
            'summon ArmorStand ~ ~ ~ {Equipment:[{id:secret}]}',failed)
        self.assertEqual(out["source_snbt_parse_unresolved"],1)
        self.assertEqual(out["source_snbt_parser_error_class_ValueError"],1)
        self.assertEqual(out["source_snbt_payload_braces_balanced"],1)
        self.assertEqual(out["source_snbt_payload_square_brackets_balanced"],1)
        self.assertNotIn("secret",json.dumps(out))
        self.assertNotIn("Private",json.dumps(out))

    def test_original_source_sha_tamper_refused(self):
        g,r=fixture(["tellraw @p hello"])
        r["10,65,20"]="tellraw @p forged"
        with self.assertRaisesRegex(ValueError,"partial/forged"):
            analyze(g,r)

    def test_author_marker_not_native_promotion(self):
        g,r=fixture(["particle smoke 1 1 1 0 0 0 0 1"])
        out=analyze(g,r)
        self.assertEqual(out["original_java_188_native"],"NOT_RUN")
        self.assertEqual(out["modern_minecraft_263_parity"],"NOT_RUN")
        self.assertFalse(out["gameplay_promoted"])


if __name__=="__main__":
    unittest.main()
