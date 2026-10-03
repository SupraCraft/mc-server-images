import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "modern_mechanisms",
    ROOT/"tools"/"analyze_external_modern_world_mechanisms.py",
)
m=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(m)


class ModernWorldMechanismTests(unittest.TestCase):
    def test_domain_family_classification(self):
        self.assertIn("electrical_redstone",m.families_for("minecraft:redstone_wire"))
        self.assertIn("electrical_redstone",m.families_for("minecraft:stone_button"))
        self.assertIn("mechanical_geometry",m.families_for("minecraft:oak_door"))
        self.assertIn("programmable_control",m.families_for("minecraft:command_block"))
        self.assertIn("inventory_transport",m.families_for("minecraft:hopper"))
        self.assertIn("transformation_production",m.families_for("minecraft:brewing_stand"))
        self.assertIn("artifact_observation",m.families_for("minecraft:jukebox"))
        self.assertIn("artifact_observation",m.families_for("minecraft:oak_sign"))
        self.assertIn("biology_ecology",m.families_for("minecraft:wheat"))
        self.assertIn("biology_ecology",m.families_for("minecraft:red_mushroom_block"))

    def test_single_palette_decodes_without_packed_data(self):
        container={"palette":[{"Name":"minecraft:stone"}]}
        counts=m.decode_palette_counts(container,entries=4096,min_bits=4)
        self.assertEqual(4096,counts["minecraft:stone"])

    def test_empty_key_palette_entry_decodes_modern_id(self):
        container={"palette":[{"":"minecraft:air"}]}
        counts=m.decode_palette_counts(container,entries=4096,min_bits=4)
        self.assertEqual(4096,counts["minecraft:air"])
        self.assertNotIn("Compound",next(iter(counts)))

    def test_unknown_block_does_not_leak_into_domain(self):
        self.assertEqual(set(),m.families_for("minecraft:stone"))

    def test_region_classifier(self):
        self.assertEqual("entity",m.classify_region(pathlib.Path("dimensions/minecraft/overworld/entities/r.0.0.mca")))
        self.assertEqual("poi",m.classify_region(pathlib.Path("dimensions/minecraft/overworld/poi/r.0.0.mca")))
        self.assertEqual("chunk",m.classify_region(pathlib.Path("dimensions/minecraft/overworld/region/r.0.0.mca")))


if __name__=="__main__":
    unittest.main()
