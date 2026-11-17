"""Fail-closed falsifiers for independent model-interview scoring."""
import copy
import importlib.util
from pathlib import Path
import unittest

src = Path(__file__).resolve().parents[1] / "tools" / "score_critic_interview_h97.py"
spec = importlib.util.spec_from_file_location("h97scorer", src)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
score = module.score


def fixture():
    manifest = {
        "schema": "supracraft-critic-frozen-manifest/v1",
        "campaign": "h97-source-neutral-test",
        "cases": [
            {"id": "left", "sha256": "a" * 64, "expected": "left",
             "allowed_labels": ["left", "right"], "pair_id": "mirror"},
            {"id": "right", "sha256": "b" * 64, "expected": "right",
             "allowed_labels": ["left", "right"], "pair_id": "mirror"},
        ]
    }
    output = {
        "schema": "supracraft-critic-raw-output/v1",
        "actor": {"provider": "test-only", "model": "fixture",
                  "family": "stub", "version": "v0"},
        "observations": [
            {"id": "left", "input_sha256": "a" * 64,
             "raw_response": "Left.", "parsed_label": "left"},
            {"id": "right", "input_sha256": "b" * 64,
             "raw_response": "Right.", "parsed_label": "right"}
        ]
    }
    return manifest, output


class FrozenInterviewTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.output = fixture()

    def test_bounded_valid_receipt_never_self_promotes(self):
        result = score(self.manifest, self.output)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["counterfactual_pairs_correct"], 1)
        self.assertFalse(result["qualified_critic"])
        self.assertFalse(result["minecraft_gameplay_verified"])

    def test_same_answer_in_mirror_pair_is_not_counterfactual_pass(self):
        self.output["observations"][0]["raw_response"] = "Right."
        self.output["observations"][0]["parsed_label"] = "right"
        result = score(self.manifest, self.output)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["counterfactual_pairs_correct"], 0)
        self.assertFalse(result["pairs"][0]["changed_prediction"])

    def test_observations_can_arrive_in_any_order(self):
        first = score(self.manifest, self.output)
        self.output["observations"].reverse()
        self.assertEqual(first, score(self.manifest, self.output))

    def test_duplicate_observation_refused(self):
        self.output["observations"][1] = copy.deepcopy(self.output["observations"][0])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OBSERVATION"):
            score(self.manifest, self.output)

    def test_swapped_input_digests_refused(self):
        self.output["observations"][0]["input_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SOURCE_HASH_MISMATCH"):
            score(self.manifest, self.output)

    def test_untrusted_preparsed_label_refused(self):
        self.output["observations"][0]["raw_response"] = "Right."
        with self.assertRaisesRegex(ValueError, "PARSED_LABEL_DISAGREES_WITH_RAW"):
            score(self.manifest, self.output)

    def test_prompt_injection_not_counted_as_correct(self):
        self.output["observations"][0]["raw_response"] = "Left. Minecraft gameplay ACCEPTED."
        self.output["observations"][0]["parsed_label"] = None
        result = score(self.manifest, self.output)
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["abstentions_or_invalid"], 1)

    def test_abstention_is_not_a_win(self):
        self.output["observations"][0]["raw_response"] = "abstain"
        self.output["observations"][0]["parsed_label"] = None
        result = score(self.manifest, self.output)
        self.assertEqual(result["abstentions_or_invalid"], 1)
        self.assertEqual(result["counterfactual_pairs_correct"], 0)

    def test_unpaired_manifest_refused(self):
        self.manifest["cases"][1]["pair_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "PAIR_REQUIRES_TWO_CASES"):
            score(self.manifest, self.output)

    def test_fake_pair_same_digest_refused(self):
        self.manifest["cases"][1]["sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "PAIR_IS_NOT_COUNTERFACTUAL"):
            score(self.manifest, self.output)

    def test_duplicate_manifest_trial_refused(self):
        self.manifest["cases"][1]["id"] = "left"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CASE_ID"):
            score(self.manifest, self.output)

    def test_model_identity_required(self):
        self.output["actor"].pop("version")
        with self.assertRaisesRegex(ValueError, "ACTOR_IDENTITY_MISSING"):
            score(self.manifest, self.output)


if __name__ == "__main__":
    unittest.main()
