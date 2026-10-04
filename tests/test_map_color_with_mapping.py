import unittest

from tools.uplift_map_color_with_mapping import rewrite_text


class MapColorMappingTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            "43775": "sr/item/vote_race",
            "10066176": "sr/item/vote_selected",
        }

    def test_known_color_rewrites(self):
        src = 'give @s minecraft:filled_map[map_id=9,map_color=43775,custom_data={x:1b}]\n'
        out, receipts, unresolved = rewrite_text(src, self.mapping)
        self.assertIn('item_model="sr/item/vote_race"', out)
        self.assertNotIn("map_color=", out)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(unresolved, [])

    def test_unknown_color_is_preserved(self):
        src = 'give @s minecraft:filled_map[map_color=123]\n'
        out, receipts, unresolved = rewrite_text(src, self.mapping)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])
        self.assertEqual(unresolved[0]["reason"], "unmapped_color")

    def test_existing_model_is_preserved(self):
        src = 'give @s minecraft:filled_map[map_color=43775,item_model="demo:x"]\n'
        out, receipts, unresolved = rewrite_text(src, self.mapping)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])
        self.assertEqual(unresolved[0]["reason"], "item_model_already_present")

    def test_non_filled_map_is_untouched(self):
        src = 'data merge storage demo:x {map_color:43775}\n'
        out, receipts, unresolved = rewrite_text(src, self.mapping)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])
        self.assertEqual(unresolved, [])


if __name__ == "__main__":
    unittest.main()
