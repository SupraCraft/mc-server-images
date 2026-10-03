import importlib.util
import json
import pathlib
import tempfile
import unittest

import nbtlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "external_world",
    ROOT / "tools" / "analyze_external_world_metadata.py",
)
external_world = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(external_world)


class ExternalWorldMetadataTests(unittest.TestCase):
    def write_level(self, root: pathlib.Path):
        level = nbtlib.File(
            {
                "Data": nbtlib.Compound(
                    {
                        "DataVersion": nbtlib.Int(9999),
                        "GameType": nbtlib.Int(0),
                        "hardcore": nbtlib.Byte(0),
                        "allowCommands": nbtlib.Byte(1),
                        "initialized": nbtlib.Byte(1),
                        "WasModded": nbtlib.Byte(0),
                        "Version": nbtlib.Compound(
                            {
                                "Name": nbtlib.String("26.3"),
                                "Id": nbtlib.Int(9999),
                                "Snapshot": nbtlib.Byte(0),
                            }
                        ),
                        "DataPacks": nbtlib.Compound(
                            {
                                "Enabled": nbtlib.List[nbtlib.String](
                                    [nbtlib.String("vanilla"), nbtlib.String("file/demo")]
                                ),
                                "Disabled": nbtlib.List[nbtlib.String]([]),
                            }
                        ),
                        "GameRules": nbtlib.Compound(
                            {
                                "doDaylightCycle": nbtlib.String("true"),
                                "keepInventory": nbtlib.String("false"),
                            }
                        ),
                    }
                )
            }
        )
        level.save(root / "level.dat")

    def write_scoreboard(self, root: pathlib.Path):
        data = root / "data"
        data.mkdir()
        scoreboard = nbtlib.File(
            {
                "data": nbtlib.Compound(
                    {
                        "Objectives": nbtlib.List[nbtlib.Compound](
                            [
                                nbtlib.Compound(
                                    {
                                        "Name": nbtlib.String("SECRET_OBJECTIVE_NAME"),
                                        "CriteriaName": nbtlib.String("dummy"),
                                    }
                                )
                            ]
                        ),
                        "PlayerScores": nbtlib.List[nbtlib.Compound](
                            [
                                nbtlib.Compound(
                                    {
                                        "Name": nbtlib.String("SECRET_PLAYER"),
                                        "Objective": nbtlib.String("SECRET_OBJECTIVE_NAME"),
                                        "Score": nbtlib.Int(1),
                                    }
                                )
                            ]
                        ),
                        "Teams": nbtlib.List[nbtlib.Compound]([]),
                    }
                )
            }
        )
        scoreboard.save(data / "scoreboard.dat")
        game_rules = nbtlib.File(
            {
                "data": nbtlib.Compound(
                    {
                        "SECRET_RULE": nbtlib.String("SECRET_VALUE"),
                    }
                )
            }
        )
        game_rules.save(data / "game_rules.dat")

    def args(self, root):
        class A:
            pass

        a = A()
        a.world_root = root
        a.source_id = "fixture"
        a.minecraft_version = "26.3"
        a.upstream_repository = "fixture/repo"
        a.upstream_commit = "deadbeef"
        a.license_label = "fixture"
        return a

    def test_metadata_counts_without_identity_payloads(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.write_level(root)
            self.write_scoreboard(root)
            (root / "datapacks").mkdir()
            (root / "datapacks" / "demo").mkdir()
            receipt = external_world.analyze(self.args(root))

        encoded = json.dumps(receipt)
        self.assertEqual(9999, receipt["level"]["data_version"])
        self.assertEqual("26.3", receipt["level"]["version"]["name"])
        self.assertTrue(receipt["provenance_checks"]["claimed_version_matches_level_name"])
        self.assertTrue(receipt["provenance_checks"]["exact_version_world_authority"])
        self.assertEqual(
            "EXACT_VERSION_LEVEL_METADATA_MATCH",
            receipt["provenance_checks"]["classification"],
        )
        self.assertEqual(2, receipt["level"]["enabled_datapack_count"])
        self.assertEqual(1, receipt["scoreboard"]["objective_count"])
        self.assertEqual(1, receipt["scoreboard"]["score_record_count"])
        self.assertFalse(receipt["raw_player_identity_retained"])
        self.assertFalse(receipt["raw_nbt_payload_retained"])
        self.assertNotIn("SECRET_PLAYER", encoded)
        self.assertNotIn("SECRET_OBJECTIVE_NAME", encoded)
        self.assertNotIn("SECRET_VALUE", encoded)

    def test_version_mismatch_fails_exact_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.write_level(root)
            self.write_scoreboard(root)
            args = self.args(root)
            args.minecraft_version = "26.2"
            receipt = external_world.analyze(args)

        self.assertFalse(receipt["provenance_checks"]["claimed_version_matches_level_name"])
        self.assertFalse(receipt["provenance_checks"]["exact_version_world_authority"])
        self.assertEqual(
            "STALE_OR_TEMPLATE_LEVEL_METADATA",
            receipt["provenance_checks"]["classification"],
        )

    def test_namespaced_modern_data_layout_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.write_level(root)
            ns = root / "data" / "minecraft"
            ns.mkdir(parents=True)
            scoreboard = nbtlib.File(
                {
                    "data": nbtlib.Compound(
                        {
                            "Objectives": nbtlib.List[nbtlib.Compound]([]),
                            "PlayerScores": nbtlib.List[nbtlib.Compound]([]),
                            "Teams": nbtlib.List[nbtlib.Compound]([]),
                        }
                    )
                }
            )
            scoreboard.save(ns / "scoreboard.dat")
            game_rules = nbtlib.File({"data": nbtlib.Compound({"foo": nbtlib.String("bar")})})
            game_rules.save(ns / "game_rules.dat")
            receipt = external_world.analyze(self.args(root))

        self.assertTrue(receipt["scoreboard"]["present"])
        self.assertEqual(1, receipt["world_state_data"]["groups"]["scoreboard"])
        self.assertEqual(1, receipt["world_state_data"]["groups"]["game_rules"])
        self.assertIn("minecraft/scoreboard.dat", receipt["world_state_data"]["files"])
        self.assertIn("minecraft/game_rules.dat", receipt["world_state_data"]["files"])

    def test_data_files_are_shape_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            self.write_level(root)
            self.write_scoreboard(root)
            receipt = external_world.analyze(self.args(root))

        game_rules = receipt["world_state_data"]["files"]["game_rules.dat"]
        self.assertEqual("ok", game_rules["parse"])
        self.assertIn("SECRET_RULE", game_rules["data_keys"])
        self.assertNotIn("SECRET_VALUE", json.dumps(game_rules))


if __name__ == "__main__":
    unittest.main()
