import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools/analyze_legacy_uplift_candidates.py"
CATALOG = REPO / "bench/worldgen/corpora/legacy-uplift-rules-26.3-v1.json"


def run_tool(*args):
    p = subprocess.run(
        [sys.executable, str(TOOL), *map(str, args)],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    return p


class LegacyUpliftTests(unittest.TestCase):
    def make_tree(self, root: Path):
        pred = root / "data/demo/predicate/is_here.json"
        pred.parent.mkdir(parents=True)
        pred.write_text(json.dumps({
            "condition": "minecraft:entity_properties",
            "entity": "this",
            "predicate": {"location": {"dimension": "minecraft:overworld"}},
        }), encoding="utf-8")

        loot = root / "data/demo/loot_table/test.json"
        loot.parent.mkdir(parents=True)
        loot.write_text(json.dumps({
            "pools": [{"conditions": [{"condition": "minecraft:random_chance", "chance": 0.5}]}]
        }), encoding="utf-8")

        feature = root / "data/demo/worldgen/configured_feature/stone.json"
        feature.parent.mkdir(parents=True)
        feature.write_text(json.dumps({
            "type": "minecraft:ore",
            "config": {
                "target_state": {
                    "Name": "minecraft:stone",
                    "Properties": {"axis": "y"}
                }
            }
        }), encoding="utf-8")

        carver = root / "data/demo/worldgen/configured_carver/cave.json"
        carver.parent.mkdir(parents=True)
        carver.write_text('{"type":"minecraft:cave","config":{}}', encoding="utf-8")

        fn = root / "data/demo/function/legacy.mcfunction"
        fn.parent.mkdir(parents=True)
        fn.write_text(
            "scoreboard players operation #tmp calc = #a calc\n"
            "summon minecraft:armor_stand ~ ~ ~ {Marker:1b,Tags:[\"legacy\"]}\n"
            "give @s minecraft:stick{CustomModelData:12}\n",
            encoding="utf-8",
        )

    def test_scan_separates_safe_and_advisory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_tree(root)
            p = run_tool(root, "--catalog", CATALOG)
            self.assertEqual(p.returncode, 0, p.stderr)
            data = json.loads(p.stdout)
            by_rule = data["counts_by_rule"]
            self.assertEqual(by_rule["predicate_condition_to_type"], 1)
            self.assertEqual(by_rule["worldgen_configured_feature_directory_to_feature"], 1)
            self.assertEqual(by_rule["worldgen_configured_carver_directory_to_carver"], 1)
            self.assertEqual(by_rule["block_state_Name_Properties_to_id_properties"], 1)
            self.assertGreaterEqual(by_rule["scoreboard_arithmetic_to_context_compute"], 1)
            self.assertGreaterEqual(by_rule["legacy_item_nbt_to_data_components"], 1)

            # The loot-table condition must not be treated as a safe predicate migration.
            safe_pred_paths = [
                x["path"] for x in data["findings"]
                if x["rule_id"] == "predicate_condition_to_type"
            ]
            self.assertEqual(safe_pred_paths, ["data/demo/predicate/is_here.json"])

    def test_apply_safe_materializes_separate_tree_and_discharges_safe_findings(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "source"
            root.mkdir()
            self.make_tree(root)
            out = base / "uplifted"

            p = run_tool(root, "--catalog", CATALOG, "--apply-safe", out, "--fail-on-safe")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            data = json.loads(p.stdout)
            self.assertEqual(data["safe_apply"]["residual_safe_finding_count"], 0)

            # Source is immutable.
            source_pred = json.loads((root / "data/demo/predicate/is_here.json").read_text())
            self.assertIn("condition", source_pred)
            self.assertNotIn("type", source_pred)

            # Predicate migrated.
            pred = json.loads((out / "data/demo/predicate/is_here.json").read_text())
            self.assertEqual(pred["type"], "minecraft:entity_properties")
            self.assertNotIn("condition", pred)

            # Worldgen paths migrated.
            self.assertTrue((out / "data/demo/worldgen/feature/stone.json").exists())
            self.assertFalse((out / "data/demo/worldgen/configured_feature").exists())
            self.assertTrue((out / "data/demo/worldgen/carver/cave.json").exists())

            # Block-state fields migrated.
            feature = json.loads((out / "data/demo/worldgen/feature/stone.json").read_text())
            state = feature["config"]["target_state"]
            self.assertEqual(state["id"], "minecraft:stone")
            self.assertEqual(state["properties"], {"axis": "y"})
            self.assertNotIn("Name", state)
            self.assertNotIn("Properties", state)

            # Non-predicate nested condition untouched.
            loot = json.loads((out / "data/demo/loot_table/test.json").read_text())
            self.assertEqual(
                loot["pools"][0]["conditions"][0]["condition"],
                "minecraft:random_chance",
            )

    def test_apply_safe_handles_nested_predicate_and_carried_block_state(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = base / "source"
            root.mkdir()

            pred = root / "data/demo/predicate/nested.json"
            pred.parent.mkdir(parents=True)
            pred.write_text(json.dumps({
                "condition": "minecraft:all_of",
                "terms": [
                    {"condition": "minecraft:reference", "name": "demo:a"},
                    {
                        "condition": "minecraft:inverted",
                        "term": {
                            "condition": "minecraft:entity_properties",
                            "entity": "this",
                            "predicate": {
                                "demo:component": {
                                    "condition": "domain-data-must-stay"
                                }
                            }
                        }
                    }
                ]
            }), encoding="utf-8")

            fn = root / "data/demo/function/state.mcfunction"
            fn.parent.mkdir(parents=True)
            fn.write_text(
                'data merge entity @s {CustomName:"Keep",'
                'carriedBlockState:{Name:"minecraft:gold_block"},'
                'Other:{Name:"minecraft:stone"}}\\n',
                encoding="utf-8",
            )

            out = base / "uplifted"
            p = run_tool(root, "--catalog", CATALOG, "--apply-safe", out, "--fail-on-safe")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            data = json.loads(p.stdout)
            self.assertEqual(data["safe_apply"]["residual_safe_finding_count"], 0)

            upgraded = json.loads((out / "data/demo/predicate/nested.json").read_text())
            self.assertEqual(upgraded["type"], "minecraft:all_of")
            self.assertEqual(upgraded["terms"][0], "demo:a")
            self.assertEqual(upgraded["terms"][1]["type"], "minecraft:inverted")
            self.assertEqual(
                upgraded["terms"][1]["term"]["type"],
                "minecraft:entity_properties",
            )
            self.assertEqual(
                upgraded["terms"][1]["term"]["predicate"]["demo:component"]["condition"],
                "domain-data-must-stay",
            )

            text = (out / "data/demo/function/state.mcfunction").read_text()
            self.assertIn('carriedBlockState:{id:"minecraft:gold_block"}', text)
            self.assertIn('CustomName:"Keep"', text)
            self.assertIn('Other:{Name:"minecraft:stone"}', text)

            self.assertEqual(len(data["safe_apply"]["mcfunction_changes"]), 1)
            self.assertEqual(
                data["safe_apply"]["mcfunction_changes"][0]["fields"],
                ["carriedBlockState"],
            )

    def test_fail_on_safe_detects_unmigrated_tree(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_tree(root)
            p = run_tool(root, "--catalog", CATALOG, "--fail-on-safe")
            self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
