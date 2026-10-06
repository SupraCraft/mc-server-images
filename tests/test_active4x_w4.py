import copy,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"tools"))
from probe_active4x_two_rivers_w4 import W4Simulation,scenario_for,signature
BASE=json.loads((ROOT/"probes/active4x/two-rivers-v0.1.json").read_text())["scenario"]
SPEC=json.loads((ROOT/"probes/active4x/two-rivers-w4-interventions-v0.1.json").read_text())
class W4Tests(unittest.TestCase):
 def test_all_surfaces_and_conservation(self):
  sigs=set()
  for case in SPEC["cases"]:
   s=scenario_for(BASE,case); a=W4Simulation(s,case["id"]).run(); b=W4Simulation(s,case["id"]).run()
   self.assertTrue(a["balance"]["passed"]); self.assertEqual(a["deterministic_digest"],b["deterministic_digest"]); sigs.add(signature(a))
  self.assertGreaterEqual(len(sigs),3)
 def test_damage_uses_shared_route_memory(self):
  case=next(x for x in SPEC["cases"] if x["id"]=="damage"); r=W4Simulation(scenario_for(BASE,case),"damage").run()
  self.assertIn("secure_route",[d["selected"]["action"] for d in r["decisions"] if d["settlement_id"]=="kilnreach"])
if __name__=="__main__": unittest.main()
