"""Exact synthetic offline OP bot is confined to disposable standalone 26.3."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
import qualify_vanilla_datapack_player_263 as target

class OfflinePlayerSetupTests(unittest.TestCase):
    def test_offline_bot_java_v3_uuid_pinned(self):
        self.assertEqual(target.offline_bot_uuid(),
                         "f4469b77-cc14-3c07-95f3-0b0c3f151bd2")

    def test_only_one_synthetic_disposable_account_is_operator(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            target.install_disposable_operator(home)
            ops=json.loads((home/"ops.json").read_text())
            self.assertEqual(len(ops),1)
            self.assertEqual(ops[0]["uuid"],target.offline_bot_uuid())
            self.assertEqual(ops[0]["name"],"SupraCraftProbe")
            self.assertEqual(ops[0]["level"],4)
            self.assertFalse(ops[0]["bypassesPlayerLimit"])
            self.assertNotIn("truenas_admin",str(ops))
            self.assertNotIn("API_KEY",str(ops))

    def test_disposable_world_offline_and_rcon_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            target.server_config(p)
            data=(p/"server.properties").read_text()
            self.assertIn("server-ip=127.0.0.1",data)
            self.assertIn("online-mode=false",data)
            self.assertIn("enable-rcon=false",data)
            self.assertNotIn("enable-rcon=true",data)
            self.assertIn("spawn-protection=0",data)

if __name__=="__main__":
    unittest.main()
