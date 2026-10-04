import tempfile
import unittest
from pathlib import Path

from tools.analyze_map_color_replacement import MAP_COLOR_RE, ITEM_MODEL_RE


class MapColorReplacementTests(unittest.TestCase):
    def test_extracts_legacy_color(self):
        line = 'item replace entity @s hotbar.0 with minecraft:filled_map[map_id=9,map_color=43775] 1'
        self.assertEqual(MAP_COLOR_RE.search(line).group(1), "43775")

    def test_extracts_target_model(self):
        line = 'item replace entity @s hotbar.0 with minecraft:filled_map[map_id=9,item_model="sr/item/vote_race"] 1'
        self.assertEqual(ITEM_MODEL_RE.search(line).group(1), '"sr/item/vote_race"')

    def test_component_regex_stops_at_comma(self):
        line = 'minecraft:filled_map[map_color=10066176,custom_data={x:1b}]'
        self.assertEqual(MAP_COLOR_RE.search(line).group(1), "10066176")


if __name__ == "__main__":
    unittest.main()
