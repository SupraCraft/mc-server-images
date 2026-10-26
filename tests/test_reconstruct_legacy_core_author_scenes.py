"""No-world/source-free adversarial oracles for original CORE finale/chess recovery."""
import hashlib
import json
import unittest

from tools.reconstruct_legacy_core_author_scenes import (
    SCHEMA, analyze, source_command_families, source_selector_signature,
    inspect_saved_scene_chunk, source_exact_join_audit
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
