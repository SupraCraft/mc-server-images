#!/usr/bin/env python3
"""Bounded deterministic static contract; native game validation is separate."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures/barsoom/habitat"))
from gen_habitat_263 import build


class HabitatTests(unittest.TestCase):
    def test_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "a.zip", Path(t) / "b.zip"
            first, second = build(a), build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(first["sha256"], second["sha256"])
            with zipfile.ZipFile(a) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(set(z.namelist()), set(first["members"]))
                f = json.loads(z.read("data/barsoom_habitat/worldgen/feature/scarlet_patch.json"))
                self.assertEqual(f["type"], "minecraft:projected_random_patchy_square")
                self.assertEqual(f["block"]["state"]["id"], "minecraft:dead_bush")
                self.assertEqual(f["max_projection_height"], 24)
                self.assertEqual(json.loads(z.read("pack.mcmeta"))["pack"]["min_format"], [121, 0])

    def test_no_override_or_implicit_mutation(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "habitat.zip"
            rec = build(p)
            self.assertFalse(rec["automatic_biome_injection"])
            self.assertFalse(any("minecraft/worldgen/biome" in name for name in rec["members"]))
            self.assertFalse(any("/function/" in name or name.endswith(".mcfunction") for name in rec["members"]))


if __name__ == "__main__":
    unittest.main()
