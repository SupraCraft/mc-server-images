import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "external_world_datapacks",
    ROOT/"tools"/"analyze_external_world_datapacks.py",
)
mod=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class ExternalWorldDatapackTests(unittest.TestCase):
    def fixture(self,root:pathlib.Path):
        pack=root/"datapacks"/"demo"
        fn=pack/"data"/"demo"/"function"
        adv=pack/"data"/"demo"/"advancement"
        fn.mkdir(parents=True)
        adv.mkdir(parents=True)
        (pack/"pack.mcmeta").write_text('{"pack":{"pack_format":121,"description":"fixture"}}')
        (fn/"tick.mcfunction").write_text(
            "scoreboard objectives add race dummy\n"
            "scoreboard players add #clock race 1\n"
            "execute if score #clock race matches 20.. run function demo:lap\n"
            "title @a actionbar {\"text\":\"SECRET_UI\"}\n"
        )
        (fn/"lap.mcfunction").write_text(
            "tag @a add racer\n"
            "effect give @a speed 2 1 true\n"
        )
        (adv/"start.json").write_text(json.dumps({
            "criteria":{"tick":{"trigger":"minecraft:tick"}},
            "rewards":{"function":"demo:tick"}
        }))

    def args(self,root):
        class A: pass
        a=A()
        a.world_root=root
        a.source_id="fixture"
        a.minecraft_version="26.3"
        a.upstream_repository="fixture/repo"
        a.upstream_commit="deadbeef"
        a.license_label="fixture"
        return a

    def test_summary_preserves_structure_not_payload(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            self.fixture(root)
            r=mod.analyze(self.args(root))
        encoded=json.dumps(r)
        self.assertFalse(r["raw_content_retained"])
        self.assertNotIn("SECRET_UI",encoded)
        self.assertEqual(2,r["causal_summary"]["function_count"])
        self.assertEqual({},r["causal_summary"]["unresolved_reference_counts"])
        self.assertEqual(1,r["story_feature_signals"]["actors_and_multiplayer"]["tag_commands"])
        self.assertEqual(1,r["story_feature_signals"]["items_and_rewards"]["effect_commands"])
        self.assertEqual(1,r["story_feature_signals"]["observation_and_ui"]["title_commands"])
        self.assertIn("demo",r["pack_inventory"])

    def test_pack_inventory_is_aggregate_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            self.fixture(root)
            r=mod.analyze(self.args(root))
        p=r["pack_inventory"]["demo"]
        self.assertEqual("directory",p["container"])
        self.assertGreaterEqual(p["file_count"],4)
        self.assertIn("function",p["resource_kind_counts"])
        self.assertIn("advancement",p["resource_kind_counts"])


if __name__=="__main__":
    unittest.main()
