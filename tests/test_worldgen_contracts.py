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
        }
        self.assertEqual(expected, {p.name for p in SCHEMA_DIR.glob("*.schema.json")})
        for path in SCHEMA_DIR.glob("*.schema.json"):
            data = json.loads(path.read_text())
            self.assertEqual("object", data["type"], path)
            self.assertFalse(data["additionalProperties"], path)
            self.assertTrue(data["required"], path)

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
