import importlib.util
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
        self.assertEqual("east", d["facing"])
        self.assertEqual([1,0,0], d["facing_vector"])
        self.assertEqual(3, d["delay_redstone_ticks"])
        self.assertTrue(d["powered"])

    def test_comparator_metadata_separates_mode_and_power(self):
        d=causal.metadata_semantics("comparator_off", 0b0110)
        self.assertEqual("south", d["facing"])
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

    def test_relative_setblock_target_resolves_from_command_origin(self):
        _,parts=causal.normalize_command("setblock ~2 ~-1 ~ minecraft:redstone_block")
        targets=causal.command_targets(parts,(10,64,-3))
        self.assertEqual((12,63,-3), targets[0]["position"])

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
