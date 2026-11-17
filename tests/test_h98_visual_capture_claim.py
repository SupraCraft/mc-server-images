"""Claim-only 26.3 camera/media contract, no authoritative client claims."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from bridge_visual_capture_claim_h98 import correlate


def fixtures():
    media={"schema":"supracraft-critic-media-probe/v1",
           "sha256":"a"*64,"kind":"video","tracks":["video"],
           "duration_ms":5000,"review_status":"REVIEW_REQUIRED",
           "minecraft_runtime_verified":False,"stock_client_verified":False}
    route={"schema":"supracraft-h98-tour-claim/v1",
           "media_sha256":"a"*64,"route_contract":"supracraft.visual-route/v0.2",
           "claimed_server_version":"26.3","claimed_protocol":777,
           "route_manifest_sha256":"b"*64,"world_sha256":"c"*64,
           "server_receipt_sha256":"d"*64,
           "source_run_url":"https://github.com/SupraCraft/mc-server-images/actions/runs/12345",
           "views":[{"id":"approach","frame_ms":0,"xyz":[12.0,65.0,4.0]},
                    {"id":"interior","frame_ms":4000,"xyz":[17.0,65.0,8.0]}],
           "official_client_verified":False,"human_accepted":False}
    return media,route


class VisualCaptureCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.m,self.r=fixtures()
    def assertRefused(self,reason):
        with self.assertRaisesRegex(ValueError,reason):
            correlate(self.m,self.r)
    def test_links_source_only_no_authenticity_promotion(self):
        x=correlate(self.m,self.r)
        self.assertEqual(x["status"],"CORRELATED_SOURCE_CLAIMS_REVIEW_REQUIRED")
        self.assertEqual(x["view_count"],2)
        self.assertFalse(x["source_run_independently_authenticated"])
        self.assertFalse(x["official_server_verified"])
        self.assertFalse(x["stock_client_verified"])
        self.assertFalse(x["human_story_acceptance"])
        self.assertFalse(x["critic_model_qualified"])
    def test_media_mismatch(self):
        self.r["media_sha256"]="f"*64
        self.assertRefused("MEDIA_BYTES_HASH_MISMATCH")
    def test_audio_only_is_not_visual_tour(self):
        self.m["kind"]="audio"
        self.assertRefused("VIDEO_TOUR_MEDIA_REQUIRED")
    def test_route_schema_mismatch(self):
        self.r["route_contract"]="supracraft.visual-route/v0.1"
        self.assertRefused("UNSUPPORTED_ROUTE_CONTRACT")
    def test_wrong_runtime_refused(self):
        self.r["claimed_protocol"]=766
        self.assertRefused("WRONG_RUNTIME_VERSION_CLAIM")
        self.r["claimed_protocol"]=777
        self.r["claimed_server_version"]="26.2"
        self.assertRefused("WRONG_RUNTIME_VERSION_CLAIM")
    def test_missing_view_refused(self):
        self.r["views"]=[]
        self.assertRefused("BOUNDED_TOUR_VIEWPOINTS_REQUIRED")
    def test_nonmonotonic_timestamp_refused(self):
        self.r["views"][1]["frame_ms"]=0
        self.assertRefused("NONMONOTONIC_OR_OUT_OF_BOUNDS_FRAME")
    def test_out_of_media_timestamp_refused(self):
        self.r["views"][1]["frame_ms"]=5001
        self.assertRefused("NONMONOTONIC_OR_OUT_OF_BOUNDS_FRAME")
    def test_invalid_coordinate_refused(self):
        self.r["views"][0]["xyz"]=[float("nan"),64,0]
        self.assertRefused("INVALID_VIEW_LOCATION")
    def test_duplicate_view_refused(self):
        self.r["views"][1]["id"]="approach"
        self.assertRefused("DUPLICATE_OR_INVALID_VIEW_ID")
    def test_unverified_run_url_cannot_be_external(self):
        self.r["source_run_url"]="https://example.com/run/123"
        self.assertRefused("SOURCE_RUN_LINK_UNTRUSTED")
    def test_forged_client_acceptance_refused(self):
        self.r["official_client_verified"]=True
        self.assertRefused("ROUTE_AUTHORITY_CLAIM_FORGED")
    def test_forged_media_acceptance_refused(self):
        self.m["stock_client_verified"]=True
        self.assertRefused("MEDIA_AUTHORITY_CLAIM_FORGED")
    def test_route_manifest_hash_required(self):
        self.r["route_manifest_sha256"]="unverified"
        self.assertRefused("INVALID_ROUTE_PROVENANCE_DIGEST")
    def test_media_duration_needs_bounds(self):
        self.m["duration_ms"]=None
        self.assertRefused("BOUNDED_VIDEO_DURATION_REQUIRED")


if __name__=="__main__":
    unittest.main()
