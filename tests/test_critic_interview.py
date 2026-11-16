"""Public-safe contract tests: all model outputs are synthetic test doubles."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from critic_media_probe import inspect
from critic_observation_gate import accept


class MediaProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.mp4"
        self.path.write_bytes(b"synthetic-test-bytes-not-an-actual-mp4")

    def tearDown(self):
        self.tmp.cleanup()

    @patch("critic_media_probe.subprocess.run")
    def test_video_source_receipt(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({
                "streams": [{"codec_type": "video", "codec_name": "h264", "width": 64, "height": 64}],
                "format": {"duration": "2.000000"},
            }), "",
        )
        r = inspect(self.path, "video")
        self.assertEqual(r["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(r["duration_ms"], 2000)
        self.assertFalse(r["minecraft_runtime_verified"])
        self.assertEqual(r["review_status"], "REVIEW_REQUIRED")
        with self.assertRaisesRegex(ValueError, "NO_AUDIO_TRACK"):
            inspect(self.path, "video", require_audio=True)

    def test_symlink_and_empty_refused(self):
        link = Path(self.tmp.name) / "alias"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            inspect(link, "video")
        self.path.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "EMPTY"):
            inspect(self.path, "video")

    @patch("critic_media_probe.subprocess.run")
    def test_audio_only_refuses_video(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({
                "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le", "sample_rate": "44100"}],
                "format": {"duration": "1.000000"},
            }), "",
        )
        self.assertEqual(inspect(self.path, "audio")["tracks"], ["audio"])
        with self.assertRaisesRegex(ValueError, "NO_VIDEO_TRACK"):
            inspect(self.path, "video")


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.media = {
            "schema": "supracraft-critic-media-probe/v1", "kind": "video",
            "sha256": "a" * 64, "review_status": "REVIEW_REQUIRED",
            "tracks": ["video"], "duration_ms": 2000,
            "minecraft_runtime_verified": False, "stock_client_verified": False,
        }
        self.response = {
            "schema": "supracraft-critic-observation/v1",
            "candidate": {"provider": "test-double", "model": "fixture-only", "family": "synthetic"},
            "input_sha256": "a" * 64,
            "disposition": "observe",
            "observations": [{
                "modality": "video", "time_ms": 1000, "severity": "minor",
                "claim": "The synthetic scene changes between frames",
                "evidence": "Timestamped synthetic fixture has a deliberate color change",
                "confidence": 0.8,
            }],
        }

    def test_valid_evidence_never_promotes(self):
        result = accept(self.media, self.response)
        self.assertEqual(result["status"], "EVIDENCE_ADMISSIBLE_REVIEW_REQUIRED")
        self.assertFalse(result["qualified_model"])
        self.assertFalse(result["official_gameplay_verified"])

    def test_hash_mismatch_refused(self):
        self.response["input_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "SOURCE_MISMATCH"):
            accept(self.media, self.response)

    def test_missing_audio_track_refused(self):
        self.response["observations"][0]["modality"] = "audio"
        with self.assertRaisesRegex(ValueError, "AUDIO_TRACK_ABSENT"):
            accept(self.media, self.response)

    def test_impossible_timestamp_refused(self):
        self.response["observations"][0]["time_ms"] = 2001
        with self.assertRaisesRegex(ValueError, "TIME_OUTSIDE_MEDIA"):
            accept(self.media, self.response)

    def test_unattributed_model_refused(self):
        del self.response["candidate"]["family"]
        with self.assertRaisesRegex(ValueError, "CANDIDATE_IDENTITY_REQUIRED"):
            accept(self.media, self.response)

    def test_bad_confidence_and_ungrounded_reason_refused(self):
        self.response["observations"][0]["confidence"] = 1.1
        with self.assertRaisesRegex(ValueError, "INVALID_CONFIDENCE"):
            accept(self.media, self.response)
        self.response["observations"][0]["confidence"] = 0.8
        self.response["observations"][0]["evidence"] = "trust me"
        with self.assertRaisesRegex(ValueError, "UNGROUNDED_CLAIM"):
            accept(self.media, self.response)

    def test_explicit_abstention(self):
        self.response["disposition"] = "abstain"
        self.response["observations"] = []
        self.response["uncertainty"] = "Insufficient frames for identification"
        self.assertEqual(accept(self.media, self.response)["disposition"], "abstain")
        self.response["uncertainty"] = "unknown"
        with self.assertRaisesRegex(ValueError, "ABSTENTION"):
            accept(self.media, self.response)

    def test_image_region_bounds(self):
        self.media["kind"] = "image"
        self.media["duration_ms"] = None
        item = self.response["observations"][0]
        item["modality"] = "image"
        del item["time_ms"]
        item["region"] = [0.1, 0.2, 0.8, 0.9]
        self.assertEqual(accept(self.media, self.response)["observation_count"], 1)
        item["region"] = [0.8, 0.2, 0.1, 0.9]
        with self.assertRaisesRegex(ValueError, "INVALID_IMAGE_REGION"):
            accept(self.media, self.response)

    def test_authentication_forgery_refused(self):
        self.media["stock_client_verified"] = True
        with self.assertRaisesRegex(ValueError, "AUTHORITY_CLAIM_UNTRUSTED"):
            accept(self.media, self.response)


if __name__ == "__main__":
    unittest.main()
