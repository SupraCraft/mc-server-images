"""Source-only FFmpeg installer budget/stop guard, no external dependencies."""
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "multimodal-critic-interview.yml"


class AptTimeboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = PATH.read_text(encoding="utf-8")

    def test_two_independent_media_lanes_are_bounded(self):
        self.assertEqual(self.workflow.count("timeout -k 5s 70s sudo apt-get"), 2)
        self.assertEqual(self.workflow.count("timeout -k 5s 85s sudo apt-get"), 2)
        self.assertEqual(self.workflow.count("if ! command -v ffmpeg"), 2)

    def test_no_unbounded_apt_remains(self):
        self.assertNotIn("          sudo apt-get update -qq", self.workflow)
        self.assertNotIn("          sudo apt-get install -y -qq --no-install-recommends", self.workflow)
        self.assertEqual(self.workflow.count("Acquire::Retries=0"), 4)
        self.assertEqual(self.workflow.count("Acquire::http::Timeout=15"), 4)

    def test_no_api_model_or_security_fallback(self):
        self.assertIn("github.event.repository.private == false", self.workflow)
        self.assertIn("contents: read", self.workflow)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.workflow)
        self.assertNotIn("curl | sh", self.workflow)

    def test_preserve_not_yet_qualified_canonical_probe(self):
        self.assertIn("tools/critic_media_probe.py --kind image", self.workflow)
        self.assertIn("tools/critic_media_probe.py --kind video", self.workflow)
        self.assertIn("tools/critic_acoustic_preflight.py --media", self.workflow)
        self.assertIn("tests -p 'test_critic_*.py'", self.workflow)


if __name__ == "__main__":
    unittest.main()
