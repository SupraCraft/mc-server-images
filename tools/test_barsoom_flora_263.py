#!/usr/bin/env python3
"""No-network static regression checks for determinism and guardrails."""
import json
from pathlib import Path
import tempfile
import unittest
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fixtures/barsoom/flora'))
from gen_flora_263 import build, make

class FloraTests(unittest.TestCase):
    def test_deterministic_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td)/'a.zip', Path(td)/'b.zip'
            first, second = build(a), build(b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(first['sha256'], second['sha256'])
            self.assertEqual(len(first['species']), 5)
            with zipfile.ZipFile(a) as z:
                self.assertIsNone(z.testzip())
                names = set(z.namelist())
                self.assertEqual(names, set(first['members']))
                demo = z.read('data/barsoom_flora/function/demo.mcfunction').decode()
                pulse = z.read('data/barsoom_flora/function/pulse.mcfunction').decode()
                self.assertIn('summon minecraft:marker', demo)
                self.assertIn('distance=..2', pulse)
                self.assertEqual(pulse.count('schedule function'), 1)
                self.assertEqual(json.loads(z.read('pack.mcmeta'))['pack']['min_format'], [121,0])
                self.assertFalse(any(n.startswith('assets/') for n in names))

    def test_fail_closed_bad_species(self):
        spec = json.loads((ROOT/'fixtures/barsoom/flora/species.json').read_text())
        spec['species'][0]['blocks'][0]['state'] = 'minecraft:stone;kill @a'
        with self.assertRaises(AssertionError): make(spec)

    def test_invalid_geometry_fails(self):
        spec = json.loads((ROOT/'fixtures/barsoom/flora/species.json').read_text())
        spec['species'][-1]['origin'] = [80, 0]
        with self.assertRaises(AssertionError): make(spec)

if __name__ == '__main__':
    unittest.main()
