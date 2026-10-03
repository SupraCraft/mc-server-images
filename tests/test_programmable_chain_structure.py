import importlib.util
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
P=ROOT/"tools"/"inspect_programmable_chain_structure.py"
S=importlib.util.spec_from_file_location("p",P); m=importlib.util.module_from_spec(S); S.loader.exec_module(m)
class ProgrammableChainStructureTests(unittest.TestCase):
    def test_targets_are_programmable_only(self):
        self.assertEqual(m.CLASS,"net.minecraft.world.level.block.CommandBlock")
        self.assertEqual({x[0] for x in m.TARGETS},{"command_execute","command_execute_chain","command_tick"})
    def test_no_cross_domain_target_names(self):
        text=" ".join(x[0] for x in m.TARGETS)
        self.assertNotIn("piston",text); self.assertNotIn("hopper",text); self.assertNotIn("redstone",text)
if __name__=="__main__": unittest.main()
