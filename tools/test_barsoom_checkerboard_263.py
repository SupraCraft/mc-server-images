#!/usr/bin/env python3
"""Pure/static checkerboard v0 acceptance (NOT a native Minecraft claim)."""
import ast
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

def native_literal(name):
    # Read declared native control constants without importing a module that
    # depends on server/network helpers unavailable in pure static CI.
    source=ast.parse((ROOT/"tools"/"qualify_barsoom_checkerboard_263.py").read_text(encoding="utf-8"))
    definitions=[node.value for node in source.body if isinstance(node,ast.Assign)
                 and any(isinstance(target,ast.Name) and target.id==name
                         for target in node.targets)]
    if len(definitions)!=1:
        raise AssertionError("native control constant missing or ambiguous")
    return ast.literal_eval(definitions[0])


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

    def test_native_probe_visits_all_four_checkerboard_parity_cells(self):
        # Inspect the native script's declared fixed sites without importing
        # runtime network/server dependencies into the pure static test.
        probe=ROOT/"tools"/"qualify_barsoom_checkerboard_263.py"
        syntax=ast.parse(probe.read_text(encoding="utf-8"))
        declared=[node for node in syntax.body if isinstance(node,ast.Assign)
                  and any(isinstance(target,ast.Name) and target.id=="REGIONS"
                          for target in node.targets)]
        self.assertEqual(len(declared),1)
        sites=ast.literal_eval(declared[0].value)
        self.assertEqual(sites,[(64,64),(192,64),(64,192),(192,192)])
        self.assertEqual([biome_at(x,z) for x,z in sites],
                         [BIOMES[0],BIOMES[1],BIOMES[1],BIOMES[0]])
        self.assertEqual(len(set(sites)),4)

    def test_four_parity_cell_census_stays_clear_of_biome_boundaries(self):
        for cx,cz in ((64,64),(192,64),(64,192),(192,192)):
            b=biome_at(cx,cz)
            for dx,dz in ((-12,0),(12,0),(0,-12),(0,12)):
                self.assertEqual(biome_at(cx+dx,cz+dz),b)
        # Both x and z stripe transitions reverse parity independently.
        self.assertNotEqual(biome_at(127,64),biome_at(128,64))
        self.assertNotEqual(biome_at(64,127),biome_at(64,128))

    def test_negative_centers_include_both_biomes_and_four_quadrants(self):
        centers=native_literal('NEGATIVE_REGIONS')
        self.assertEqual(centers,[(-64,64),(-64,-64),(64,-64),(-192,64)])
        self.assertEqual(
            [biome_at(*pt) for pt in centers],
            [BIOMES[1],BIOMES[0],BIOMES[1],BIOMES[0]])
        for cx,cz in centers:
            for dx,dz in ((0,0),(-12,0),(12,0),(0,-12),(0,12)):
                self.assertEqual(biome_at(cx+dx,cz+dz),biome_at(cx,cz))

    def test_boundary_pairs_cross_exact_native_stripe_boundaries(self):
        pairs=native_literal('BOUNDARY_PAIRS')
        self.assertEqual(len(pairs),4)
        for left,right in pairs:
            self.assertEqual(abs(left[0]-right[0])+abs(left[1]-right[1]),1)
            self.assertNotEqual(biome_at(*left),biome_at(*right))
        self.assertEqual(pairs[0],((127,64),(128,64)))
        self.assertEqual(pairs[1],((64,127),(64,128)))
        self.assertEqual(pairs[2],((-1,64),(0,64)))
        self.assertEqual(pairs[3],((64,-1),(64,0)))

    def test_native_negative_and_boundary_probes_force_load_before_predicates(self):
        # Source-free ordering oracle for the first failure on public run
        # 40650369861: a valid server returns 'position not loaded' unless
        # every added geographic target is force-loaded in the new world.
        native=(ROOT/"tools"/"qualify_barsoom_checkerboard_263.py").read_text(encoding="utf-8")
        for section_start in ("for n,(x,z) in enumerate(NEGATIVE_REGIONS):",
                              "for n,((ax,az),(bx,bz)) in enumerate(BOUNDARY_PAIRS):"):
            section=native.split(section_start,1)
            self.assertEqual(len(section),2)
            probe=section[1]
            self.assertIn("forceload add",probe)
            self.assertLess(probe.index("forceload add"),
                            probe.index("prove(proc,log"))

    def test_parent_custody_exact(self):
        self.assertEqual(set(PARENT_SHA256),{"terrain","habitat","scarlet"})
        self.assertTrue(all(len(v)==64 and all(c in "0123456789abcdef" for c in v) for v in PARENT_SHA256.values()))

if __name__=="__main__":unittest.main()
