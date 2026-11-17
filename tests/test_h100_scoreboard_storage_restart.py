"""H100 scoreboard file location and metadata falsifiers (not actual game proof)."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
import json
import hashlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from h100_vanilla_scoreboard_path_restart import qualify_scoreboard_storage, GOOD, LEGACY, marker_present


class ScoreboardPathTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix="h100-scoreboard-test-")
        self.root=Path(self.t.name)
        self.good=self.root/GOOD
        self.good.parent.mkdir(parents=True)
        self.good.write_bytes(gzip.compress(b"synthetic NBT marker h100 #restored source-only"))
    def tearDown(self):
        self.t.cleanup()
    def test_proposed_namespaced_file_accepted_bounded_only(self):
        r=qualify_scoreboard_storage(self.root)
        self.assertEqual(r["relative_path"],GOOD)
        self.assertTrue(r["nbt_marker_only_not_value_validation"])
        self.assertTrue(r["legacy_path_absent"])
        self.assertEqual(len(r["file_sha256"]),64)
    def test_legacy_path_even_with_good_path_is_refused(self):
        stale=self.root/LEGACY
        stale.write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError,"LEGACY_SCOREBOARD_PATH_PRESENT"):
            qualify_scoreboard_storage(self.root)
    def test_legacy_only_is_not_accepted(self):
        self.good.unlink()
        (self.root/LEGACY).write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError,"LEGACY_SCOREBOARD_PATH_PRESENT"):
            qualify_scoreboard_storage(self.root)
    def test_missing_canonical_path_refused(self):
        self.good.unlink()
        with self.assertRaisesRegex(ValueError,"NAMESPACED_SCOREBOARD_PATH_MISSING"):
            qualify_scoreboard_storage(self.root)
    def test_symlink_canonical_refused(self):
        target=self.root/"target"
        target.write_bytes(self.good.read_bytes())
        self.good.unlink()
        self.good.symlink_to(target)
        with self.assertRaisesRegex(ValueError,"NAMESPACED_SCOREBOARD_PATH_MISSING"):
            qualify_scoreboard_storage(self.root)
    def test_nongzip_source_refused(self):
        self.good.write_bytes(b"abcdef"*20)
        with self.assertRaisesRegex(ValueError,"SCOREBOARD_NOT_GZIP_NBT"):
            qualify_scoreboard_storage(self.root)
    def test_marker_missing_refused(self):
        self.good.write_bytes(gzip.compress(b"no score stored here"))
        with self.assertRaisesRegex(ValueError,"SCOREBOARD_NBT_MARKERS_MISSING"):
            qualify_scoreboard_storage(self.root)
    def test_oversize_compressed_refused(self):
        self.good.write_bytes(b"X"*2_000_001)
        with self.assertRaisesRegex(ValueError,"SCOREBOARD_NBT_LENGTH_INVALID"):
            qualify_scoreboard_storage(self.root)
    def test_log_marker_only_accepts_server_origin(self):
        log=self.root/"game.log"
        log.write_text("console> execute if score #restored h100 matches 1 run say H100_SCORE_PRE_VERIFIED\n")
        self.assertFalse(marker_present(log,"PRE"))
        log.write_text("[12:01:01] [Server thread/INFO]: [Not Secure] [Server] H100_SCORE_PRE_VERIFIED\n")
        self.assertTrue(marker_present(log,"PRE"))
        self.assertFalse(marker_present(log,"POST"))
    def test_invalid_gzip_refused(self):
        self.good.write_bytes(b"\x1f\x8b"+b"X"*100)
        with self.assertRaisesRegex(ValueError,"SCOREBOARD_NBT_DECODE_REFUSED"):
            qualify_scoreboard_storage(self.root)


class FirstRealBlueSnapshotTests(unittest.TestCase):
    def test_original_official_server_blue_log_is_immutable(self):
        raw=(Path(__file__).resolve().parents[1]/"evidence/h100/official-26.3-scoreboard-restart-first-blue.json").read_bytes()
        blob=b"blob "+str(len(raw)).encode()+b"\x00"+raw
        self.assertEqual(hashlib.sha1(blob).hexdigest(),"a6592cf2bc80c0ad3eec64a4ae4ef8b16da2ed5b")
        data=json.loads(raw)
        self.assertEqual(data["status"],"OFFICIAL_26_3_SCOREBOARD_PATH_AND_RESTART_ACCEPTED_BOUNDED")
        self.assertEqual(data["first"]["relative_path"],"world/data/minecraft/scoreboard.dat")
        self.assertEqual(data["after_restart"]["relative_path"],"world/data/minecraft/scoreboard.dat")
        self.assertEqual(data["first"]["file_sha256"],data["after_restart"]["file_sha256"])
        self.assertEqual({x["marker"] for x in data["authoritative_oracles"]},
                         {"H100_SCORE_PRE_VERIFIED","H100_SCORE_POST_VERIFIED"})
        self.assertTrue(all(x["score_observed_from_server"] for x in data["authoritative_oracles"]))
        self.assertFalse(data["restoration_story_verified"])
        self.assertFalse(data["stock_client_verified"])


if __name__=="__main__":
    unittest.main()
