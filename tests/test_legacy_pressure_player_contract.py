import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"tools"/"legacy_pressure_plate_player.js").read_text()


class LegacyPressurePlayerContractTests(unittest.TestCase):
    def test_all_feedback_event_classes_capture_observation_time(self):
        self.assertIn(
            "appendFeedbackEvent('message_events', {",
            SOURCE,
        )
        self.assertIn(
            "appendFeedbackEvent('protocol_chat_events', classifyProtocolChat(packet))",
            SOURCE,
        )
        self.assertIn(
            "appendFeedbackEvent('self_effect_events', {",
            SOURCE,
        )

        classifier=SOURCE[SOURCE.index("function classifyProtocolChat"):
                          SOURCE.index("function recordProtocolChat")]
        self.assertIn("observed_at_epoch_ms: Date.now()",classifier)

        message=SOURCE[SOURCE.index("function recordMessage"):
                       SOURCE.index("function classifyProtocolChat")]
        self.assertIn("observed_at_epoch_ms: Date.now()",message)

        effect=SOURCE[SOURCE.index("function recordSelfEffect"):
                      SOURCE.index("function writeReceipt")]
        self.assertIn("observed_at_epoch_ms: Date.now()",effect)


if __name__ == "__main__":
    unittest.main()
