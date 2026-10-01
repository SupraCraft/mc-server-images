import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "discover_minecraft_observability.py"
SPEC = importlib.util.spec_from_file_location("discover_minecraft_observability", MODULE_PATH)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class FrontierDiscoveryTests(unittest.TestCase):
    def test_resolve_frontier_uses_manifest_latest_exactly(self):
        manifest = {
            "latest": {"release": "26.3", "snapshot": "26.4 Snapshot 2"},
            "versions": [
                {"id": "26.3", "url": "https://example/release.json", "releaseTime": "r"},
                {"id": "26.4 Snapshot 2", "url": "https://example/snapshot.json", "releaseTime": "s"},
            ],
        }
        details = {
            "https://example/release.json": {
                "javaVersion": {"majorVersion": 25},
                "releaseTime": "release-time",
                "downloads": {
                    "server": {
                        "url": "https://example/release.jar",
                        "sha1": "1" * 40,
                        "size": 123,
                    }
                },
            },
            "https://example/snapshot.json": {
                "javaVersion": {"majorVersion": 25},
                "releaseTime": "snapshot-time",
                "downloads": {
                    "server": {
                        "url": "https://example/snapshot.jar",
                        "sha1": "2" * 40,
                        "size": 456,
                    }
                },
            },
        }
        rows = mod.resolve_frontier(manifest, detail_loader=details.__getitem__)
        self.assertEqual(
            [(row["channel"], row["minecraft_version"]) for row in rows],
            [("release", "26.3"), ("snapshot", "26.4 Snapshot 2")],
        )
        self.assertEqual([row["java_major"] for row in rows], [25, 25])

    def test_symbol_mode_requires_multiple_exact_named_witnesses(self):
        classes = {
            "net/minecraft/server/MinecraftServer.class",
            "net/minecraft/commands/Commands.class",
        }
        mode, witnesses = mod.detect_symbol_mode(classes)
        self.assertEqual(mode, "unobfuscated")
        self.assertEqual(len(witnesses), 2)

    def test_jfr_catalog_is_discovered_not_hard_coded(self):
        metadata = """
        @Name("minecraft.ServerTickTime")
        class ServerTickTime {}
        @Name("minecraft.PacketSent")
        class PacketSent {}
        @Name("jdk.CPULoad")
        class CPULoad {}
        minecraft.FutureEvent
        """
        events = mod.parse_minecraft_jfr_event_names(metadata)
        self.assertEqual(
            events,
            [
                "minecraft.FutureEvent",
                "minecraft.PacketSent",
                "minecraft.ServerTickTime",
            ],
        )

    def test_semantic_coverage_is_conservative(self):
        coverage = {
            row["event_family"]: row
            for row in mod.semantic_coverage(
                ["minecraft.ServerTickTime", "minecraft.PacketSent"]
            )
        }
        self.assertEqual(coverage["tick_boundary"]["status"], "native_candidate")
        self.assertEqual(coverage["packet_send"]["status"], "native_candidate")
        self.assertEqual(coverage["command_trigger"]["status"], "missing")
        self.assertTrue(coverage["command_trigger"]["direct_hook_required"])

    def test_discovery_schema_does_not_masquerade_as_adapter_manifest(self):
        schema = json.loads(
            (
                ROOT
                / "bench"
                / "worldgen"
                / "observability"
                / "supracraft-causal-version-discovery-v1.schema.json"
            ).read_text()
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "supracraft-causal-version-discovery/1",
        )
        self.assertEqual(
            schema["properties"]["qualification_status"]["const"],
            "discovery_only_not_adapter_qualified",
        )
        provenance=schema["properties"]["artifact_provenance"]
        self.assertIn("server_sha256_observed",provenance["required"])
        self.assertEqual(
            provenance["properties"]["server_sha256_observed"]["pattern"],
            "^[0-9a-f]{64}$",
        )


if __name__ == "__main__":
    unittest.main()
