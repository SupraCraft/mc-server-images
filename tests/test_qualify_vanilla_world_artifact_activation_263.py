"""OP-3 cheap fail-closed artifact intake tests (no game server or network)."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from qualify_vanilla_world_artifact_activation_263 import (
    MEMBERS, PRODUCER, Refused, validate_candidate
)


class WorldCandidateTests(unittest.TestCase):
    def fixture(self, home):
        artifact = home / "candidate.zip"
        payloads = {
            "pack.mcmeta": json.dumps({"pack": {"min_format": [121, 0],
                                                  "max_format": [121, 0]}}).encode(),
            "data/minecraft/tags/function/tick.json": b'{"values":["supracraft_core_restore:tick"]}',
            "data/supracraft_core_restore/function/tick.mcfunction": b'say source-verified\n'
        }
        with zipfile.ZipFile(artifact, "w") as out:
            for path, content in payloads.items():
                out.writestr(path, content)
        data = artifact.read_bytes()
        manifest = {
            "schema": "supracraft-vanilla-datapack-candidate/1",
            "classification": "SOURCE_ARTIFACT_EXPORTED",
            "producer": PRODUCER, "kind": "datapack",
            "backend": "vanilla", "minecraft_version": "26.3",
            "world_id": "lantern-rdte",
            "release_id": "lantern-core-restore-26-3",
            "pack_format": [121, 0],
            "world_save_included": False,
            "collage_deployed": False,
            "sha256": hashlib.sha256(data).hexdigest(),
            "archive_size": len(data),
            "members": [
                {"path": name, "bytes": len(payload),
                 "sha256": hashlib.sha256(payload).hexdigest()}
                for name, payload in payloads.items()
            ]
        }
        return artifact, manifest

    def test_expected_inner_zip_passes_and_cannot_claim_deployment(self):
        with tempfile.TemporaryDirectory() as td:
            zip_path, manifest = self.fixture(pathlib.Path(td))
            rec = validate_candidate(zip_path, manifest)
            self.assertEqual(rec["sha256"], manifest["sha256"])
            self.assertEqual(rec["member_count"], len(MEMBERS))

    def test_refuse_wrong_realm_version_and_producer(self):
        with tempfile.TemporaryDirectory() as td:
            z, m = self.fixture(pathlib.Path(td))
            for field, value in (
                ("world_id", "other-realm"),
                ("minecraft_version", "26.4"),
                ("backend", "paper"),
                ("producer", "SupraCraft/mc-server-images@main"),
                ("pack_format", [123, 0]),
                ("collage_deployed", True),
            ):
                other = dict(m, **{field: value})
                with self.subTest(field=field), self.assertRaises(Refused):
                    validate_candidate(z, other)

    def test_refuse_bad_inner_digest_and_member_hash(self):
        with tempfile.TemporaryDirectory() as td:
            z, m = self.fixture(pathlib.Path(td))
            with self.assertRaisesRegex(Refused, "INNER_SHA256"):
                validate_candidate(z, dict(m, sha256="0"*64))
            copy = dict(m)
            copy["members"] = [dict(x) for x in m["members"]]
            copy["members"][0]["sha256"] = "f" * 64
            with self.assertRaisesRegex(Refused, "MEMBER_DIGEST"):
                validate_candidate(z, copy)

    def test_refuse_outer_archive_instead_of_inner_zip(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            z, m = self.fixture(root)
            outer = root / "gha-outer.zip"
            with zipfile.ZipFile(outer, "w") as out:
                out.write(z, "candidate.zip")
            fake = dict(m, sha256=hashlib.sha256(outer.read_bytes()).hexdigest(),
                        archive_size=outer.stat().st_size)
            with self.assertRaisesRegex(Refused, "MEMBER_SET_DRIFT"):
                validate_candidate(outer, fake)

    def test_refuse_symlink_candidate_and_traversal_zip(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            z, m = self.fixture(root)
            link = root / "link.zip"
            link.symlink_to(z)
            with self.assertRaisesRegex(Refused, "REGULAR_FILE"):
                validate_candidate(link, m)
            with zipfile.ZipFile(z, "a") as out:
                out.writestr("../escape", "bad")
            m["sha256"] = hashlib.sha256(z.read_bytes()).hexdigest()
            m["archive_size"] = z.stat().st_size
            with self.assertRaisesRegex(Refused, "MEMBER_SET_DRIFT"):
                validate_candidate(z, m)


if __name__ == "__main__":
    unittest.main()
