import json
import tempfile
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from story_volcano_pack import write_volcano_pack

class VolcanoPackTests(unittest.TestCase):
    def test_underwater_pack_has_story_phases_growth_resources_and_emergence(self):
        with tempfile.TemporaryDirectory() as td:
            world=Path(td)/"world"; world.mkdir()
            m=write_volcano_pack(world,88,cx=0,base_y=100,cz=0,underwater=True,water_surface_y=104,max_cycles=3)
            self.assertEqual(m["implementation_mode"],"command_orchestrated")
            self.assertEqual(m["max_top_y"],106)
            self.assertGreaterEqual(m["max_radius"],5)
            funcs=world/"datapacks"/"supracraft_volcano"/"data"/"supracraft_volcano"/"function"
            self.assertTrue((funcs/"start.mcfunction").exists())
            self.assertTrue((funcs/"eruption/3.mcfunction").exists())
            self.assertTrue((funcs/"cool/3.mcfunction").exists())
            cool=(funcs/"cool.mcfunction").read_text()
            self.assertIn("SUPRACRAFT_VOLCANO_COMPLETE",cool)
            self.assertIn("island_emerged",cool)
            eruption=(funcs/"eruption/3.mcfunction").read_text()
            self.assertIn("minecraft:lava",eruption)
            cooled=(funcs/"cool/3.mcfunction").read_text()
            self.assertIn("replace minecraft:lava",cooled)
            self.assertIn("minecraft:gold_ore",cooled)

    def test_surface_profile_does_not_emit_island_gate(self):
        with tempfile.TemporaryDirectory() as td:
            world=Path(td)/"world"; world.mkdir()
            write_volcano_pack(world,88,underwater=False,max_cycles=2)
            cool=(world/"datapacks"/"supracraft_volcano"/"data"/"supracraft_volcano"/"function"/"cool.mcfunction").read_text()
            self.assertNotIn("island_emerged",cool)

    def test_invalid_non_recurring_profile_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            world=Path(td)/"world"; world.mkdir()
            with self.assertRaises(ValueError):
                write_volcano_pack(world,88,max_cycles=1)

if __name__=="__main__":
    unittest.main()
