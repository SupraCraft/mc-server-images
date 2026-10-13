"""S3 low-cost adversarial source-contract tests (no network or Java)."""
import pathlib
import sys
import unittest
from copy import deepcopy

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_vanilla_direct_proxy_263_equivalence import (
    BOT_NAME, config, same_baseline, semantic_equivalence, PACK_SHA,
)
from qualify_vanilla_world_artifact_activation_263 import Refused

BASE = {"username": BOT_NAME, "requested_version": "26.3",
        "negotiated_version": "26.3", "protocol": 777,
        "server_join_independently_observed": True,
        "client_saw_air_before": True, "client_saw_redstone_after": True,
        "action": "mineflayer.placeBlock", "offline_mode": True,
        "backend_uuid": "c3ee317f-cf1d-3b27-8ec6-03842bc98019",
        "world_effect": True, "rollback_reobserved": True}

class S3CheapTests(unittest.TestCase):
    def test_baseline_hash_identity_and_refusal(self):
        same_baseline("a"*64, "a"*64)
        for a,b in (("a"*64,"b"*64), ("", "a"*64), ("a"*62,"a"*62)):
            with self.subTest(a=a[:6], b=b[:6]), self.assertRaises(Refused):
                same_baseline(a,b)

    def test_semantics_matching_independent_observations(self):
        self.assertTrue(semantic_equivalence(BASE, BASE.copy(), BASE["backend_uuid"])
                        ["offline_protocol_only"])

    def test_protocol_version_and_action_drift_refused(self):
        for k, value in (("protocol",776), ("negotiated_version","26.4"),
                         ("client_saw_redstone_after",False),
                         ("world_effect",False), ("rollback_reobserved",False),
                         ("backend_uuid","00000000-0000-0000-0000-000000000000"),
                         ("action","imaginary"), ("server_join_independently_observed",False)):
            bad=deepcopy(BASE)
            bad[k]=value
            with self.subTest(k=k), self.assertRaises(Refused):
                semantic_equivalence(BASE,bad,BASE["backend_uuid"])

    def test_both_bad_does_not_elevate_to_equal(self):
        bad=deepcopy(BASE)
        bad["protocol"]=776
        with self.assertRaises(Refused):
            semantic_equivalence(bad,bad,BASE["backend_uuid"])

    def test_missing_receipt_denied(self):
        bad=deepcopy(BASE)
        bad.pop("server_join_independently_observed")
        with self.assertRaises(Refused):
            semantic_equivalence(BASE,bad,BASE["backend_uuid"])

    def test_loopback_seed_no_rcon_no_remote_ingress(self):
        text=config()
        for fragment in ("server-ip=127.0.0.1","server-port=25586",
                         "online-mode=false","enable-rcon=false",
                         "level-seed=4242424242"):
            self.assertIn(fragment,text)
        self.assertNotIn("0.0.0.0",text)
        self.assertEqual(PACK_SHA,
            "da25005e8729e6f013f7108ac5b8869dd46323befc78efdae18221b26cafe5f8")

if __name__ == "__main__":
    unittest.main()
