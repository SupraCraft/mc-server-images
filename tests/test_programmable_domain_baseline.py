import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
MOD_PATH=ROOT/"tools"/"validate_programmable_domain_baseline.py"
SPEC=importlib.util.spec_from_file_location("prog",MOD_PATH)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
DOC=ROOT/"bench"/"worldgen"/"causal"/"programmable"/"programmable-domain-baseline-v1.json"

class ProgrammableDomainBaselineTests(unittest.TestCase):
    def test_candidate_validates(self):
        doc=json.loads(DOC.read_text())
        self.assertEqual(mod.validate(doc)["domain"],"programmable")

    def test_no_cross_domain_promotion(self):
        doc=json.loads(DOC.read_text())
        text=" ".join(doc["exclusions"]).lower()
        self.assertIn("no electrical-to-programmable trigger semantics",text)

    def test_runtime_evidence_is_exact_and_fail_closed(self):
        doc=json.loads(DOC.read_text())
        ev=doc["runtime_evidence"]
        self.assertTrue(ev["stock_canary_pass"])
        self.assertTrue(ev["instrumented_canary_pass"])
        self.assertFalse(ev["semantic_divergence"])
        self.assertEqual(ev["dropped_events"],0)

if __name__=="__main__":
    unittest.main()
