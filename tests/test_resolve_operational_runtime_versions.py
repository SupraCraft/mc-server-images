"""Offline, public-safe release discovery contract; no auto-upgrades."""
import copy
import json
import pathlib
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from resolve_operational_runtime_versions import (
    Refused, mojang_release, paper_build, resolve, velocity_build,
)

POLICY=json.loads((ROOT/"spec/operational-runtime-lanes-v1.json").read_text())
PAPER="https://fill.papermc.io/v3/projects/paper/versions/26.3/builds/177/downloads/server:default"
VELOCITY="https://fill.papermc.io/v3/projects/velocity/versions/4.2.0/builds/30/downloads/server:default"
METADATA="https://piston-meta.mojang.com/v1/packages/sha/26.3.json"

def fixtures():
    manifest={"latest":{"release":"26.3","snapshot":"26.4-snapshot-3"},
              "versions":[{"id":"26.3","type":"release","url":METADATA},
                          {"id":"26.4-snapshot-3","type":"snapshot","url":METADATA}]}
    paper=[{"id":177,"channel":"STABLE",
            "downloads":{"server:default":{"url":PAPER,
                                           "checksums":{"sha256":"a"*64}}}},
           {"id":178,"channel":"BETA",
            "downloads":{"server:default":{"url":PAPER}}}]
    velocity=[{"id":30,"channel":"STABLE",
               "downloads":{"server:default":{"url":VELOCITY,
                                               "checksums":{"sha256":"b"*64}}}}]
    return manifest,paper,velocity

class LanesTests(unittest.TestCase):
    def test_operational_26_3_protocol_and_current_bypass_rules(self):
        self.assertEqual(POLICY["stable"]["minecraft_java"]["version"],"26.3")
        self.assertEqual(POLICY["stable"]["minecraft_java"]["protocol"],777)
        self.assertEqual(POLICY["stable"]["minecraft_java"]["java_major"],25)
        self.assertFalse(POLICY["stable"]["paper"]["operationally_selected"])
        self.assertEqual(POLICY["stable"]["velocity"]["version"],"4.2.0")
        self.assertTrue(POLICY["policy"]["do_not_inherit_paper_1_21_11_qualification"])
        self.assertEqual(POLICY["policy"]["physical_truenas_apply"],"HOLD")

    def test_three_stable_candidates_and_canary_never_auto_apply(self):
        m,p,v=fixtures()
        r=resolve(POLICY,m,p,v)
        self.assertEqual(r["classification"],"READ_ONLY_CANDIDATES_DISCOVERED")
        self.assertEqual(r["stable"]["paper"]["build"],177)
        self.assertEqual(r["stable"]["velocity"]["build"],30)
        self.assertEqual(r["stable"]["vanilla"]["approved_release"],"26.3")
        self.assertTrue(r["preview"]["snapshot_matches_expected_series"])
        self.assertFalse(r["auto_deploy_authorized"])
        self.assertFalse(r["candidate_verified_by_real_runtime"])

    def test_unstable_paper_cannot_supplant_stable_build(self):
        m,p,v=fixtures()
        p.append({"id":999,"channel":"EXPERIMENTAL",
                  "downloads":{"server:default":{"url":PAPER}}})
        self.assertEqual(resolve(POLICY,m,p,v)["stable"]["paper"]["build"],177)
        with self.assertRaisesRegex(Refused,"NO_STABLE_PAPER_BUILD"):
            paper_build([p[-1]],"26.3")

    def test_build_drift_and_download_domain_refused(self):
        m,p,v=fixtures()
        v[0]["id"]=31
        with self.assertRaisesRegex(Refused,"PINNED_VELOCITY_BUILD_NOT_AVAILABLE"):
            resolve(POLICY,m,p,v)
        m,p,v=fixtures()
        p[0]["downloads"]["server:default"]["url"]="https://foreign.example/jar"
        with self.assertRaisesRegex(Refused,"PAPER_DOWNLOAD_UNTRUSTED"):
            resolve(POLICY,m,p,v)

    def test_suspicious_checksums_and_duplicates_fail(self):
        m,p,v=fixtures()
        p[0]["downloads"]["server:default"]["checksums"]["sha256"]="wrong"
        with self.assertRaisesRegex(Refused,"PAPER_DIGEST_DRIFT"):
            resolve(POLICY,m,p,v)
        m,p,v=fixtures()
        p.append(copy.deepcopy(p[0]))
        with self.assertRaisesRegex(Refused,"DUPLICATE_PAPER_BUILDS"):
            resolve(POLICY,m,p,v)

    def test_new_stable_release_is_observation_not_promotion(self):
        m,p,v=fixtures()
        m["latest"]["release"]="26.4"
        m["latest"]["snapshot"]="26.5-snapshot-1"
        r=resolve(POLICY,m,p,v)
        self.assertTrue(r["stable"]["vanilla"]["release_changed"])
        self.assertFalse(r["preview"]["snapshot_matches_expected_series"])
        self.assertFalse(r["auto_deploy_authorized"])

    def test_missing_pinned_mojang_release_refused(self):
        m,p,v=fixtures()
        m["versions"][0]["type"]="snapshot"
        with self.assertRaisesRegex(Refused,"PINNED_MINECRAFT_RELEASE_MISSING"):
            resolve(POLICY,m,p,v)

if __name__=="__main__":
    unittest.main()
