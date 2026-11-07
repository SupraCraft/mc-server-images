import importlib.util
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("persona",ROOT/"tools"/"analyze_persona_trace.py")
persona=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(persona)

FIX=ROOT/"bench"/"worldgen"/"personas"/"fixtures"

class PersonaTraceTests(unittest.TestCase):
    def load(self,name):
        return json.loads((FIX/name).read_text())

    def test_direct_trace_has_no_stall_and_completes(self):
        d=persona.analyze(self.load("direct-legible.json"))
        self.assertTrue(d["objective_complete"])
        self.assertEqual(0,d["progress"]["stall_window_count"])
        self.assertGreater(d["movement"]["directness"],0.95)
        self.assertEqual(0,d["actions"]["failed_action_count"])

    def test_confused_loop_detects_stall_backtracking_and_failed_actions(self):
        d=persona.analyze(self.load("confused-loop.json"))
        self.assertFalse(d["objective_complete"])
        self.assertGreaterEqual(d["progress"]["stall_window_count"],1)
        self.assertGreater(d["movement"]["backtrack_ratio"],0.2)
        self.assertGreater(d["actions"]["unproductive_action_rate"],0.4)

    def test_hard_but_progressing_is_not_confusion_control(self):
        d=persona.analyze(self.load("hard-progressing.json"))
        self.assertTrue(d["objective_complete"])
        self.assertEqual(2,d["recovery"]["failure_count"])
        self.assertEqual(2,d["recovery"]["retry_count"])
        self.assertEqual(0,d["progress"]["stall_window_count"])
        self.assertGreater(d["progress"]["progress_event_count"],2)

if __name__=="__main__":
    unittest.main()
