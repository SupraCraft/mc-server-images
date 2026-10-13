"""S2B cheap red/blue checks: no network, server, secrets, or player required."""
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

from qualify_velocity_vanillacord_263_forwarding import (
    VC_SHA256, PASS, Refused, backend_join_log, backend_usercache,
    download_vanillacord, expected_offline_uuid, trusted_release_location,
    validate_discovery, validate_vanilla_config, vanilla_config,
)
from test_qualify_velocity_paper_263_link import DEFAULT
from qualify_velocity_paper_263_forwarding import velocity_config


class S2BForwardingTests(unittest.TestCase):
    def test_public_release_integrity_is_original_not_new_release(self):
        self.assertEqual(VC_SHA256,
            "24e850a261dbf108e2f7ac412c34651ffae753543665ec47d5e40ff9c8981719")
        self.assertIn("VANILLACORD", PASS)
        self.assertTrue(trusted_release_location(
            "https://release-assets.githubusercontent.com/example/signed"))
        for url in (
            "http://github.com/SupraCraft/VanillaCord",
            "https://github.example.com/a",
            "https://evil.invalid/release",
            "https://github.com.evil.invalid/a",
            "https://user:secret@github.com/x",
            "https://github.com:444/x",
        ):
            self.assertFalse(trusted_release_location(url))

    def test_invalid_download_is_rejected_before_patching(self):
        class FakeReader:
            url = "https://release-assets.githubusercontent.com/immutable"
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, n): return b"BAD" if not hasattr(self, "read_once") else b""
        # Refuse wrong digest even when provenance URL is an allowed release host.
        def make():
            x = FakeReader()
            orig = x.read
            def read(n):
                if hasattr(x, "read_once"): return b""
                x.read_once = True
                return b"BAD"
            x.read = read
            return x
        with tempfile.TemporaryDirectory() as td:
            with patch("qualify_velocity_vanillacord_263_forwarding.urllib.request.urlopen",
                       return_value=make()):
                with self.assertRaisesRegex(Refused, "VC_RELEASE_BYTES_OR_DIGEST_DRIFT"):
                    download_vanillacord(pathlib.Path(td) / "vc.jar")

    def test_vanillacord_real_parser_keys_not_corrected_typo(self):
        secret = "f" * 64
        config = vanilla_config(secret)
        self.assertIn("forwarding = velocity\n", config)
        self.assertIn("seecret = ", config)
        self.assertNotIn("\nsecret = ", config)
        validate_vanilla_config(config, secret)
        with self.assertRaisesRegex(Refused, "VANILLACORD_CONFIG_READBACK_DRIFT"):
            validate_vanilla_config(config.replace("seecret", "secret"), secret)
        with self.assertRaisesRegex(Refused, "EPHEMERAL_SECRET_INVALID"):
            vanilla_config("test-secret")

    def test_vanilla_backend_cache_is_independent_and_unique(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)
            uuid = expected_offline_uuid("SupraProbe263")
            (path / "usercache.json").write_text(json.dumps([
                {"name":"SupraProbe263", "uuid": uuid}
            ]))
            self.assertEqual(backend_usercache(path, "SupraProbe263"), uuid)
            (path / "usercache.json").write_text(json.dumps([
                {"name":"SupraProbe263", "uuid": uuid},
                {"name":"SupraProbe263", "uuid": uuid}
            ]))
            with self.assertRaisesRegex(Refused, "VANILLA_USERCACHE_NOT_UNIQUE"):
                backend_usercache(path, "SupraProbe263")

    def test_vanilla_log_and_persisted_playerdata_are_independent_oracles(self):
        name = "SupraProbe263"
        player_uuid = expected_offline_uuid(name)
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            log = home / "server.log"
            data = home / "world" / "playerdata"
            data.mkdir(parents=True)
            log.write_text(f"[Server thread/INFO]: {name} joined the game\\n")
            with self.assertRaisesRegex(Refused, "VANILLA_FORWARDED_PLAYERDATA_MISSING"):
                backend_join_log(home, name, player_uuid)
            saved = data / (player_uuid + ".dat")
            saved.write_bytes(bytes((0x1f, 0x8b)) + bytes(100))
            self.assertTrue(backend_join_log(home, name, player_uuid))
            log.write_text(f"[Server thread/INFO]: SomeoneElse joined the game\\n")
            with self.assertRaisesRegex(Refused, "VANILLA_BACKEND_JOIN_LOG_MISSING"):
                backend_join_log(home, name, player_uuid)
            log.write_text(f"UUID of player {name} is 00000000-0000-0000-0000-000000000001\\n"
                           f"{name} joined the game\\n")
            with self.assertRaisesRegex(Refused, "VANILLA_UUID_LOG_MISMATCH"):
                backend_join_log(home, name, player_uuid)
            log.write_text(f"{name} joined the game\\n")
            saved.write_bytes(bytes(100))
            with self.assertRaisesRegex(Refused, "VANILLA_PLAYERDATA_NOT_COMPRESSED_NBT"):
                backend_join_log(home, name, player_uuid)

    def test_discovery_version_and_hold_gates(self):
        good={"classification":"READ_ONLY_CANDIDATES_DISCOVERED",
              "stable":{"vanilla":{"approved_release":"26.3"}}}
        _, sha = validate_discovery(good)
        self.assertEqual(len(sha), 64)
        with self.assertRaisesRegex(Refused, "OFFICIAL_DISCOVERY_NOT_ACCEPTED"):
            validate_discovery({**good, "classification":"INCONCLUSIVE"})
        with self.assertRaisesRegex(Refused, "MOJANG_263_POLICY_DRIFT"):
            validate_discovery({
                **good, "stable":{"vanilla":{"approved_release":"26.4"}}
            })

    def test_proxy_still_uses_existing_loopback_modern_template(self):
        config = velocity_config(DEFAULT)
        self.assertIn('bind = "127.0.0.1:25577"', config)
        self.assertIn('lobby = "127.0.0.1:25586"', config)
        self.assertIn('player-info-forwarding-mode = "modern"', config)
        self.assertIn("online-mode = false", config)


if __name__ == "__main__":
    unittest.main()
