import importlib.util
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
P=ROOT/"tools"/"inspect_mechanical_domain_structure.py"
S=importlib.util.spec_from_file_location("m",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)
class MechanicalStructureTests(unittest.TestCase):
    def test_targets_are_mechanical_only(self):
        self.assertEqual(m.CLASS,"net.minecraft.world.level.block.piston.PistonBaseBlock")
        self.assertEqual({x[0] for x in m.TARGETS},{
            "piston_check_if_extend","piston_is_pushable","piston_move_blocks","piston_trigger_event"})
    def test_no_cross_domain_targets(self):
        text=" ".join(x[0] for x in m.TARGETS)
        self.assertNotIn("command",text); self.assertNotIn("hopper",text)
if __name__=="__main__": unittest.main()
