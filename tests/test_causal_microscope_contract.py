import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
OBS=ROOT/"bench"/"worldgen"/"observability"


class CausalMicroscopeContractTests(unittest.TestCase):
    def test_event_schema_excludes_raw_authored_text(self):
        schema=json.loads(
            (OBS/"supracraft-causal-event-v1.schema.json").read_text()
        )
        data=schema["properties"]["data"]["properties"]
        self.assertNotIn("message",data)
        self.assertNotIn("command",data)
        self.assertNotIn("raw_text",data)
        self.assertIn("command_sha256",data)
        self.assertIn("payload_sha256",data)

    def test_legacy_manifest_is_exact_version_and_fail_closed(self):
        manifest=json.loads(
            (OBS/"legacy-1.8.8-mcp918-capability-manifest.json").read_text()
        )
        self.assertEqual(
            "supracraft-causal-capability-manifest/1",manifest["schema"]
        )
        self.assertEqual("1.8.8",manifest["minecraft_version"])
        self.assertEqual(8,manifest["java_major"])
        self.assertEqual("obfuscated",manifest["symbol_mode"])
        self.assertIs(manifest["fail_closed"],True)
        self.assertEqual(
            "47c636a70ff7fc60c52ac3ac4bca426e8b55743a",
            manifest["mapping_provenance"]["commit"],
        )
        self.assertEqual(
            "f04cb796b25a21ed76d93c80bd7086864feeb50f",
            manifest["mapping_provenance"]["mapping_blob_sha"],
        )

    def test_legacy_bindings_are_unique_and_narrow(self):
        manifest=json.loads(
            (OBS/"legacy-1.8.8-mcp918-capability-manifest.json").read_text()
        )
        bindings=manifest["bindings"]
        keys=[
            (x["runtime_class"],x["runtime_method"],x["runtime_descriptor"])
            for x in bindings
        ]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(x["expected_bind_count"]==1 for x in bindings))
        self.assertIn(
            ("adc","a","(Ladm;)V"),
            set(keys),
        )
        self.assertIn(
            ("lm","a","(Lff;)V"),
            set(keys),
        )

    def test_trace_event_types_cover_execution_and_delivery_boundaries(self):
        schema=json.loads(
            (OBS/"supracraft-causal-event-v1.schema.json").read_text()
        )
        events=set(schema["properties"]["event_type"]["enum"])
        for required in (
            "command_trigger_start","command_trigger_end",
            "packet_send","redstone_power_query","redstone_power_result",
            "scheduled_tick_enqueue","neighbor_notify",
        ):
            self.assertIn(required,events)


if __name__=="__main__":
    unittest.main()
