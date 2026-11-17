"""H100 player negative/positive receipt admissions, exact source-marker parser."""
import json
from pathlib import Path
import tempfile
import unittest
import hashlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from h100_physical_restoration_negative_matrix import (
    exact_marker_count, validate_valid_install, validate_wrong_support, configure,
)

def bot_result(*, valid):
    return {
        "requested_version":"26.3",
        "protocol_version":777,
        "_exit":0 if valid else 1,
        "placed":bool(valid),
        "error":None if valid else "Error: core socket support block is not stone",
        "before":"air" if valid else None,
        "after":"redstone_block" if valid else None,
    }


class H100NegativeAdmissionTests(unittest.TestCase):
    def test_wrong_support_actual_player_error_required(self):
        validate_wrong_support(bot_result(valid=False))
    def test_wrong_support_success_is_red(self):
        item=bot_result(valid=False);item["_exit"]=0
        with self.assertRaisesRegex(RuntimeError,"WRONG_SUPPORT_PLAYER_UNEXPECTEDLY_PLACED"):
            validate_wrong_support(item)
    def test_wrong_support_missing_error_is_red(self):
        item=bot_result(valid=False);item["error"]="socket was fine"
        with self.assertRaisesRegex(RuntimeError,"WRONG_SUPPORT_NOT_FAIL_CLOSED_BY_PLAYER"):
            validate_wrong_support(item)
    def test_wrong_support_wrong_protocol_is_red(self):
        item=bot_result(valid=False);item["protocol_version"]=766
        with self.assertRaisesRegex(RuntimeError,"BOT_NOT_EXACT_PROTOCOL_777"):
            validate_wrong_support(item)
    def test_valid_real_player_placement_is_narrow_success(self):
        validate_valid_install(bot_result(valid=True))
    def test_valid_but_wrong_item_is_refused(self):
        item=bot_result(valid=True);item["after"]="gold_block"
        with self.assertRaisesRegex(RuntimeError,"VALID_PLAYER_CORE_BLOCK_MISMATCH"):
            validate_valid_install(item)
    def test_valid_but_wrong_before_is_refused(self):
        item=bot_result(valid=True);item["before"]="stone"
        with self.assertRaisesRegex(RuntimeError,"VALID_PLAYER_CORE_BLOCK_MISMATCH"):
            validate_valid_install(item)
    def test_valid_but_worker_failed_is_refused(self):
        item=bot_result(valid=True);item["_exit"]=1
        with self.assertRaisesRegex(RuntimeError,"VALID_PLAYER_DID_NOT_PLACE_CORE"):
            validate_valid_install(item)
    def test_valid_but_worker_error_is_refused(self):
        item=bot_result(valid=True);item["error"]="player denied"
        with self.assertRaisesRegex(RuntimeError,"VALID_PLAYER_DID_NOT_PLACE_CORE"):
            validate_valid_install(item)
    def test_valid_but_wrong_client_is_refused(self):
        item=bot_result(valid=True);item["requested_version"]="26.2"
        with self.assertRaisesRegex(RuntimeError,"BOT_NOT_EXACT_PROTOCOL_777"):
            validate_valid_install(item)
    def test_console_command_echo_is_not_authoritative(self):
        with tempfile.TemporaryDirectory() as t:
            log=Path(t)/"server.log"
            log.write_text("stdin> execute if block 0 70 0 gold_block run say H100_WRONG_ITEM_REJECTED\n")
            self.assertEqual(exact_marker_count(log,"H100_WRONG_ITEM_REJECTED"),0)
            log.write_text("[23:01:00] [Server thread/INFO]: [Not Secure] [Server] H100_WRONG_ITEM_REJECTED\n")
            self.assertEqual(exact_marker_count(log,"H100_WRONG_ITEM_REJECTED"),1)
            self.assertEqual(exact_marker_count(log,"H100_VALID_CORE_INSTALLED"),0)
    def test_config_adds_explicit_loopback(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            configure(p)
            txt=(p/"server.properties").read_text()
            self.assertIn("server-ip=127.0.0.1\n",txt)
            self.assertIn("online-mode=false\n",txt)
            self.assertIn("enable-rcon=false\n",txt)


class FirstRealBlueSnapshotTests(unittest.TestCase):
    def test_original_real_unprivileged_player_blue_log_is_immutable(self):
        raw=(Path(__file__).resolve().parents[1]/"evidence/h100/official-26.3-physical-negative-first-blue.json").read_bytes()
        blob=b"blob "+str(len(raw)).encode()+b"\x00"+raw
        self.assertEqual(hashlib.sha1(blob).hexdigest(),"68f43463f3280d912c86b0c17c2d100d62acaaad")
        data=json.loads(raw)
        self.assertEqual(data["status"],"PUBLIC_26_3_SYNTHETIC_NEGATIVES_AND_POSITIVE_ACCEPTED_BOUNDED")
        self.assertTrue(data["negative_wrong_object"]["rejected"])
        self.assertEqual(data["negative_wrong_object"]["source"],"fixture_console_injected")
        self.assertTrue(data["negative_wrong_support"]["refused"])
        self.assertEqual(data["negative_wrong_support"]["source"],
                         "real_connected_unprivileged_mineflayer_player")
        self.assertEqual(data["valid_install"]["before"],"air")
        self.assertEqual(data["valid_install"]["after"],"redstone_block")
        self.assertTrue(data["restart_same_world_consequence"])
        self.assertFalse(data["unique_marked_core_custody_verified"])
        self.assertFalse(data["lantern_authored_story_verified"])
        self.assertFalse(data["human_or_stock_client_accepted"])


if __name__=="__main__":
    unittest.main()
