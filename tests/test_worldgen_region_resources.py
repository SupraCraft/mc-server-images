import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "region_analyzer", ROOT / "tools" / "analyze_worldgen_region_resources.py"
)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class FakeContainer(dict):
    pass


class PaletteDecodeTests(unittest.TestCase):
    def test_single_palette_value_needs_no_data(self):
        c = FakeContainer(palette=[{"Name":"minecraft:stone"}])
        self.assertEqual([0] * 16, mod.decode_palette_indices(c, 16, 4))

    def test_non_crossing_packed_values(self):
        # Five palette values => block-state storage uses 4 bits, 16 values per 64-bit word.
        vals = [0, 1, 2, 3, 4, 3, 2, 1, 0, 4, 4, 2, 1, 3, 0, 2]
        word = 0
        for i, value in enumerate(vals):
            word |= value << (i * 4)
        c = FakeContainer(
            palette=[{"Name":f"minecraft:test_{i}"} for i in range(5)],
            data=[word],
        )
        self.assertEqual(vals, mod.decode_palette_indices(c, len(vals), 4))

    def test_resource_classification(self):
        self.assertIn("wood", mod.category_for("minecraft:oak_log"))
        self.assertIn("iron", mod.category_for("minecraft:deepslate_iron_ore"))
        self.assertNotIn("diamond", mod.category_for("minecraft:stone"))


if __name__ == "__main__":
    unittest.main()
