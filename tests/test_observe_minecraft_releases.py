"""Source-only fail-closed tests for OP-5 release observation."""
import copy
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from observe_minecraft_releases import observe, publish_once, WatchRefused

SHA = "0123456789abcdef0123456789abcdef01234567"
BASE = {
    "latest": {"release": "26.3", "snapshot": "26.4-snapshot-3"},
    "versions": [
        {"id": "26.3", "type": "release",
         "sha1": SHA, "url": "https://piston-meta.mojang.com/a.json",
         "releaseTime": "2026-09-15T00:00:00Z"},
        {"id": "26.4-snapshot-3", "type": "snapshot",
         "sha1": SHA, "url": "https://piston-meta.mojang.com/b.json",
         "releaseTime": "2026-10-06T00:00:00Z"},
    ]
}


class ReleaseWatchTests(unittest.TestCase):
    def test_stable_pair_is_observed_with_no_promotion(self):
        row = observe(copy.deepcopy(BASE), "f"*64)
        self.assertEqual(row["observed"]["release"]["id"], "26.3")
        self.assertEqual(row["snapshot_classification"], "26.4_RDTE_PREVIEW_ONLY")
        self.assertFalse(row["operational_promotion_allowed"])
        self.assertFalse(row["world_mutated"])
        self.assertEqual(row["physical_truenas_apply"], "HOLD")
        self.assertEqual(row["pair_key"], observe(copy.deepcopy(BASE), "0"*64)["pair_key"])

    def test_new_stable_is_only_candidate(self):
        row = copy.deepcopy(BASE)
        row["latest"]["release"] = "26.4"
        row["versions"][0]["id"] = "26.4"
        result = observe(row, "f"*64)
        self.assertEqual(result["operational_change"], "CANDIDATE_REQUALIFICATION_REQUIRED")
        self.assertFalse(result["operational_promotion_allowed"])

    def test_duplicate_or_untrusted_metadata_fails_closed(self):
        row = copy.deepcopy(BASE)
        row["versions"].append(copy.deepcopy(row["versions"][0]))
        with self.assertRaisesRegex(WatchRefused, "NOT_UNIQUELY"):
            observe(row, "x")
        row = copy.deepcopy(BASE)
        row["versions"][0]["url"] = "https://untrusted.example/evil"
        with self.assertRaisesRegex(WatchRefused, "METADATA_HOST"):
            observe(row, "x")

    def test_invalid_release_name_is_refused(self):
        row = copy.deepcopy(BASE)
        row["latest"]["release"] = "../26.3"
        with self.assertRaisesRegex(WatchRefused, "INVALID_LATEST"):
            observe(row, "x")

    def test_issue_writes_are_main_only(self):
        record = observe(copy.deepcopy(BASE), "0"*64)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "SupraCraft/mc-server-images",
                 "GITHUB_REF": "refs/heads/feat/26-4-release-metadata-watch-op5",
                 "GITHUB_EVENT_NAME": "workflow_dispatch"}):
            with self.assertRaisesRegex(WatchRefused, "ISSUE_WRITE_NOT_AUTHORIZED"):
                publish_once(record, "fake-token")

    def test_repeat_observation_emits_no_second_comment(self):
        record = observe(copy.deepcopy(BASE), "0"*64)
        marker = "<!-- supracraft-mc-release-pair:" + record["pair_key"] + " -->"
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "SupraCraft/mc-server-images",
                 "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "schedule"}), \
             patch("observe_minecraft_releases.github_api",
                   return_value=[{"body": marker}]) as mock:
            self.assertEqual(publish_once(record, "fake-token"), "ALREADY_RECORDED")
            self.assertEqual(mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
