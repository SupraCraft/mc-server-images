import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "fixtures/barsoom/biomes"))
from gen_scarlet_wastes_263 import build

class ScarletAutogenTests(unittest.TestCase):
    def test_determinism_and_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            a,b=Path(temp)/"a.zip",Path(temp)/"b.zip"
            r1,r2=build(a),build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(r1["sha256"],r2["sha256"])
            with zipfile.ZipFile(a) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(set(z.namelist()),set(r1["members"]))
                self.assertFalse(any(p.startswith("data/minecraft/") for p in r1["members"]))
                self.assertFalse(any(p.endswith("dead_sea.json") for p in r1["members"]))
                biome=json.loads(z.read("data/barsoom_habitat/worldgen/biome/scarlet_wastes.json"))
                self.assertEqual(biome["features"][9],["barsoom_habitat:scarlet_auto"])
                self.assertEqual(len(biome["features"]),11)
                placed=json.loads(z.read("data/barsoom_habitat/worldgen/placed_feature/scarlet_auto.json"))
                self.assertEqual(placed["feature"],"barsoom_habitat:scarlet_patch")
                self.assertEqual([x["type"] for x in placed["placement"]],
                                 ["minecraft:count","minecraft:in_square","minecraft:heightmap","minecraft:biome"])
                preset=json.loads(z.read("data/barsoom_habitat/worldgen/world_preset/scarlet_province.json"))
                self.assertEqual(preset["dimensions"]["minecraft:overworld"]["generator"]["biome_source"]["biome"],
                                 "barsoom_habitat:scarlet_wastes")
                self.assertEqual(json.loads(z.read("pack.mcmeta"))["pack"]["min_format"],[121,0])
if __name__=="__main__":unittest.main()
