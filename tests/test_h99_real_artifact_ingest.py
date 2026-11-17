"""H99 replay source integrity checks; fake metadata is never a real artifact."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import replay_real_clap_artifact_h99 as m


def source_run():
    return {"id": m.SOURCE_RUN_ID, "head_sha": m.SOURCE_HEAD_SHA,
            "repository": {"full_name": m.REPO}, "status": "completed",
            "conclusion": "success", "event": "pull_request"}


def source_meta():
    return {"id": m.SOURCE_ARTIFACT_ID, "name": m.SOURCE_ARTIFACT_NAME,
            "expired": False, "digest": "sha256:" + m.SOURCE_ARTIFACT_ZIP_SHA256,
            "workflow_run": {"id": m.SOURCE_RUN_ID}}


class SourceArtifactAdmissionTests(unittest.TestCase):
    def test_trusted_run_claim_only_not_entire_model(self):
        m.validate_run(source_run())

    def test_wrong_commit_refused(self):
        run = source_run()
        run["head_sha"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "SOURCE_RUN_IDENTITY"):
            m.validate_run(run)

    def test_wrong_repository_refused(self):
        run = source_run()
        run["repository"]["full_name"] = "other/repo"
        with self.assertRaisesRegex(ValueError, "SOURCE_REPOSITORY"):
            m.validate_run(run)

    def test_non_success_run_refused(self):
        run = source_run()
        run["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "SOURCE_RUN_IDENTITY"):
            m.validate_run(run)

    def test_forged_published_archive_digest_refused(self):
        meta = source_meta()
        meta["digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "ARTIFACT_PUBLISHED_DIGEST"):
            m.validate_archive(meta, b"bogus")

    def test_expired_artifact_refused(self):
        meta = source_meta()
        meta["expired"] = True
        with self.assertRaisesRegex(ValueError, "ARTIFACT_RUN_LINK"):
            m.validate_archive(meta, b"bogus")

    def test_wrong_artifact_id_refused(self):
        meta = source_meta()
        meta["id"] = 0
        with self.assertRaisesRegex(ValueError, "ARTIFACT_IDENTITY"):
            m.validate_archive(meta, b"bogus")

    def test_wrong_archive_bytes_refused(self):
        with self.assertRaisesRegex(ValueError, "ARTIFACT_ZIP_SHA256"):
            m.validate_archive(source_meta(), b"bogus")

    def test_missing_run_id_link_refused(self):
        meta=source_meta()
        meta["workflow_run"]["id"]=m.SOURCE_RUN_ID+1
        with self.assertRaisesRegex(ValueError, "ARTIFACT_RUN_LINK"):
            m.validate_archive(meta, b"bogus")

    def test_oversized_archive_refused(self):
        with self.assertRaisesRegex(ValueError, "ARTIFACT_BYTES_UNSAFE"):
            m.validate_archive(source_meta(), b"x" * 100_001)

    @unittest.skipUnless(importlib.util.find_spec("numpy") is not None,
                         "optional NumPy: separately pinned source-oracle job")
    def test_independent_manifest_is_byte_deterministic_and_pairs(self):
        first = m.get_manifest()
        second = m.get_manifest()
        self.assertEqual(first, second)
        self.assertEqual(len(first["cases"]), 8)
        self.assertEqual(first["model_constraints"]["model"], m.MODEL)
        self.assertEqual(first["model_constraints"]["fixture_plan_sha256"],
                         m.sha(repr(m.PAIRS).encode()))
        for i in range(0, 8, 2):
            a,b=first["cases"][i:i+2]
            self.assertEqual(a["pair_id"],b["pair_id"])
            self.assertEqual(a["expected"],"first_a")
            self.assertEqual(b["expected"],"first_b")
            self.assertNotEqual(a["sha256"],b["sha256"])


if __name__ == "__main__":
    unittest.main()
