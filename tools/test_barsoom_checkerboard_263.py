#!/usr/bin/env python3
"""Pure/static checkerboard v0 acceptance (NOT a native Minecraft claim)."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures/barsoom/provinces"))
from gen_checkerboard_263 import BIOMES, PARENT_SHA256, PRESET_ID, SCALE, biome_at, build, cell_size

class CheckerboardTests(unittest.TestCase):
    def test_zip_bit_reproducibility(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"a.zip",Path(d)/"b.zip"
            first,second=build(a),build(b)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            self.assertEqual(first,second)
            self.assertEqual(first["pack_sha256"],hashlib.sha256(a.read_bytes()).hexdigest())
            with ZipFile(a) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(set(z.namelist()),set(first["members"]))

    def test_only_namespaced_new_preset(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/"pack.zip"
            receipt=build(a)
            self.assertEqual(receipt["native_acceptance"],"NOT_RUN")
            self.assertEqual(receipt["production"],"HOLD")
            self.assertEqual(len(receipt["members"]),2)
            self.assertFalse(any(x.startswith("data/minecraft/") for x in receipt["members"]))
            self.assertFalse(any("dead_sea.json" in x or "scarlet_province.json" in x for x in receipt["members"]))
            with ZipFile(a) as z:
                biome_src=json.loads(z.read("data/barsoom_habitat/worldgen/world_preset/checkerboard_provinces.json"))["dimensions"]["minecraft:overworld"]["generator"]["biome_source"]
                self.assertEqual(biome_src,{"type":"minecraft:checkerboard","biomes":BIOMES,"scale":SCALE})
                meta=json.loads(z.read("pack.mcmeta"))["pack"]
                self.assertEqual((meta["min_format"],meta["max_format"]),([121,0],[121,0]))

    def test_cell_geometry_is_8_chunks(self):
        self.assertEqual(cell_size(),128)
        self.assertEqual(cell_size()//16,8)
        self.assertEqual(PRESET_ID,"barsoom_habitat:checkerboard_provinces")
        self.assertEqual(biome_at(64,64),"barsoom_habitat:scarlet_wastes")
        self.assertEqual(biome_at(192,64),"minecraft:badlands")
        self.assertEqual(biome_at(64,192),"minecraft:badlands")
        self.assertEqual(biome_at(192,192),"barsoom_habitat:scarlet_wastes")
        self.assertEqual(biome_at(-64,64),"minecraft:badlands")
        self.assertEqual(biome_at(-64,-64),"barsoom_habitat:scarlet_wastes")
        self.assertEqual(biome_at(128,64),"minecraft:badlands")
        self.assertEqual(biome_at(127,64),"barsoom_habitat:scarlet_wastes")

    def test_oracle_regions_not_border_contaminated(self):
        # Each readback region is 32x32, centered on cell, so >=48 blocks from border.
        for cx,cz in [(64,64),(192,64),(64,192),(192,192),(-64,64)]:
            expected=biome_at(cx,cz)
            for x in range(cx-16,cx+16):
                for z in range(cz-16,cz+16):
                    self.assertEqual(biome_at(x,z),expected)

    def test_parent_custody_exact(self):
        self.assertEqual(set(PARENT_SHA256),{"terrain","habitat","scarlet"})
        self.assertTrue(all(len(v)==64 and all(c in "0123456789abcdef" for c in v) for v in PARENT_SHA256.values()))

if __name__=="__main__":unittest.main()
