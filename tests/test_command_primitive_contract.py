import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/"bench"/"worldgen"/"causal"/"command"/"command-primitive-contract-v0.json"
TRANSFORMER=ROOT/"tools"/"causal-microscope"/"modern-26.3-agent"/"src"/"main"/"java"/"org"/"supracraft"/"microscope"/"Modern263Transformer.java"
TRACE=ROOT/"tools"/"causal-microscope"/"modern-26.3-agent"/"src"/"main"/"java"/"org"/"supracraft"/"microscope"/"TraceRuntime.java"
WORKFLOW=ROOT/".github"/"workflows"/"worldgen-causal-microscope-modern-263.yml"


class CommandPrimitiveContractTests(unittest.TestCase):
    def contract(self):
        return json.loads(CONTRACT.read_text())

    def test_contract_is_candidate_and_exact_26_3_java(self):
        c=self.contract()
        self.assertEqual(c["status"],"candidate_supported_by_existing_26_3_oracle")
        self.assertEqual(c["authority"]["minecraft_edition"],"java")
        self.assertEqual(c["authority"]["minecraft_version"],"26.3")

    def test_exact_runtime_class_bindings_are_guarded(self):
        src=TRANSFORMER.read_text()
        c=self.contract()
        for binding in c["exact_bindings"]:
            internal=binding["class_name"].replace(".","/")
            self.assertIn(internal,src)
            self.assertIn(binding["class_sha256"],src)
            for hook in binding["hooks"]:
                self.assertIn(hook["id"],src)
                self.assertIn('"'+hook["method"]+'"',src)
                self.assertIn(hook["descriptor"],src)

    def test_runtime_does_not_retain_plaintext_payload_as_evidence(self):
        src=TRACE.read_text()
        self.assertIn('\\\"command_sha256\\\":\\\"',src)
        self.assertIn('\\\"command_verb\\\":\\\"',src)
        self.assertNotIn('\\\"command\\\":\\\"',src)
        self.assertIn("sha256(command)",src)

    def test_workflow_still_guards_bounded_causal_order(self):
        w=WORKFLOW.read_text()
        required=[
            'rows[-1]["data"]["dropped_events"]==0',
            'r["event_type"]=="command_trigger_start"',
            'r["data"].get("command_sha256")==command_hash',
            'r["event_type"]=="command_trigger_end"',
            'start["seq"]<r["seq"]<end["seq"]',
            'start["tick"]==target["tick"]==end["tick"]',
            'r["event_type"]=="command_block_scheduled_tick"',
            'r["event_type"]=="command_block_neighbor"',
            'r["event_type"]=="command_dispatch"',
            'r["data"].get("command_sha256")==command_hash',
        ]
        for needle in required:
            self.assertIn(needle,w)

    def test_contract_keeps_unproved_semantics_unknown(self):
        c=self.contract()
        unknown="\n".join(c["unknowns"])
        for phrase in (
            "conditional chain semantics",
            "success-count/result",
            "electrical-to-command transducer",
            "command state machine",
        ):
            self.assertIn(phrase,unknown)

    def test_promoted_head_evidence_is_zero_drop_no_divergence(self):
        c=self.contract()
        ev=c["runtime_evidence"]
        self.assertEqual(ev["workflow_run_id"],37101462459)
        self.assertEqual(ev["job_id"],111141661480)
        self.assertEqual(ev["observed_event_counts_on_promoted_head"]["dropped_events"],0)
        self.assertFalse(ev["observer_effect"]["semantic_divergence"])


if __name__=="__main__":
    unittest.main()
