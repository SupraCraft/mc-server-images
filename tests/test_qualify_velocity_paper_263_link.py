"""Source-only negative qualification for the current Java status data plane."""
import copy
import json
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from qualify_velocity_paper_263_link import (
    Refused, make_velocity_config, pinned_artifact, backend_status, load_pins
)

DEFAULT='''config-version = "2.9"
bind = "0.0.0.0:25565"
online-mode = true
force-key-authentication = true
player-info-forwarding-mode = "NONE"
forwarding-secret-file = "forwarding.secret"
[ping-passthrough]
version = false
players = false
description = false
favicon = false
modinfo = false
[packet-limiter]
enabled = true
[servers]
lobby = "127.0.0.1:30066"
factions = "127.0.0.1:30067"
try = ["lobby","factions"]
[forced-hosts]
"lobby.example.com" = ["lobby"]
[advanced]
read-timeout = 30000
'''

class LinkTests(unittest.TestCase):
    def test_real_digest_pins_are_not_floating(self):
        p=load_pins()
        self.assertEqual(p["paper"]["sha256"],
                         "580c266b6526bb34752e9c2c274be025f763af1ce5b3fa662fa2b3006f966c13")
        self.assertEqual(p["velocity"]["sha256"],
                         "35a5596a5468a035d8a32c8de5ebb0dc6b8d8f0cc3ff5169d514aca762af8aa8")
        self.assertFalse(p["selection"]["operational"])
        self.assertEqual(p["proxy_link"]["first_gate"],"BACKEND_STATUS_PASSTHROUGH_ONLY")

    def test_generated_configuration_is_loopback_and_not_promotable(self):
        s=make_velocity_config(DEFAULT)
        self.assertIn('bind = "127.0.0.1:25577"',s)
        self.assertIn('lobby = "127.0.0.1:25586"',s)
        self.assertNotIn("30067",s)
        self.assertNotIn("lobby.example.com",s)
        self.assertIn("description = true",s)
        self.assertIn('player-info-forwarding-mode = "NONE"',s)

    def test_changed_template_rejected(self):
        with self.assertRaisesRegex(Refused,"VELOCITY_PING_CONFIG_SCHEMA_DRIFT"):
            make_velocity_config(DEFAULT.replace("[ping-passthrough]","[other-section]"))
        with self.assertRaisesRegex(Refused,"VELOCITY_TEMPLATE_KEY_DRIFT_bind"):
            make_velocity_config(DEFAULT.replace('bind = "0.0.0.0:25565"',""))

    def test_backend_motd_is_actual_data_dependency(self):
        self.assertTrue(backend_status({"description":"SUPRACRAFT_263_PAPER_BACKEND_RDTE"}))
        self.assertFalse(backend_status({"description":"VELOCITY_PROXY_ONLY"}))
        self.assertFalse(backend_status({}))

if __name__=="__main__":
    unittest.main()
