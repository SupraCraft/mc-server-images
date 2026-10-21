#!/usr/bin/env python3
"""Deterministic Barsoom flora public fixture static tests (no external deps)."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

GEN = Path(__file__).resolve().parents[1] / "fixtures/barsoom/flora/gen_flora_263.py"
spec = importlib.util.spec_from_file_location("flora_generator", GEN)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

class FloraStaticTests(unittest.TestCase):
    def test_exact_five_distinct_categories(self):
        self.assertEqual(len(gen.SPECIES), 5)
        self.assertEqual({v["kind"] for v in gen.SPECIES.values()},
                         {"grass", "shrub", "tree", "crop", "carnivorous"})
        offsets = [tuple(x["offset"]) for x in gen.SPECIES.values()]
        self.assertEqual(len(set(offsets)), 5)

    def test_deterministic_zip_and_namespace_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root) / "a.zip", Path(root) / "b.zip"
            first = gen.build(a)
            second = gen.build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(first["sha256"], hashlib.sha256(a.read_bytes()).hexdigest())
            self.assertEqual(first["sha256"], second["sha256"])
            with zipfile.ZipFile(a) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertTrue(all(n == "pack.mcmeta" or n.startswith(
                    ("data/barsoom_flora/", "data/minecraft/tags/function/load.json")
                ) for n in names))
                meta = json.loads(archive.read("pack.mcmeta"))["pack"]
                self.assertEqual(meta["min_format"], [121, 0])
                self.assertEqual(meta["max_format"], [121, 0])
                self.assertIn(b"schedule function barsoom_flora:hazard_tick 20t replace",
                              archive.read("data/barsoom_flora/function/hazard_tick.mcfunction"))
                demo = archive.read("data/barsoom_flora/function/demo.mcfunction").decode()
                self.assertEqual(demo.count("run function barsoom_flora:species/"), 5)
                self.assertIn("execute unless entity", archive.read(
                    "data/barsoom_flora/function/species/predator_fungus.mcfunction").decode())

    def test_no_automatic_world_mutation_or_host_controls(self):
        docs = gen.documents()
        load = docs["data/barsoom_flora/function/load.mcfunction"].decode()
        self.assertNotIn("setblock", load)
        self.assertNotIn("fill ", load)
        self.assertNotIn("summon", load)
        self.assertNotIn("function barsoom_flora:demo", load)
        for path, content in docs.items():
            if path.endswith(".mcfunction"):
                self.assertNotIn("op ", content.decode())
                self.assertNotIn("gamerule ", content.decode())
                self.assertNotIn("kill @a", content.decode())

if __name__ == "__main__":
    unittest.main()
