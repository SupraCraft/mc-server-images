"""Source-free red-team tests for comprehensive original CORE gameplay channels."""
import json
import unittest

from tools.inventory_legacy_core_gameplay_channels import (
    CHANNELS, CHANNEL_IDS, classify_blocks, inspect_tiles,
    inspect_entities, allow_family, TILE_FAMILIES, ENTITY_FAMILIES,
)


class AllGameplayChannelsTests(unittest.TestCase):
    def test_all_required_channels_present_in_registry(self):
        needed={"mechanical_kinematics","electrical_signal_logic",
                "inventory_storage_transport","magical_potions_enchanting",
                "entities_actor_spawning","environmental_hazard_physics",
                "traversal_navigation","presentation_signals_and_art",
                "control_commands","multiplayer_progression_state"}
        self.assertEqual(set(CHANNELS), needed)

    def test_piston_and_rail_are_mechanical_without_needing_command(self):
        result,_,_=classify_blocks([29,33,66,27])
        self.assertEqual(result["mechanical_kinematics"],4)
        self.assertEqual(result.get("control_commands",0),0)

    def test_redstone_power_and_wire_appear_electrical(self):
        result,_,_=classify_blocks([55,75,93,149,152,69,77])
        self.assertEqual(result["electrical_signal_logic"],7)

    def test_brewing_beacon_and_enchantment_are_magic_family(self):
        result,_,_=classify_blocks([116,117,118,138,90,119,130,52])
        self.assertEqual(result["magical_potions_enchanting"],8)

    def test_inventory_machines_detect_without_command_blocks(self):
        result,_,_=classify_blocks([54,146,154,158,23,117])
        self.assertEqual(result["inventory_storage_transport"],6)

    def test_survival_hazards_traversal_and_portals_are_not_omitted(self):
        result,_,_=classify_blocks([8,10,30,51,79,81,90,119])
        self.assertEqual(result["environmental_hazard_physics"],6)
        self.assertEqual(result["traversal_navigation"],5)

    def test_overlapping_channels_are_not_unique_mechanisms(self):
        result,nonair,other=classify_blocks([0,0,137])
        self.assertEqual(nonair,1)
        self.assertEqual(other,0)
        self.assertEqual(result["control_commands"],1)
        self.assertEqual(result["electrical_signal_logic"],1)

    def test_unknown_block_not_fabricated_as_mechanism(self):
        result,nonair,other=classify_blocks([4095])
        self.assertEqual(nonair,1)
        self.assertEqual(other,1)
        self.assertEqual(result,{})

    def test_named_entity_never_emitted(self):
        tc, channel=inspect_entities([{
            "id":"ArmorStand","CustomName":"PRIVATE_SPOILER",
            "Equipment":[{"id":1}], "ActiveEffects":[{"Id":1}]
        }])
        s=json.dumps([tc,channel])
        self.assertNotIn("PRIVATE_SPOILER",s)
        self.assertEqual(tc["entities_with_custom_name_redacted"],1)
        self.assertEqual(channel["magical_potions_enchanting"],1)

    def test_magic_item_inventory_and_written_book_pages_are_aggregated(self):
        tc,ch=inspect_tiles([{
            "id":"Chest",
            "Items":[
                {"id":373,"Count":1,"tag":{"CustomPotionEffects":[{"Id":1}]}},
                {"id":403,"tag":{"StoredEnchantments":[{"id":16}]}},
                {"id":387,"tag":{"pages":["SECRET WRITTEN CONTENT"]}},
            ]}])
        self.assertEqual(tc["item_stacks"],3)
        self.assertEqual(tc["legacy_potion_stacks"],1)
        self.assertEqual(tc["enchanted_book_stacks"],1)
        self.assertEqual(tc["books_with_written_pages"],1)
        self.assertNotIn("SECRET WRITTEN CONTENT",json.dumps([tc,ch]))
        self.assertGreater(ch["magical_potions_enchanting"],0)

    def test_spawners_and_traders_captured(self):
        tc,ch=inspect_tiles([{"id":"MobSpawner","SpawnData":{"id":"SECRET_MOB"}}])
        self.assertEqual(tc["spawner_nbt_instances"],1)
        ec,ech=inspect_entities([{"id":"Villager","Offers":{"Recipes":[{"buy":"SECRET"}]}}])
        self.assertEqual(ec["entities_with_trade_offers"],1)
        self.assertNotIn("SECRET",json.dumps([tc,ch,ec,ech]))

    def test_item_frames_paintings_and_signs_capture_presentation(self):
        tc,_=inspect_tiles([{"id":"Sign","Text1":"PRIVATE SIGN"},
                           {"id":"Note","note":4}])
        ec,_=inspect_entities([{"id":"ItemFrame","Item":{"id":"PRIVATE"}},
                               {"id":"Painting","Motive":"PRIVATE"}])
        self.assertEqual(tc["sign_text_sources_redacted"],1)
        self.assertEqual(ec["entity_itemframe"],1)
        self.assertEqual(ec["entity_painting"],1)
        self.assertNotIn("PRIVATE",json.dumps([tc,ec]))

    def test_source_specific_names_are_not_exposed(self):
        self.assertEqual(allow_family("SECRET PLUGIN",TILE_FAMILIES),"unclassified")
        self.assertEqual(allow_family("minecraft:witch",ENTITY_FAMILIES),"witch")
        self.assertEqual(allow_family("CustomMagicalTotem",ENTITY_FAMILIES),"unclassified")

    def test_riding_mounts_and_equipment_are_considered(self):
        ec,_=inspect_entities([{"id":"Boat","Riding":{}},
                               {"id":"Minecart","Equipment":[{"id":1}]}])
        self.assertEqual(ec["entities_with_riding_or_passenger_links"],1)
        self.assertEqual(ec["entities_with_equipment_metadata"],1)


if __name__=="__main__":
    unittest.main()
