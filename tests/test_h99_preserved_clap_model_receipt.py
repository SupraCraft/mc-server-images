"""Permanent falsifiable source-log snapshot after short-lived GHA artifact expiry.

The preserved JSON was reconstructed from the immutable first CLAP interview
job stdout. This test checks the snapshot's EXACT Git blob and independently
derives labels from RAW logits; it is NOT a new model execution or game HIL.
"""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "critic" / "h98-clap-temporal-first-model-receipt.json"
SOURCE_GIT_BLOB = "23f476591c287e5809dbdc96161b645988f3fbdf"
WEIGHT_SHA = "1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb"


class OriginalGhaLogSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.raw = SOURCE.read_bytes()
        self.receipt = json.loads(self.raw)

    def test_stable_original_git_blob_content(self):
        blob = b"blob " + str(len(self.raw)).encode() + b"\x00" + self.raw
        self.assertEqual(hashlib.sha1(blob).hexdigest(), SOURCE_GIT_BLOB)

    def test_status_and_exact_source_pins(self):
        r = self.receipt
        self.assertEqual(r["schema"], "supracraft-h98-clap-temporal-counterfactual/v1")
        self.assertEqual(r["status"], "FIRST_FROZEN_REAL_MODEL_OUTPUT_REVIEW_REQUIRED")
        self.assertEqual(r["weights_sha256"], WEIGHT_SHA)
        self.assertEqual(r["total"], 8)
        self.assertEqual(r["counterfactual_pairs_total"], 4)
        self.assertEqual(r["audio_origin"], "original_synthetic_only")
        self.assertFalse(r["qualified_model"])
        self.assertFalse(r["authentic_minecraft_audio"])
        self.assertFalse(r["human_accepted"])

    def test_independently_recalculate_original_source_log_score(self):
        r = self.receipt
        self.assertEqual(len(r["results"]), 8)
        seen = set()
        pairs = {}
        correct = 0
        invariants = 0
        for row in r["results"]:
            self.assertNotIn(row["id"], seen)
            seen.add(row["id"])
            self.assertEqual(len(row["input_sha256"]), 64)
            self.assertEqual(row["expected"] in ("first_a", "first_b"), True)
            fwd = row["raw_logits_forward_order"]
            rev = row["raw_logits_reverse_order"]
            self.assertEqual(set(fwd), {"first_a", "first_b"})
            self.assertEqual(set(rev), {"first_a", "first_b"})
            first = max(fwd, key=fwd.get)
            reverse = max(rev, key=rev.get)
            self.assertEqual(first, row["predicted_forward_order"])
            self.assertEqual(reverse, row["predicted_reverse_order"])
            same = first == reverse
            self.assertEqual(same, row["prompt_order_invariant"])
            invariants += same
            passed = first == row["expected"]
            self.assertEqual(passed, row["correct"])
            correct += passed
            pairs.setdefault(row["pair_id"], []).append((row["expected"], first))
        self.assertEqual(correct, 3)
        self.assertEqual(invariants, 8)
        self.assertEqual(len(pairs), 4)
        fully_correct = 0
        for entries in pairs.values():
            self.assertEqual({ref for ref,_ in entries}, {"first_a","first_b"})
            fully_correct += all(ref == actual for ref,actual in entries)
        self.assertEqual(fully_correct, 0)
        self.assertEqual(r["correct"], correct)
        self.assertEqual(r["fully_correct_counterfactual_pairs"], fully_correct)

    def test_no_release_authority_in_snapshot(self):
        text = self.raw.decode("utf-8")
        self.assertNotIn("stock_client_verified", text)
        self.assertNotIn("official_gameplay_verified", text)
        self.assertFalse(self.receipt["qualified_model"])


if __name__ == "__main__":
    unittest.main()
