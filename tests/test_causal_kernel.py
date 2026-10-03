import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
VALIDATOR=ROOT/"tools"/"validate_causal_kernel.py"
EXAMPLE=ROOT/"bench"/"worldgen"/"causal"/"kernel"/"examples"/"synthetic-multidomain-v1.json"
SCHEMA=ROOT/"bench"/"worldgen"/"causal"/"kernel"/"causal-kernel-v1.schema.json"

spec=importlib.util.spec_from_file_location("validate_causal_kernel",VALIDATOR)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CausalKernelV1Tests(unittest.TestCase):
    def fixture(self):
        return json.loads(EXAMPLE.read_text())

    def test_schema_and_example_are_json(self):
        schema=json.loads(SCHEMA.read_text())
        doc=self.fixture()
        self.assertEqual(schema["$id"],"urn:supracraft:schema:causal-kernel:1")
        self.assertEqual(doc["schema"],"supracraft-causal-kernel/1")

    def test_multidomain_fixture_validates(self):
        doc=mod.validate(self.fixture())
        domains={d for e in doc["entities"] for d in e["domains"]}
        self.assertEqual(domains,{"electrical","mechanical","programmable","inventory"})
        self.assertNotIn("presentation",domains)
        self.assertTrue(any(e["edge_kind"]=="transducer" for e in doc["edges"]))

    def test_unknown_is_preserved_without_invention(self):
        doc=mod.validate(self.fixture())
        unknown=[e for e in doc["edges"] if e["knowledge_state"]=="unknown"]
        self.assertEqual([e["edge_id"] for e in unknown],["edge-lamp-observer-unknown"])
        self.assertIsNone(unknown[0]["event_id"])

    def test_same_tick_micro_order_is_representable(self):
        doc=mod.validate(self.fixture())
        events={e["event_id"]:e for e in doc["events"]}
        self.assertEqual(events["evt-power-on"]["event_time"],{"game_tick":10,"microstep_or_order":0})
        self.assertEqual(events["evt-piston-move"]["event_time"],{"game_tick":10,"microstep_or_order":1})

    def test_dangling_port_fails_closed(self):
        doc=copy.deepcopy(self.fixture())
        doc["edges"][0]["target"]["port_id"]="not-a-port"
        with self.assertRaisesRegex(ValueError,"dangling target port"):
            mod.validate(doc)

    def test_micro_order_without_tick_fails_closed(self):
        doc=copy.deepcopy(self.fixture())
        doc["events"][0]["event_time"]={"game_tick":None,"microstep_or_order":0}
        with self.assertRaisesRegex(ValueError,"cannot order an unknown tick"):
            mod.validate(doc)

    def test_presentation_is_not_a_peer_domain(self):
        doc=copy.deepcopy(self.fixture())
        doc["entities"][0]["domains"].append("presentation")
        with self.assertRaisesRegex(ValueError,"unsupported domain"):
            mod.validate(doc)

    def test_non_java_authority_fails_closed(self):
        doc=copy.deepcopy(self.fixture())
        doc["edition"]="bedrock"
        with self.assertRaisesRegex(ValueError,"Minecraft Java only"):
            mod.validate(doc)


if __name__=="__main__":
    unittest.main()
