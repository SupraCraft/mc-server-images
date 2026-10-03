import tempfile
import unittest
from pathlib import Path

from tools.uplift_mcfunction_block_state_snbt import rewrite_text, process_file


class McfunctionBlockStateUpliftTests(unittest.TestCase):
    def test_rewrites_only_block_state_top_level_keys(self):
        src = (
            'summon area_effect_cloud ~ ~ ~ '
            '{CustomName:{text:"Name stays"},'
            'custom_particle:{type:"block",block_state:{Name:"minecraft:light",'
            'Properties:{level:"15"}}},'
            'Other:{Name:"also stays"}}\n'
        )
        out, receipt = rewrite_text(src)
        self.assertIn('CustomName:{text:"Name stays"}', out)
        self.assertIn('Other:{Name:"also stays"}', out)
        self.assertIn(
            'block_state:{id:"minecraft:light",properties:{level:"15"}}',
            out,
        )
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt[0]["change_count"], 2)

    def test_handles_id_without_namespace_and_no_properties(self):
        src = (
            'data merge entity @s '
            '{custom_particle:{type:"block",block_state:{Name:"air"}},Duration:-1}\n'
        )
        out, receipt = rewrite_text(src)
        self.assertIn('block_state:{id:"air"}', out)
        self.assertEqual(receipt[0]["change_count"], 1)

    def test_modern_input_is_unchanged(self):
        src = 'particle block_marker{block_state:{id:"minecraft:light",properties:{level:"0"}}}\n'
        out, receipt = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipt, [])

    def test_unterminated_compound_fails_closed(self):
        with self.assertRaises(ValueError):
            rewrite_text('particle block_marker{block_state:{Name:"minecraft:light"')

    def test_process_file_never_mutates_source(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "old.mcfunction"
            output = root / "new.mcfunction"
            original = 'particle block_marker{block_state:{Name:"minecraft:light"}}\n'
            source.write_text(original, "utf-8")
            receipt = process_file(source, output)
            self.assertEqual(source.read_text("utf-8"), original)
            self.assertIn('block_state:{id:"minecraft:light"}', output.read_text("utf-8"))
            self.assertTrue(receipt["source_unchanged"])


if __name__ == "__main__":
    unittest.main()
