import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "external_corpus",
    ROOT / "tools" / "analyze_external_datapack_corpus.py",
)
external_corpus = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(external_corpus)


class ExternalCorpusTests(unittest.TestCase):
    def build_pack(self, root: pathlib.Path):
        (root / "data" / "demo" / "function").mkdir(parents=True)
        (root / "data" / "demo" / "advancement").mkdir(parents=True)
        (root / "data_26_2" / "data" / "demo" / "predicate").mkdir(parents=True)
        (root / "data_26_3" / "data" / "demo" / "predicate").mkdir(parents=True)
        (root / "legacy" / "data" / "demo" / "recipe").mkdir(parents=True)

        (root / "pack.mcmeta").write_text(
            json.dumps(
                {
                    "pack": {
                        "min_format": [101, 2],
                        "max_format": [121, 0],
                        "description": "fixture",
                    },
                    "overlays": {
                        "entries": [
                            {
                                "directory": "data_26_2",
                                "min_format": [101, 2],
                                "max_format": [107, 1],
                            },
                            {
                                "directory": "data_26_3",
                                "min_format": [108, 0],
                                "max_format": [121, 0],
                            },
                            {
                                "directory": "legacy",
                                "min_format": [101, 2],
                                "max_format": [121, 0],
                            },
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )

        (root / "data" / "demo" / "function" / "start.mcfunction").write_text(
            "scoreboard objectives add quest dummy\n"
            "scoreboard players set @s quest 1\n"
            "schedule function demo:tick 20t replace\n"
            "tellraw @s {\"text\":\"SECRET_STORY_TEXT\"}\n",
            encoding="utf-8",
        )
        (root / "data" / "demo" / "function" / "tick.mcfunction").write_text(
            "scoreboard players add @s quest 1\n",
            encoding="utf-8",
        )
        (root / "data" / "demo" / "advancement" / "begin.json").write_text(
            json.dumps(
                {
                    "criteria": {"tick": {"trigger": "minecraft:tick"}},
                    "rewards": {"function": "demo:start"},
                }
            ),
            encoding="utf-8",
        )
        (root / "data_26_2" / "data" / "demo" / "predicate" / "inside.json").write_text(
            json.dumps(
                {
                    "condition": "minecraft:entity_properties",
                    "entity": "this",
                    "predicate": {},
                }
            ),
            encoding="utf-8",
        )
        (root / "data_26_3" / "data" / "demo" / "predicate" / "inside.json").write_text(
            json.dumps(
                {
                    "type": "minecraft:entity_properties",
                    "entity": "this",
                    "predicate": {},
                }
            ),
            encoding="utf-8",
        )
        (root / "legacy" / "data" / "demo" / "recipe" / "token.json").write_text(
            json.dumps(
                {
                    "type": "minecraft:crafting_shapeless",
                    "ingredients": ["minecraft:stone"],
                    "result": {"id": "minecraft:cobblestone", "count": 1},
                }
            ),
            encoding="utf-8",
        )

    def args(self, root, fmt, version):
        class A:
            pass

        a = A()
        a.datapack_root = root
        a.target_pack_format = fmt
        a.source_id = f"fixture-{version}"
        a.minecraft_version = version
        a.upstream_repository = "fixture/repo"
        a.upstream_commit = "deadbeef"
        a.license_label = "fixture"
        return a

    def test_overlay_selection_recovers_26_2_and_26_3_predicate_shapes(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.build_pack(root)

            old = external_corpus.analyze(self.args(root, "107.1", "26.2"))
            new = external_corpus.analyze(self.args(root, "121.0", "26.3"))

        self.assertEqual(
            ["data_26_2", "legacy"],
            [x["directory"] for x in old["overlay_materialization"]["selected_overlays"]],
        )
        self.assertEqual(
            ["data_26_3", "legacy"],
            [x["directory"] for x in new["overlay_materialization"]["selected_overlays"]],
        )
        self.assertEqual(
            {"condition": 1},
            old["resource_summary"]["predicate_top_level_schema_counts"],
        )
        self.assertEqual(
            {"type": 1},
            new["resource_summary"]["predicate_top_level_schema_counts"],
        )
        self.assertNotEqual(old["effective_content_sha256"], new["effective_content_sha256"])

    def test_receipt_is_derived_only_and_preserves_story_signals(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.build_pack(root)
            receipt = external_corpus.analyze(self.args(root, "121.0", "26.3"))

        encoded = json.dumps(receipt)
        self.assertFalse(receipt["raw_content_retained"])
        self.assertNotIn("SECRET_STORY_TEXT", encoded)
        self.assertEqual(2, receipt["causal_summary"]["function_count"])
        self.assertGreaterEqual(
            receipt["story_feature_signals"]["state_and_progression"][
                "semantic_state_command_count"
            ],
            2,
        )
        self.assertEqual(
            1,
            receipt["story_feature_signals"]["inventory_and_transformation"][
                "recipe_resource_count"
            ],
        )
        self.assertEqual(
            1,
            receipt["story_feature_signals"]["timing_and_orchestration"][
                "schedule_verb_count"
            ],
        )


if __name__ == "__main__":
    unittest.main()
