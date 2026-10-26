"""Independent, source-free chess smoke and armor-stand target geometry tests.

This is separate from the refused legacy-SNBT compatibility test modification.
No original source, world, player, native Java, or supplied private artifacts.
"""
import hashlib
import json
import unittest

from tools.reconstruct_legacy_core_author_scenes import (
    chess_source_effect_geometry, source_command_families
)


def commands(lines):
    verified={}
    classes={}
    for i,(cmd,position) in enumerate(lines):
        key=str(i)
        parts=cmd.split()
        verified[key]=({"position":list(position)},cmd,parts)
        classes[key]=source_command_families(cmd)
    return verified,classes


class ChessEffectGeometryTests(unittest.TestCase):
    def test_exact_original_position_overlap_is_noncausal(self):
        verified,classes=commands([
            ('particle smoke 11 65 21 0 0 0 0 1',(5,65,5)),
            ('summon ArmorStand 11 65 21 {Equipment:[{id:"minecraft:skull"}]}',
             (10,65,10))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],
                         {"same_coordinate":1})
        self.assertEqual(x["shared_scene_or_control_flow"],
                         "NOT_ESTABLISHED_BY_SPATIAL_OVERLAP")
        self.assertEqual(x["particle_emission_and_spawn"],"NOT_OBSERVED")
        self.assertNotIn("11,65,21",json.dumps(x))

    def test_relative_author_command_coordinates_not_false_absolute(self):
        verified,classes=commands([
            ('particle smoke ~1 ~ ~-1 0 0 0 0 1',(10,65,10)),
            ('summon ArmorStand ~ ~ ~ {Equipment:[{id:"minecraft:skull"}]}',
             (11,65,9))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],
                         {"same_coordinate":1})

    def test_same_chunk_but_remote_effect_not_a_link(self):
        verified,classes=commands([
            ('particle smoke 10 65 10 0 0 0 0 1',(10,65,10)),
            ('summon ArmorStand 100 65 100 {Equipment:[{id:"minecraft:skull"}]}',
             (10,65,11))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],
                         {"more_than_16_blocks":1})

    def test_radius_bands_are_nearest_not_union_count(self):
        verified,classes=commands([
            ('particle smoke 0 64 0 0 0 0 0 1',(1,64,0)),
            ('summon ArmorStand 3 64 0 {Equipment:[{id:"minecraft:skull"}]}',
             (10,64,10)),
            ('summon ArmorStand 30 64 0 {Equipment:[{id:"minecraft:skull"}]}',
             (10,64,10))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],
                         {"within_3_blocks":1})
        self.assertEqual(x["source_skull_armorstand_spawn_targets_resolved"],2)

    def test_actor_without_skull_not_counted_as_chess_target(self):
        verified,classes=commands([
            ('particle smoke ~ ~ ~ 0 0 0 0 1',(1,64,1)),
            ('summon ArmorStand ~ ~ ~',(1,64,1))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_skull_armorstand_spawn_targets_resolved"],0)
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],
                         {"smoke_without_saved_head_spawn_target_candidates":1})

    def test_dynamic_or_malformed_target_stays_unresolved(self):
        verified,classes=commands([
            ('particle smoke ~bad ~ ~ 0 0 0 0 1',(0,64,0)),
            ('summon ArmorStand ~? ~ ~ {Equipment:[{id:"minecraft:skull"}]}',
             (0,64,0))])
        x=chess_source_effect_geometry(verified,classes)
        self.assertEqual(x["source_target_coordinate_parse_failures"],
                         {"non_resolvable_author_target":2})
        self.assertEqual(x["source_effect_to_spawn_nearest_distance_bands"],{})

    def test_no_original_source_coordinates_are_exported(self):
        verified,classes=commands([
            ('particle smoke ~ ~ ~ 0 0 0 0 1',(123456,250,-123456)),
            ('summon ArmorStand 123456 250 -123456 {Equipment:[{id:"minecraft:skull"}]}',
             (0,65,0))])
        x=json.dumps(chess_source_effect_geometry(verified,classes))
        self.assertNotIn("123456",x)
        self.assertNotIn("-123456",x)
        self.assertNotIn("node_id",x)


if __name__=="__main__":
    unittest.main()
