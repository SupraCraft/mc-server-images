import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=ROOT/"bench"/"worldgen"/"observability"/"supracraft-causal-event-v1.schema.json"
T263=ROOT/"tools"/"causal-microscope"/"modern-26.3-agent"/"src"/"main"/"java"/"org"/"supracraft"/"microscope"/"Modern263Transformer.java"
T264=ROOT/"tools"/"causal-microscope"/"modern-26.4-snapshot-2-agent"/"src"/"main"/"java"/"org"/"supracraft"/"microscope"/"Modern264Snapshot2Transformer.java"
R263=T263.with_name("TraceRuntime.java")
R264=T264.with_name("TraceRuntime.java")


class PistonMicroscopeContractTests(unittest.TestCase):
    def test_exact_piston_hashes_and_sensor_pack_are_guarded(self):
        for path in (T263,T264):
            src=path.read_text()
            self.assertIn(
                "47b87b5736027ca99add513835ddb594417ab6b8943c2fa746870af101b105d9",
                src,
            )
            self.assertIn(
                "9280026fba3b95dbbf1347d7608b88f3663da017daf8312b4a1a07742dc04121",
                src,
            )
            self.assertIn('"core+piston".equals(sensors)',src)
            for hook in (
                "piston_check_if_extend","piston_get_neighbor_signal",
                "piston_move_blocks","piston_trigger_event",
                "piston_structure_resolve",
            ):
                self.assertIn(hook,src)

    def test_runtime_has_positionless_integer_event_for_resolver(self):
        for path in (R263,R264):
            src=path.read_text()
            self.assertIn("public static void eventInt(int value,String eventType)",src)
            self.assertIn('emit(eventType,"{\\\"value\\\":"+value+"}")',src)

    def test_event_schema_contains_only_bounded_piston_events(self):
        schema=json.loads(SCHEMA.read_text())
        events=set(schema["properties"]["event_type"]["enum"])
        expected={
            "piston_check_start","piston_check_end",
            "piston_neighbor_signal_query","piston_neighbor_signal_result",
            "piston_structure_resolve_result",
            "piston_move_blocks_query","piston_move_blocks_result",
            "piston_trigger_event_query","piston_trigger_event_result",
        }
        self.assertTrue(expected<=events)

    def test_moving_entity_tick_is_not_runtime_hooked_yet(self):
        for path in (T263,T264):
            src=path.read_text()
            self.assertNotIn('"piston_moving_tick"',src)
            self.assertNotIn('"piston_final_tick"',src)

    def test_piston_hook_count_is_minimal(self):
        for path in (T263,T264):
            self.assertIn("private static final int PISTON_HOOK_COUNT=5;",path.read_text())


if __name__=="__main__":
    unittest.main()
