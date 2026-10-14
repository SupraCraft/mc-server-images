import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("dp",ROOT/"tools"/"analyze_datapack_causal_semantics.py")
dp=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(dp)

class DatapackCausalTests(unittest.TestCase):
    def build_world(self, root):
        pack=root/"datapacks"/"fixture"
        (pack/"data"/"demo"/"function").mkdir(parents=True)
        (pack/"data"/"demo"/"predicate").mkdir(parents=True)
        (pack/"data"/"demo"/"advancement").mkdir(parents=True)
        (pack/"pack.mcmeta").write_text(json.dumps({
            "pack":{"pack_format":88,"description":"fixture"}
        }))
        (pack/"data"/"demo"/"function"/"start.mcfunction").write_text(
            "scoreboard objectives add quest dummy\n"
            "scoreboard players set @s quest 1\n"
            "data modify storage demo:state quest set value 1\n"
            "execute if predicate demo:has_key run function demo:open_gate\n"
            "schedule function demo:tick 20t replace\n"
            "playsound minecraft:block.note_block.pling master @s\n"
        )
        (pack/"data"/"demo"/"function"/"open_gate.mcfunction").write_text(
            "setblock 10 64 10 minecraft:air\n"
            "tellraw @s {\"text\":\"Gate opened\"}\n"
        )
        (pack/"data"/"demo"/"function"/"tick.mcfunction").write_text(
            "scoreboard players add @s quest 1\n"
        )
        (pack/"data"/"demo"/"predicate"/"has_key.json").write_text(json.dumps({
            "condition":"minecraft:entity_properties",
            "entity":"this",
            "predicate":{}
        }))
        (pack/"data"/"demo"/"advancement"/"begin.json").write_text(json.dumps({
            "criteria":{"tick":{"trigger":"minecraft:tick"}},
            "rewards":{"function":"demo:start"}
        }))

    def test_fixture_recovers_state_orchestration_and_feedback(self):
        with tempfile.TemporaryDirectory() as td:
            world=pathlib.Path(td)
            self.build_world(world)
            d=dp.analyze(world)

        self.assertEqual(3,d["function_count"])
        self.assertGreaterEqual(d["edge_count"],10)
        self.assertGreaterEqual(d["role_counts"].get("semantic_state",0),3)
        self.assertGreaterEqual(d["role_counts"].get("presentation_feedback",0),2)
        self.assertEqual(1,d["advancement_reward_function_edge_count"])

        edge_types=[e["edge_type"] for e in d["edges"]]
        self.assertIn("function_call",edge_types)
        self.assertIn("function_schedule",edge_types)
        self.assertIn("scoreboard_write",edge_types)
        self.assertIn("storage_write",edge_types)
        self.assertIn("predicate_read",edge_types)
        self.assertIn("advancement_reward_function",edge_types)

    def test_missing_function_reference_is_explicit_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            world=pathlib.Path(td)
            self.build_world(world)
            p=world/"datapacks"/"fixture"/"data"/"demo"/"function"/"start.mcfunction"
            p.write_text(p.read_text()+"function demo:missing\n")
            d=dp.analyze(world)
        self.assertGreaterEqual(d["unresolved_reference_counts"].get("function_ref",0),1)

if __name__=="__main__":
    unittest.main()
