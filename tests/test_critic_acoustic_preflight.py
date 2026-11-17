"""Acoustic front-end fuzz/refusal gates, independent from VLM reasoning."""
from array import array
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from critic_acoustic_preflight import probe, SCHEMA


class AcousticProbeTests(unittest.TestCase):
    def setUp(self):
        self.meta = {
            "sha256": "1" * 64, "duration_ms": 1000,
            "tracks": ["audio"],
        }

    def _samples(self, values):
        buf = array("h", values)
        if sys.byteorder != "little":
            buf.byteswap()
        return bytes(buf)

    @patch("critic_acoustic_preflight.inspect")
    @patch("critic_acoustic_preflight.subprocess.run")
    def test_non_silent_tone_is_signal_not_game_audio(self, run, inspect):
        inspect.return_value = self.meta
        # Synthetic alternating waveform; no music/game audio.
        run.return_value = subprocess.CompletedProcess(
            [], 0, self._samples([5000, -5000] * 8000), b"",
        )
        r = probe("fixture.wav")
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["decoded_samples"], 16000)
        self.assertTrue(r["acoustic_signal_present"])
        self.assertEqual(r["silence_windows"], 0)
        self.assertFalse(r["minecraft_audio_verified"])
        self.assertFalse(r["source_audio_origin_authenticated"])
        self.assertEqual(r["source_sha256"], "1" * 64)

    @patch("critic_acoustic_preflight.inspect")
    @patch("critic_acoustic_preflight.subprocess.run")
    def test_present_but_silent_is_not_absent_track(self, run, inspect):
        inspect.return_value = self.meta
        run.return_value = subprocess.CompletedProcess(
            [], 0, self._samples([0] * 16000), b"",
        )
        r = probe("fixture.wav")
        self.assertFalse(r["acoustic_signal_present"])
        self.assertEqual(r["silence_windows"], 4)
        self.assertEqual(r["rms_dbfs"], -240.0)

    @patch("critic_acoustic_preflight.inspect")
    @patch("critic_acoustic_preflight.subprocess.run")
    def test_clipping_detected(self, run, inspect):
        inspect.return_value = self.meta
        run.return_value = subprocess.CompletedProcess(
            [], 0, self._samples([32767, -32768] * 8000), b"",
        )
        self.assertEqual(probe("fixture.wav")["clipping_sample_fraction"], 1.0)

    @patch("critic_acoustic_preflight.inspect")
    @patch("critic_acoustic_preflight.subprocess.run")
    def test_decode_failure_refused(self, run, inspect):
        inspect.return_value = self.meta
        run.side_effect = subprocess.CalledProcessError(1, ["ffmpeg"])
        with self.assertRaisesRegex(ValueError, "AUDIO_DECODE_FAILED"):
            probe("fixture.wav")

    @patch("critic_acoustic_preflight.inspect")
    @patch("critic_acoustic_preflight.subprocess.run")
    def test_empty_or_misaligned_decode_refused(self, run, inspect):
        inspect.return_value = self.meta
        run.return_value = subprocess.CompletedProcess([], 0, b"", b"")
        with self.assertRaisesRegex(ValueError, "AUDIO_DECODE_SIZE_INVALID"):
            probe("fixture.wav")
        run.return_value = subprocess.CompletedProcess([], 0, b"\x01", b"")
        with self.assertRaisesRegex(ValueError, "AUDIO_DECODE_SIZE_INVALID"):
            probe("fixture.wav")

    @patch("critic_acoustic_preflight.inspect")
    def test_unbounded_audio_refused_before_decode(self, inspect):
        inspect.return_value = dict(self.meta, duration_ms=30001)
        with self.assertRaisesRegex(ValueError, "AUDIO_DURATION_OUT_OF_BOUNDS"):
            probe("fixture.wav")


if __name__ == "__main__":
    unittest.main()
