import hashlib
import importlib.util
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("causal",ROOT/"tools"/"analyze_legacy_causal_machinery.py")
causal=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(causal)

class CausalMachineryPrimitiveTests(unittest.TestCase):
    def test_repeater_metadata_decodes_orientation_delay_and_power(self):
        d=causal.metadata_semantics("repeater_on", 0b1001)
        self.assertEqual("west", d["facing"])
        self.assertEqual([-1,0,0], d["facing_vector"])
        self.assertEqual(3, d["delay_redstone_ticks"])
        self.assertTrue(d["powered"])

    def test_exact_1_8_8_horizontal_diode_metadata_uses_s_w_n_e_order(self):
        expected={
            0:("south",[0,0,1]),
            1:("west",[-1,0,0]),
            2:("north",[0,0,-1]),
            3:("east",[1,0,0]),
        }
        for meta,(facing,vector) in expected.items():
            for family in ("repeater_off","comparator_off"):
                with self.subTest(meta=meta,family=family):
                    d=causal.metadata_semantics(family,meta)
                    self.assertEqual(facing,d["facing"])
                    self.assertEqual(vector,d["facing_vector"])

    def test_comparator_metadata_separates_mode_and_power(self):
        d=causal.metadata_semantics("comparator_off", 0b0110)
        self.assertEqual("north", d["facing"])
        self.assertEqual([0,0,-1], d["facing_vector"])
        self.assertEqual("subtract", d["mode"])
        self.assertFalse(d["powered"])

    def test_command_block_metadata_decodes_conditional_facing(self):
        d=causal.metadata_semantics("chain_command_block", 0b1010)
        self.assertEqual("north", d["facing"])
        self.assertTrue(d["conditional"])

    def test_trapped_chest_has_two_distinct_channels(self):
        d=causal.metadata_semantics("trapped_chest", 2)
        self.assertEqual("dynamic_not_stored_in_block_metadata", d["open_sensor_state"])
        self.assertEqual("readable_by_comparator", d["inventory_signal_state"])

    def test_tellraw_payload_fingerprints_retain_hashes_not_text(self):
        command='tellraw @a "private calibration phrase"'
        d=causal.presentation_payload_fingerprints(command,"tellraw")
        self.assertEqual("tellraw_json",d["kind"])
        self.assertEqual("parsed",d["parse_status"])
        self.assertEqual("string",d["json_kind"])
        self.assertEqual(
            hashlib.sha256(
                '"private calibration phrase"'.encode("utf-8")
            ).hexdigest(),
            d["wire_json_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(
                "private calibration phrase".encode("utf-8")
            ).hexdigest(),
            d["literal_text_sha256"],
        )
        self.assertNotIn("private calibration phrase",json.dumps(d))

    def test_non_tellraw_command_has_no_presentation_payload_fingerprint(self):
        self.assertIsNone(
            causal.presentation_payload_fingerprints("clear @a","clear")
        )

    def test_relative_setblock_target_resolves_from_command_origin(self):
        _,parts=causal.normalize_command("setblock ~2 ~-1 ~ minecraft:redstone_block")
        targets=causal.command_targets(parts,(10,64,-3))
        self.assertEqual((12,63,-3), targets[0]["position"])

    def test_setblock_compact_world_state_write_keeps_only_bounded_class(self):
        _,parts=causal.normalize_command(
            "setblock ~2 ~-1 ~ minecraft:redstone_block 0 replace"
        )
        self.assertEqual(
            [{
                "position":[12,63,-3],
                "state_class":"redstone_block",
                "write_kind":"setblock",
            }],
            causal.command_authored_world_state_writes(parts,(10,64,-3)),
        )

        _,air_parts=causal.normalize_command("setblock 1 2 3 air")
        self.assertEqual(
            [{
                "position":[1,2,3],
                "state_class":"air",
                "write_kind":"setblock",
            }],
            causal.command_authored_world_state_writes(air_parts,(0,0,0)),
        )

        _,other_parts=causal.normalize_command("setblock 1 2 3 stone")
        self.assertEqual(
            [],
            causal.command_authored_world_state_writes(other_parts,(0,0,0)),
        )

    def test_setblock_redstone_power_is_exact_and_narrow(self):
        source=(0,70,0)
        authored=(10,65,10)
        command_below=(10,64,10)
        rear_input_diode=(10,65,11)
        wrong_side_diode=(11,65,10)
        adjacent_wire=(9,65,10)
        machinery={
            source:{
                "family":"command_block",
                "command":{
                    "authored_world_state_writes":[{
                        "position":list(authored),
                        "state_class":"redstone_block",
                        "write_kind":"setblock",
                    }],
                },
            },
            command_below:{
                "family":"command_block",
                "metadata_semantics":{},
            },
            rear_input_diode:{
                "family":"repeater_off",
                "metadata_semantics":causal.metadata_semantics(
                    "repeater_off",2
                ),
            },
            wrong_side_diode:{
                "family":"repeater_off",
                "metadata_semantics":causal.metadata_semantics(
                    "repeater_off",2
                ),
            },
            adjacent_wire:{
                "family":"redstone_wire",
                "metadata_semantics":{},
            },
        }
        edges=causal.legacy_command_authored_redstone_edges(machinery)
        triples={(e["source"],e["target"],e["edge_type"]) for e in edges}
        self.assertIn(
            (
                "0,70,0","10,64,10",
                "legacy_setblock_redstone_block_direct_command_power",
            ),
            triples,
        )
        self.assertIn(
            (
                "0,70,0","10,65,11",
                "legacy_setblock_redstone_block_diode_rear_input",
            ),
            triples,
        )
        self.assertFalse(any(e["target"]=="11,65,10" for e in edges))
        self.assertFalse(any(e["target"]=="9,65,10" for e in edges))
        self.assertTrue(all(e["certainty"]=="strong" for e in edges))

    def test_repeater_command_block_conduction_is_collinear_and_narrow(self):
        repeater=(0,65,0)
        conductor=(0,65,1)
        dust=(0,65,2)
        side_dust=(1,65,1)
        machinery={
            repeater:{
                "family":"repeater_off",
                "metadata_semantics":causal.metadata_semantics(
                    "repeater_off",2
                ),
            },
            conductor:{
                "family":"command_block",
                "metadata_semantics":{},
            },
            dust:{
                "family":"redstone_wire",
                "metadata_semantics":{},
            },
            side_dust:{
                "family":"redstone_wire",
                "metadata_semantics":{},
            },
        }
        edges=causal.legacy_repeater_command_block_conduction_edges(machinery)
        self.assertEqual(1,len(edges))
        edge=edges[0]
        self.assertEqual("0,65,0",edge["source"])
        self.assertEqual("0,65,2",edge["target"])
        self.assertEqual("0,65,1",edge["via"])
        self.assertEqual(
            "legacy_repeater_through_command_block_to_dust_power",
            edge["edge_type"],
        )
        self.assertEqual("strong",edge["certainty"])

    def test_fill_emits_both_region_boundaries(self):
        _,parts=causal.normalize_command("fill 1 2 3 4 5 6 minecraft:stone")
        targets=causal.command_targets(parts,(0,0,0))
        self.assertEqual(["region_start","region_end"], [x["kind"] for x in targets])
        self.assertEqual((1,2,3),targets[0]["position"])
        self.assertEqual((4,5,6),targets[1]["position"])

    def test_scoreboard_set_is_write_and_test_is_read(self):
        _,set_parts=causal.normalize_command("scoreboard players set @p keys 1")
        _,test_parts=causal.normalize_command("scoreboard players test @p keys 1")
        self.assertEqual([{"objective":"keys","access":"write"}],causal.scoreboard_refs(set_parts))
        self.assertEqual([{"objective":"keys","access":"read"}],causal.scoreboard_refs(test_parts))

    def test_button_metadata_decodes_facing_and_attached_support(self):
        cases={
            1:("east",[1,0,0],[-1,0,0]),
            2:("west",[-1,0,0],[1,0,0]),
            3:("south",[0,0,1],[0,0,-1]),
            4:("north",[0,0,-1],[0,0,1]),
            0:("down",[0,-1,0],[0,1,0]),
            5:("up",[0,1,0],[0,-1,0]),
        }
        for meta,(facing,facing_vector,support_vector) in cases.items():
            with self.subTest(meta=meta):
                d=causal.metadata_semantics("wooden_button",meta)
                self.assertEqual(facing,d["facing"])
                self.assertEqual(facing_vector,d["facing_vector"])
                self.assertEqual(support_vector,d["support_vector"])
                self.assertFalse(d["powered"])

    def test_pressure_plate_metadata_separates_ordinary_and_weighted_storage(self):
        stone=causal.metadata_semantics("stone_pressure_plate",1)
        wood=causal.metadata_semantics("wooden_pressure_plate",1)
        light=causal.metadata_semantics("light_weighted_pressure_plate",7)
        heavy=causal.metadata_semantics("heavy_weighted_pressure_plate",3)

        self.assertTrue(stone["powered"])
        self.assertEqual(1,stone["stored_state"])
        self.assertEqual(15,stone["power_level"])
        self.assertEqual("living_entities_only",stone["occupancy_semantics"])
        self.assertEqual([0,-1,0],stone["support_vector"])

        self.assertEqual("all_triggering_entities",wood["occupancy_semantics"])
        self.assertEqual(15,wood["power_level"])

        self.assertEqual(7,light["stored_state"])
        self.assertEqual(7,light["power_level"])
        self.assertEqual(15,light["entity_count_capacity"])
        self.assertEqual(150,heavy["entity_count_capacity"])

    def test_pressure_plate_direct_support_power_is_strong_and_narrow(self):
        plate=(10,65,10)
        support=(10,64,10)
        side=(11,65,10)
        machinery={
            plate:{
                "family":"wooden_pressure_plate",
                "metadata_semantics":causal.metadata_semantics("wooden_pressure_plate",0),
            },
            support:{"family":"command_block","metadata_semantics":{}},
            side:{"family":"command_block","metadata_semantics":{}},
        }
        edges=causal.legacy_direct_redstone_edges(machinery)
        matches=[
            e for e in edges
            if e["edge_type"]=="legacy_pressure_plate_support_power"
        ]
        self.assertEqual(1,len(matches))
        self.assertEqual("10,65,10",matches[0]["source"])
        self.assertEqual("10,64,10",matches[0]["target"])
        self.assertEqual("strong",matches[0]["certainty"])
        self.assertFalse(any(e.get("target")=="11,65,10" for e in matches))

    def test_button_attached_command_block_is_strong_directed_power_edge(self):
        button=(25,66,-5)
        support=(26,66,-5)
        machinery={
            button:{
                "family":"wooden_button",
                "metadata_semantics":causal.metadata_semantics("wooden_button",2),
            },
            support:{"family":"command_block","metadata_semantics":{}},
        }
        edges=causal.legacy_direct_redstone_edges(machinery)
        matches=[
            e for e in edges
            if e["edge_type"]=="legacy_button_attached_support_power"
        ]
        self.assertEqual(1,len(matches))
        self.assertEqual("25,66,-5",matches[0]["source"])
        self.assertEqual("26,66,-5",matches[0]["target"])
        self.assertEqual("strong",matches[0]["certainty"])

    def test_direct_legacy_dust_edges_keep_sensor_direction(self):
        machinery={
            (0,0,0):{"family":"lever"},
            (1,0,0):{"family":"redstone_wire"},
            (2,0,0):{"family":"redstone_wire"},
            (3,0,0):{"family":"command_block"},
        }
        edges=causal.legacy_direct_redstone_edges(machinery)
        triples={(e["source"],e["target"],e["edge_type"]) for e in edges}
        self.assertIn(("0,0,0","1,0,0","legacy_sensor_direct_dust_power"),triples)
        self.assertIn(("1,0,0","2,0,0","legacy_dust_horizontal_connection"),triples)
        self.assertIn(("2,0,0","3,0,0","legacy_dust_direct_component_power"),triples)
        self.assertNotIn(("1,0,0","0,0,0","legacy_sensor_direct_dust_power"),triples)

    def test_exact_1_8_8_wire_above_command_power_is_strong_and_directional(self):
        wire=(302,95,-67)
        command_below=(302,94,-67)
        command_above=(302,96,-67)
        side_command=(303,95,-67)
        machinery={
            wire:{"family":"redstone_wire"},
            command_below:{"family":"command_block"},
            command_above:{"family":"command_block"},
            side_command:{"family":"command_block"},
        }
        edges=causal.legacy_direct_redstone_edges(machinery)
        exact=[
            e for e in edges
            if e["edge_type"]=="legacy_dust_downward_command_power"
        ]
        self.assertEqual(1,len(exact))
        self.assertEqual("302,95,-67",exact[0]["source"])
        self.assertEqual("302,94,-67",exact[0]["target"])
        self.assertEqual("strong",exact[0]["certainty"])
        self.assertFalse(any(e["target"]=="302,96,-67" for e in exact))
        self.assertFalse(any(e["target"]=="303,95,-67" for e in exact))

    def test_repeater_and_comparator_are_not_bypassed_as_generic_wire_sinks(self):
        machinery={
            (0,0,0):{"family":"redstone_wire"},
            (1,0,0):{"family":"repeater_off"},
            (0,0,1):{"family":"comparator_off"},
        }
        edges=causal.legacy_direct_redstone_edges(machinery)
        self.assertEqual([],edges)

if __name__=="__main__":
    unittest.main()
