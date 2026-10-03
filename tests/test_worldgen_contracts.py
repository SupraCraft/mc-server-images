import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "bench" / "worldgen" / "schemas"

spec = importlib.util.spec_from_file_location(
    "worldgen_policy", ROOT / "tools" / "check_worldgen_public_policy.py"
)
policy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(policy)


class WorldgenSchemaSmokeTests(unittest.TestCase):
    def test_schemas_parse_and_are_closed_at_top_level(self):
        expected = {
            "generator-adapter-v1.schema.json",
            "generator-pipeline-v1.schema.json",
            "worldgen-run-v1.schema.json",
            "worldgen-analysis-v1.schema.json",
            "worldgen-tour-v1.schema.json",
            "human-feedback-annotation-v1.schema.json",
            "persona-trace-v1.schema.json",
            "structured-human-benchmark-v1.schema.json",
        }
        self.assertEqual(expected, {p.name for p in SCHEMA_DIR.glob("*.schema.json")})
        for path in SCHEMA_DIR.glob("*.schema.json"):
            data = json.loads(path.read_text())
            self.assertEqual("object", data["type"], path)
            self.assertFalse(data["additionalProperties"], path)
            self.assertTrue(data["required"], path)

    def test_human_feedback_contract_keeps_cpe_research_namespace(self):
        data = json.loads((SCHEMA_DIR / "human-feedback-annotation-v1.schema.json").read_text())
        concept = data["properties"]["concept_annotations"]["items"]["properties"]["concept_id"]
        self.assertEqual("^research\\.game_world\\.", concept["pattern"])
        roles = data["properties"]["source"]["properties"]["source_role"]["enum"]
        self.assertIn("player_review", roles)
        self.assertIn("author_changelog", roles)
        scopes = data["properties"]["evidence_scope"]["enum"]
        self.assertIn("preference_context", scopes)
        self.assertIn("packaging_installation", scopes)

    def test_reference_world_corpus_is_blind_and_reference_only(self):
        path = ROOT / "bench" / "worldgen" / "reference-worlds" / "reference-world-corpus-v0.json"
        data = json.loads(path.read_text())
        self.assertTrue(data["analysis_blind"])
        self.assertGreaterEqual(len(data["worlds"]), 5)
        forbidden = {"human_themes", "sentiment", "comment_text", "overall_quality_label"}
        for world in data["worlds"]:
            self.assertTrue(world["artifact_rights"])
            self.assertTrue(world["execution_state"])
            self.assertTrue(world["feedback_sources"])
            self.assertFalse(forbidden & set(world))
            for source in world["feedback_sources"]:
                self.assertTrue(source["ref"].startswith("http"))

    def test_qualitative_projection_keeps_human_primary_boundaries(self):
        path = ROOT / "bench" / "worldgen" / "qualitative" / "metric-concept-hypotheses-v1.json"
        data = json.loads(path.read_text())
        by_id = {x["concept_id"]: x for x in data["hypotheses"]}
        self.assertEqual("never_directly_scored", by_id["research.game_world.fun_enjoyment"]["automation_role"])
        self.assertEqual("not_directly_observable", by_id["research.game_world.immersion"]["automation_role"])
        self.assertEqual("not_directly_observable", by_id["research.game_world.coziness_comfort"]["automation_role"])
        self.assertEqual("primary", by_id["research.game_world.perceived_challenge_fairness"]["human_validation"])

    def test_runtime_public_standard_runner_passes(self):
        self.assertEqual([], policy.check_runtime("false", "ubuntu-latest"))

    def test_private_repository_fails_closed(self):
        errors = policy.check_runtime("true", "ubuntu-latest")
        self.assertTrue(any("public repository" in x for x in errors))

    def test_larger_runner_fails_closed(self):
        errors = policy.check_runtime("false", "macos-26-xlarge")
        self.assertTrue(any("allowlist" in x for x in errors))

    def test_self_hosted_fails_closed(self):
        errors = policy.check_runtime("false", "self-hosted")
        self.assertTrue(any("allowlist" in x for x in errors))

    def test_workflow_scanner_rejects_missing_guard_and_billed_label(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "worldgen-bad.yml"
            p.write_text("jobs:\n  bad:\n    runs-on: ubuntu-latest-8-cores\n")
            errors = policy.scan_workflows(pathlib.Path(td))
            self.assertGreaterEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
