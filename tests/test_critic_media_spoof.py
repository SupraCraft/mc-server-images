"""Media modality spoofing must fail before a generative critic can be considered."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from critic_media_probe import inspect


class MediaSpoofingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_mp4_cannot_masquerade_as_still_image(self):
        f = self.root / "image.png"
        f.write_bytes(b"\x00\x00\x00\x18ftypisomrest")
        with self.assertRaisesRegex(ValueError, "STILL_IMAGE_SIGNATURE_REQUIRED"):
            inspect(f, "image")

    def test_png_cannot_masquerade_as_video(self):
        f = self.root / "movie.mp4"
        f.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-test")
        with self.assertRaisesRegex(ValueError, "VIDEO_MUST_NOT_BE_STILL_IMAGE"):
            inspect(f, "video")

    @patch("critic_media_probe.subprocess.run")
    def test_still_requires_single_image_codec(self, run):
        f = self.root / "still.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-test")
        run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({
                "streams": [{"codec_type": "video", "codec_name": "h264"}],
                "format": {"duration": "0.1"},
            }), "",
        )
        with self.assertRaisesRegex(ValueError, "STILL_IMAGE_STREAM_INVALID"):
            inspect(f, "image")

    @patch("critic_media_probe.subprocess.run")
    def test_pinned_still_header_and_single_stream_admitted_for_review(self, run):
        f = self.root / "still.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-test")
        run.return_value = subprocess.CompletedProcess(
            [], 0, json.dumps({
                "streams": [{"codec_type": "video", "codec_name": "png"}],
                "format": {"duration": "N/A"},
            }), "",
        )
        receipt = inspect(f, "image")
        self.assertEqual(receipt["sha256"], hashlib.sha256(f.read_bytes()).hexdigest())
        self.assertEqual(receipt["review_status"], "REVIEW_REQUIRED")
        self.assertIsNone(receipt["duration_ms"])
        self.assertFalse(receipt["stock_client_verified"])


if __name__ == "__main__":
    unittest.main()
