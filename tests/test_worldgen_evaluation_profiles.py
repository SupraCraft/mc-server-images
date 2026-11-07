import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("applicability",ROOT/"tools"/"apply_reference_evaluation_profile.py")
mod=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

class EvaluationProfileTests(unittest.TestCase):
    def setUp(self):
        _, self.profiles, self.assignments=mod.load_profiles(
            ROOT/"bench"/"worldgen"/"reference-worlds"/"reference-evaluation-profiles-v0.json"
        )

    def test_savanna_survival_bundle_is_not_applicable(self):
        p=self.profiles[self.assignments["reference.savanna-scramble.v2"]["primary_profile"]]
        self.assertEqual("not_applicable",mod.resolve(p,"vanilla_survival_start_bundle"))
        self.assertEqual("applicable_required",mod.resolve(p,"collectible_discoverability"))

    def test_core_progression_legibility_is_required(self):
        p=self.profiles[self.assignments["reference.core.v1.4"]["primary_profile"]]
        self.assertEqual("applicable_required",mod.resolve(p,"progression_legibility"))
        self.assertEqual("not_applicable",mod.resolve(p,"vanilla_survival_start_bundle"))

    def test_unknown_does_not_become_failure(self):
        p=self.profiles[self.assignments["reference.savanna-scramble.v2"]["primary_profile"]]
        self.assertEqual("unknown",mod.resolve(p,"unmodeled_future_metric"))

if __name__=="__main__":
    unittest.main()
