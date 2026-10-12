"""OP-1 cheap red/blue source contract tests, no network or server required."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from qualify_velocity_paper_263_forwarding import (
    Refused, patch_paper_global, paper_usercache, run_bot, velocity_config
)
from test_qualify_velocity_paper_263_link import DEFAULT


class PlayerForwardingTests(unittest.TestCase):
    def test_protocol_profile_is_loopback_modern_and_nonoperational(self):
        source = velocity_config(DEFAULT)
        self.assertIn('bind = "127.0.0.1:25577"', source)
        self.assertIn('player-info-forwarding-mode = "modern"', source)
        self.assertIn('lobby = "127.0.0.1:25586"', source)
        self.assertIn("online-mode = false", source)
        self.assertNotIn("lobby.example.com", source)

    def test_template_drift_is_refused_not_guessed(self):
        with self.assertRaises(Refused):
            velocity_config(DEFAULT.replace("player-info-forwarding-mode", "obsolete-forwarding-field"))

    def test_generated_paper_config_is_patched_and_read_back(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "paper-global.yml"
            path.write_text("proxies:\n  velocity:\n    enabled: false\n    online-mode: true\n    secret: ''\n  bungee-cord:\n    online-mode: true\n")
            patch_paper_global(path, "test-secret-not-for-production")
            import yaml
            row = yaml.safe_load(path.read_text())
            self.assertEqual(row["proxies"]["velocity"], {
                "enabled": True, "online-mode": False,
                "secret": "test-secret-not-for-production"
            })
            self.assertTrue(row["proxies"]["bungee-cord"]["online-mode"])

    def test_wrong_paper_schema_refuses_instead_of_replacing_entire_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / "paper-global.yml"
            path.write_text("proxies:\n  velocity:\n    enabled: false\n")
            with self.assertRaisesRegex(Refused, "PAPER_FORWARDING_KEYS_DRIFT"):
                patch_paper_global(path, "x")
            self.assertIn("enabled: false", path.read_text())

    @staticmethod
    def fake_bot(spawn=False, timed_out=False, protocol=None, kicked=None):
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "schema": "supracraft.forwarding-client/1",
            "requested_version": "26.3", "spawned": spawn,
            "protocol": protocol, "timed_out": timed_out,
            "kicked": kicked, "ended": bool(kicked), "error": None
        }))

    def test_denial_requires_observation(self):
        with patch("qualify_velocity_paper_263_forwarding.subprocess.run",
                   return_value=self.fake_bot(kicked="invalid-forwarding")):
            self.assertFalse(run_bot(25586, False)["spawned"])
        with patch("qualify_velocity_paper_263_forwarding.subprocess.run",
                   return_value=self.fake_bot(timed_out=True)):
            with self.assertRaisesRegex(Refused, "BOT_TIMED_OUT_NOT_DENIED"):
                run_bot(25586, False)

    def test_direct_backend_acceptance_is_a_red_failure(self):
        with patch("qualify_velocity_paper_263_forwarding.subprocess.run",
                   return_value=self.fake_bot(spawn=True, protocol=777)):
            with self.assertRaisesRegex(Refused, "UNEXPECTED_BOT_SPAWN_OR_DENIAL"):
                run_bot(25586, False)

    def test_success_requires_exact_protocol(self):
        with patch("qualify_velocity_paper_263_forwarding.subprocess.run",
                   return_value=self.fake_bot(spawn=True, protocol=776)):
            with self.assertRaisesRegex(Refused, "PROXIED_BOT_PROTOCOL_DRIFT"):
                run_bot(25577, True)

    def test_backend_identity_requires_unique_usercache_entry(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "usercache.json").write_text(json.dumps([
                {"name": "SupraProbe263", "uuid": "11111111-2222-3333-4444-555555555555"},
                {"name": "SupraProbe263", "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
            ]))
            with self.assertRaisesRegex(Refused, "PAPER_FORWARDING_PRINCIPAL_NOT_UNIQUE"):
                paper_usercache(root)


if __name__ == "__main__":
    unittest.main()
