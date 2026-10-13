"""S4 cheap red/blue unit checks; no runtime nor network."""
import pathlib
import sys
import tempfile
import unittest
from copy import deepcopy

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from qualify_paper_263_gameplay_adapter import (
    paper_mode, scoped_pins, semantic_equivalence, Refused, BOT_NAME,
)
from qualify_velocity_paper_263_forwarding import expected_offline_uuid

SAMPLE={"username":BOT_NAME, "requested_version":"26.3",
        "negotiated_version":"26.3","protocol":777,
        "server_join_independently_observed":True,
        "client_saw_air_before":True,"client_saw_redstone_after":True,
        "action":"mineflayer.placeBlock","offline_mode":True,
        "backend_uuid":expected_offline_uuid(BOT_NAME),
        "world_effect":True,"rollback_reobserved":True}


class PaperAdapterTests(unittest.TestCase):
    def config(self,root,active=False,online=True,secret=""):
        p=root/"paper-global.yml"
        p.write_text("proxies:\n  velocity:\n"
                     f"    enabled: {'true' if active else 'false'}\n"
                     f"    online-mode: {'true' if online else 'false'}\n"
                     f"    secret: '{secret}'\n")
        return p

    def test_direct_and_modern_modes_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.config(pathlib.Path(d))
            paper_mode(p,None)
            p=self.config(pathlib.Path(d),True,False,"good")
            paper_mode(p,"good")

    def test_wrong_secret_and_wrong_auth_mode_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p=self.config(pathlib.Path(d),True,False,"right")
            with self.assertRaisesRegex(Refused,"S4_PAPER_FORWARDING_CONFIG_DRIFT"):
                paper_mode(p,"wrong")
            with self.assertRaisesRegex(Refused,"S4_DIRECT_BACKEND_PROXY_MODE_DRIFT"):
                paper_mode(p,None)
            p=self.config(pathlib.Path(d),True,True,"right")
            with self.assertRaisesRegex(Refused,"S4_PAPER_FORWARDING_CONFIG_DRIFT"):
                paper_mode(p,"right")

    def test_paper_config_schema_drift_denied(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/"paper-global.yml"
            with self.assertRaisesRegex(Refused,"S4_PAPER_GLOBAL_CONFIG_ABSENT"):
                paper_mode(p,None)
            p.write_text("proxies:\n  velocity:\n    enabled: false\n")
            with self.assertRaisesRegex(Refused,"S4_PAPER_KEYS_MISSING"):
                paper_mode(p,None)

    def test_gameplay_projection_requires_independent_backend_oracles(self):
        self.assertTrue(semantic_equivalence(SAMPLE,deepcopy(SAMPLE),
                        SAMPLE["backend_uuid"])["offline_protocol_only"])
        for key,value in (("protocol",776),
                          ("server_join_independently_observed",False),
                          ("client_saw_redstone_after",False),
                          ("world_effect",False), ("rollback_reobserved",False),
                          ("backend_uuid","00000000-0000-0000-0000-000000000000")):
            bad=deepcopy(SAMPLE)
            bad[key]=value
            with self.subTest(key=key),self.assertRaises(Refused):
                semantic_equivalence(SAMPLE,bad,SAMPLE["backend_uuid"])

    def test_source_scope_and_physical_hold(self):
        source={"classification":"READ_ONLY_CANDIDATES_DISCOVERED"}
        manifest={"backend":"vanilla","minecraft_version":"26.3",
                  "world_id":"lantern-rdte"}
        pin=scoped_pins(source,manifest)
        self.assertFalse(pin["selection"]["operational"])
        self.assertEqual(pin["selection"]["physical_trueNAS_apply"],"HOLD")
        for key,value in (("backend","paper"),("minecraft_version","26.4"),
                          ("world_id","production")):
            bad=dict(manifest)
            bad[key]=value
            with self.assertRaisesRegex(Refused,"S4_DATAPACK_SOURCE_SCOPE_DRIFT"):
                scoped_pins(source,bad)

if __name__=="__main__":
    unittest.main()
