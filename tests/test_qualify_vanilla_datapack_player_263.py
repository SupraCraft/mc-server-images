import unittest
from tools.qualify_vanilla_datapack_player_263 import validate_client_result, Refused

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
