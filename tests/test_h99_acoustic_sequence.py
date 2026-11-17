"""Independent offline first-pass 440 Hz/white-noise event oracle falsifiers."""
from array import array
from functools import lru_cache
import math
from pathlib import Path
import random
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from critic_acoustic_sequence_h99 import inspect, classify, RATE, SEGMENT_SECONDS

N = RATE * SEGMENT_SECONDS


@lru_cache(maxsize=8)
def signal(kind):
    rng = random.Random(20261118)
    if kind == "quiet":
        return array("h", [0]) * N
    if kind == "noise":
        return array("h", (rng.randint(-8000, 8000) for _ in range(N)))
    if kind not in {"tone", "beeps", "off_frequency"}:
        raise ValueError("bad test fixture")
    hz = 880 if kind == "off_frequency" else 440
    return array("h", (
        round(8000 * math.sin(2 * math.pi * hz * i / RATE))
        if (kind != "beeps" or i % (RATE * 2 // 5) < RATE * 12 // 100)
        else 0
        for i in range(N)
    ))


def make_wav(path, first, second, *, channels=1, rate=RATE):
    samples = array("h", signal(first) + signal(second))
    if sys.byteorder != "little":
        samples.byteswap()
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes(samples.tobytes())


class SequenceOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "fixture.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def test_four_counterfactual_pairs(self):
        families = (("tone","noise"),("beeps","noise"),
                    ("tone","quiet"),("beeps","quiet"))
        for a,b in families:
            for x,y in ((a,b),(b,a)):
                with self.subTest(first=x,second=y):
                    make_wav(self.path,x,y)
                    result=inspect(self.path)
                    self.assertEqual(result["ordered_labels"],[x,y])
                    self.assertEqual(result["status"],"NARROW_SIGNAL_ORACLE_REVIEW_REQUIRED")
                    self.assertFalse(result["authentic_minecraft_audio"])
                    self.assertFalse(result["temporal_model_qualified"])
                    self.assertFalse(result["stock_client_verified"])

    def test_other_frequency_cannot_be_claimed_broadband_noise(self):
        self.assertEqual(classify(signal("off_frequency"))["class"],"unknown")

    def test_clipped_audio_refused(self):
        burst = array("h", [32767]) * N
        with self.assertRaisesRegex(ValueError,"CLIPPED_SOURCE_UNQUALIFIED"):
            classify(burst)

    def test_mono_only(self):
        make_wav(self.path,"tone","noise",channels=2)
        with self.assertRaisesRegex(ValueError,"ONLY_MONO"):
            inspect(self.path)

    def test_bad_sampling_rate_refused(self):
        make_wav(self.path,"tone","noise",rate=44100)
        with self.assertRaisesRegex(ValueError,"ONLY_MONO"):
            inspect(self.path)

    def test_truncated_two_segments_refused(self):
        with wave.open(str(self.path),"wb") as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(RATE)
            file.writeframes(signal("tone").tobytes())
        with self.assertRaisesRegex(ValueError,"REQUIRES_EXACT_TWO"):
            inspect(self.path)

    def test_empty_and_symlink_refused(self):
        self.path.write_bytes(b"")
        with self.assertRaisesRegex(ValueError,"MEDIA_SIZE_UNSAFE"):
            inspect(self.path)
        self.path.unlink()
        actual=Path(self.tmp.name)/"actual.wav"
        make_wav(actual,"tone","noise")
        self.path.symlink_to(actual)
        with self.assertRaisesRegex(ValueError,"MEDIA_UNAVAILABLE_OR_SYMLINK"):
            inspect(self.path)

    def test_unknown_signal_is_not_a_temporal_positive(self):
        self.assertEqual(classify(signal("off_frequency"))["class"],"unknown")


if __name__ == "__main__":
    unittest.main()
