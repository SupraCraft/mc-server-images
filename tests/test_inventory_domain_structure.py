import importlib.util
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
P=ROOT/"tools"/"inspect_inventory_domain_structure.py"
S=importlib.util.spec_from_file_location("i",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)
class InventoryStructureTests(unittest.TestCase):
    def test_targets_are_inventory_only(self):
        self.assertEqual(m.CLASS,"net.minecraft.world.level.block.entity.HopperBlockEntity")
        self.assertEqual({x[0] for x in m.TARGETS},{
            "hopper_push_items_tick","hopper_eject_items","hopper_suck_in_items","hopper_inventory_full"})
    def test_no_cross_domain_targets(self):
        text=" ".join(x[0] for x in m.TARGETS)
        self.assertNotIn("command",text); self.assertNotIn("piston",text); self.assertNotIn("comparator",text)
if __name__=="__main__": unittest.main()
