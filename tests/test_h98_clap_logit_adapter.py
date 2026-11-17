"""Independent synthetic raw-logit tamper tests; NOT a real CLAP model receipt."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adapt_clap_h98_to_critic_score import adapt, label_from_logits


def fake_frozen_pair():
    model = {
        "model": "synthetic-clap-test-double",
        "revision": "pinned-not-real-v1",
        "weights_sha256": "c" * 64,
        "fixture_plan_sha256": "d" * 64,
    }
    manifest = {
        "schema": "supracraft-critic-frozen-manifest/v1",
        "campaign": "synthetic-h98-unit-control",
        "model_constraints": model,
        "cases": [
            {"id": "first", "pair_id": "counterfactual",
             "sha256": "a" * 64, "expected": "first_a",
             "allowed_labels": ["first_a", "first_b"],
             "captions": ["First a synthetic beep", "First a synthetic tone"]},
            {"id": "reverse", "pair_id": "counterfactual",
             "sha256": "b" * 64, "expected": "first_b",
             "allowed_labels": ["first_a", "first_b"],
             "captions": ["First a synthetic beep", "First a synthetic tone"]},
        ],
    }
    source = {
        "schema": "supracraft-h98-clap-temporal-counterfactual/v1",
        "status": "FIRST_FROZEN_REAL_MODEL_OUTPUT_REVIEW_REQUIRED",
        "qualified_model": False,
        "authentic_minecraft_audio": False,
        **model,
        "results": [
            {"id": "first", "pair_id": "counterfactual",
             "input_sha256": "a" * 64,
             "captions": ["First a synthetic beep", "First a synthetic tone"],
             "raw_logits_forward_order": {"first_a": 3.0, "first_b": 2.0},
             "raw_logits_reverse_order": {"first_b": 2.0, "first_a": 3.0},
             "predicted_forward_order": "first_a",
             "predicted_reverse_order": "first_a"},
            {"id": "reverse", "pair_id": "counterfactual",
             "input_sha256": "b" * 64,
             "captions": ["First a synthetic beep", "First a synthetic tone"],
             "raw_logits_forward_order": {"first_a": 1.0, "first_b": 4.0},
             "raw_logits_reverse_order": {"first_b": 4.0, "first_a": 1.0},
             "predicted_forward_order": "first_b",
             "predicted_reverse_order": "first_b"},
        ]
    }
    return manifest, source


class RealReceiptGuards(unittest.TestCase):
    def setUp(self):
        self.manifest, self.source = fake_frozen_pair()

    def test_synthetic_pair_scores_and_is_never_promoted(self):
        r=adapt(self.manifest,self.source)
        self.assertEqual(r["correct"],2)
        self.assertEqual(r["counterfactual_pairs_correct"],1)
        self.assertFalse(r["model_promoted"])
        self.assertFalse(r["qualified_critic"])
        self.assertFalse(r["raw_logit_receipt_authenticated"])

    def test_pair_same_guess_cannot_pass(self):
        z=self.source["results"][1]
        z["raw_logits_forward_order"]={"first_a": 5.0,"first_b": 2.0}
        z["raw_logits_reverse_order"]={"first_b": 2.0,"first_a": 5.0}
        z["predicted_forward_order"]=z["predicted_reverse_order"]="first_a"
        r=adapt(self.manifest,self.source)
        self.assertEqual(r["correct"],1)
        self.assertEqual(r["counterfactual_pairs_correct"],0)

    def test_reordered_receipts_are_equivalent(self):
        a=adapt(self.manifest,self.source)
        self.source["results"].reverse()
        b=adapt(self.manifest,self.source)
        self.assertEqual(a,b)

    def test_raw_ranking_not_preparsed_claim_is_authority(self):
        self.source["results"][0]["predicted_forward_order"]="first_b"
        with self.assertRaisesRegex(ValueError,"PREPARSED_CANDIDATE"):
            adapt(self.manifest,self.source)

    def test_flip_audio_hash_refused(self):
        self.source["results"][0]["input_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"INPUT_MEDIA_HASH_MISMATCH"):
            adapt(self.manifest,self.source)

    def test_model_or_frozen_plan_mismatch_refused(self):
        self.source["revision"]="different-model"
        with self.assertRaisesRegex(ValueError,"MODEL_OR_PLAN"):
            adapt(self.manifest,self.source)
        self.source["revision"]=self.manifest["model_constraints"]["revision"]
        self.source["fixture_plan_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"MODEL_OR_PLAN"):
            adapt(self.manifest,self.source)

    def test_caption_tampering_refused(self):
        self.source["results"][0]["captions"].reverse()
        with self.assertRaisesRegex(ValueError,"PROMPT_TEXT_MISMATCH"):
            adapt(self.manifest,self.source)

    def test_prompt_order_confounded_refused(self):
        self.source["results"][0]["raw_logits_reverse_order"]={"first_a": 1.0,"first_b": 2.0}
        self.source["results"][0]["predicted_reverse_order"]="first_b"
        with self.assertRaisesRegex(ValueError,"PROMPT_ORDER_UNSTABLE_REFUSED"):
            adapt(self.manifest,self.source)

    def test_duplicate_trial_refused(self):
        self.source["results"][1]=copy.deepcopy(self.source["results"][0])
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_OR_DUPLICATE"):
            adapt(self.manifest,self.source)

    def test_non_finite_and_boolean_logits_refused(self):
        item=self.source["results"][0]["raw_logits_forward_order"]
        for invalid in (float("nan"),float("inf"),True,"1.0"):
            item["first_a"]=invalid
            with self.assertRaisesRegex(ValueError,"RAW_LOGITS_NOT_FINITE"):
                adapt(self.manifest,self.source)

    def test_unknown_logits_refused(self):
        self.source["results"][0]["raw_logits_forward_order"]["unsupported"]=3
        with self.assertRaisesRegex(ValueError,"RAW_LOGITS_SCHEMA_REFUSED"):
            adapt(self.manifest,self.source)

    def test_source_self_promoted_refused(self):
        self.source["qualified_model"]=True
        with self.assertRaisesRegex(ValueError,"SOURCE_SELF_AUTHORITY_REFUSED"):
            adapt(self.manifest,self.source)

    def test_exact_logit_ties_abstain_not_success(self):
        for key in ("raw_logits_forward_order","raw_logits_reverse_order"):
            self.source["results"][0][key]={"first_a":1.0,"first_b":1.0}
        self.source["results"][0]["predicted_forward_order"]=None
        self.source["results"][0]["predicted_reverse_order"]=None
        result=adapt(self.manifest,self.source)
        self.assertEqual(result["correct"],1)
        self.assertEqual(result["abstentions_or_invalid"],1)

    def test_case_model_manifest_needs_frozen_labels(self):
        self.manifest["cases"][0]["allowed_labels"]=["first_b","first_a"]
        with self.assertRaisesRegex(ValueError,"H98_LABEL_ORDER_NOT_FROZEN"):
            adapt(self.manifest,self.source)


if __name__=="__main__":
    unittest.main()
