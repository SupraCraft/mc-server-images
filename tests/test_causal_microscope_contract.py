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
        self.assertIn("mapping_provenance",manifest)
        self.assertNotIn("artifact_provenance",manifest)
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
        self.assertIn(("adc","a","(Ladm;)V"),set(keys))
        self.assertIn(("lm","a","(Lff;)V"),set(keys))

    def test_modern_manifest_uses_exact_artifact_provenance(self):
        manifest=json.loads(
            (OBS/"modern-26.3-java25-capability-manifest.json").read_text()
        )
        self.assertEqual("26.3",manifest["minecraft_version"])
        self.assertEqual(25,manifest["java_major"])
        self.assertEqual("unobfuscated",manifest["symbol_mode"])
        self.assertIs(manifest["fail_closed"],True)
        self.assertNotIn("mapping_provenance",manifest)
        provenance=manifest["artifact_provenance"]
        self.assertEqual("mojang",provenance["provider"])
        self.assertEqual(
            "33680f5f2ac32864d6d7cf5e56a705fdb3e05f4c",
            provenance["server_sha1"],
        )
        self.assertEqual(64,len(provenance["server_sha256"]))
        self.assertEqual(64,len(provenance["symbol_inventory_sha256"]))
        self.assertEqual(64,len(provenance["hook_structure_sha256"]))

    def test_modern_bindings_match_first_server_canary_only(self):
        manifest=json.loads(
            (OBS/"modern-26.3-java25-capability-manifest.json").read_text()
        )
        bindings=manifest["bindings"]
        self.assertEqual(7,len(bindings))
        keys={
            (x["runtime_class"],x["runtime_method"],x["runtime_descriptor"])
            for x in bindings
        }
        self.assertEqual(len(bindings),len(keys))
        self.assertTrue(all(x["expected_bind_count"]==1 for x in bindings))
        self.assertTrue(all(len(x["class_sha256"])==64 for x in bindings))
        self.assertIn(
            (
                "net/minecraft/server/MinecraftServer",
                "tickServer",
                "(Ljava/util/function/BooleanSupplier;)V",
            ),
            keys,
        )
        self.assertIn(
            (
                "net/minecraft/world/level/block/CommandBlock",
                "execute",
                "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/BaseCommandBlock;Z)V",
            ),
            keys,
        )
        self.assertFalse(any("Packet" in x["runtime_class"] for x in bindings))
        self.assertFalse(any("RedstoneWire" in x["runtime_class"] for x in bindings))

    def test_capability_schema_allows_mapping_or_artifact_provenance(self):
        schema=json.loads(
            (OBS/"supracraft-causal-capability-manifest-v1.schema.json").read_text()
        )
        self.assertEqual(2,len(schema["oneOf"]))
        props=schema["properties"]
        self.assertIn("mapping_provenance",props)
        self.assertIn("artifact_provenance",props)

    def test_trace_event_types_cover_execution_and_delivery_boundaries(self):
        schema=json.loads(
            (OBS/"supracraft-causal-event-v1.schema.json").read_text()
        )
        events=set(schema["properties"]["event_type"]["enum"])
        for required in (
            "command_trigger_start","command_trigger_end","command_dispatch",
            "packet_send","redstone_power_query","redstone_power_result",
            "scheduled_tick_enqueue","neighbor_notify",
        ):
            self.assertIn(required,events)

    def test_modern_frontier_profiles_are_exact_and_fail_closed(self):
        release=json.loads(
            (OBS/"modern-26.3-java25-capability-manifest.json").read_text()
        )
        snapshot=json.loads(
            (OBS/"modern-26.4-snapshot-2-java25-capability-manifest.json").read_text()
        )
        self.assertEqual("26.3",release["minecraft_version"])
        self.assertEqual("26.4-snapshot-2",snapshot["minecraft_version"])
        self.assertEqual(25,release["java_major"])
        self.assertEqual(25,snapshot["java_major"])
        self.assertIs(release["fail_closed"],True)
        self.assertIs(snapshot["fail_closed"],True)
        rb={x["id"]:x for x in release["bindings"]}
        sb={x["id"]:x for x in snapshot["bindings"]}
        self.assertEqual(set(rb),set(sb))
        self.assertNotEqual(
            rb["server_tick"]["class_sha256"],
            sb["server_tick"]["class_sha256"],
        )
        self.assertNotEqual(
            rb["block_state_write"]["class_sha256"],
            sb["block_state_write"]["class_sha256"],
        )
        self.assertEqual(
            rb["command_block_execute"]["class_sha256"],
            sb["command_block_execute"]["class_sha256"],
        )
        self.assertEqual(
            rb["command_dispatch"]["class_sha256"],
            sb["command_dispatch"]["class_sha256"],
        )


if __name__=="__main__":
    unittest.main()
