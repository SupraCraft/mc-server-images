import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from qualify_vanilla_datapack_player_263 import validate_client_result, Refused

JOIN = "SupraCraftProbe joined the game"
BASE = {"schema":"supracraft.mineflayer-core-placement/v0.1",
  "placed":True,"before":"air","after":"redstone_block",
  "core_item":"redstone_block","requested_version":"26.3",
  "negotiated_version":"26.3","protocol_version":777,
  "milestones":{"connect":1,"login":2,"spawn":3,"placed":4}}

class ClientReceiptTests(unittest.TestCase):
    def test_good(self):
        a = validate_client_result(BASE.copy(),0,JOIN)
        self.assertTrue(a["server_join_independently_observed"])
    def test_operator_mode_requires_worker_report_and_ordered_milestone(self):
        good=BASE.copy()
        good["operator_fixture_source"]="mineflayer_signed_chat_commands"
        good["milestones"]=dict(BASE["milestones"],operator_commands_sent=3)
        self.assertTrue(validate_client_result(
            good,0,JOIN,operator_setup=True)["server_join_independently_observed"])
        for bad in (
            dict(good,operator_fixture_source="server_console"),
            dict(good,milestones=dict(BASE["milestones"])),
            dict(good,milestones=dict(BASE["milestones"],operator_commands_sent=9)),
        ):
            with self.assertRaisesRegex(Refused,"OFFLINE_OPERATOR_BOT_COMMANDS_UNPROVEN"):
                validate_client_result(bad,0,JOIN,operator_setup=True)

    def test_missing_join(self):
        with self.assertRaises(Refused):
            validate_client_result(BASE.copy(),0,"no backend join")
    def test_bad_versions(self):
        for k,v in (("protocol_version",776),("requested_version","26.4"),
                    ("negotiated_version","1.21.11"),("placed",False),
                    ("before","redstone_block"),("after","air")):
            candidate = BASE.copy()
            candidate[k]=v
            with self.subTest(k=k),self.assertRaises(Refused):
                validate_client_result(candidate,0,JOIN)
    def test_spawn_and_error(self):
        for stage in ("connect","login","spawn","placed"):
            candidate=BASE.copy()
            candidate["milestones"]={k:v for k,v in BASE["milestones"].items() if k!=stage}
            with self.subTest(stage=stage),self.assertRaises(Refused):
                validate_client_result(candidate,0,JOIN)
        with self.assertRaises(Refused):
            validate_client_result(BASE.copy(),1,JOIN)

if __name__=="__main__":
    unittest.main()
