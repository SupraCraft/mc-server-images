"""Cheap deterministic artifact export checks: NOT Minecraft runtime acceptance."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from export_core_restoration_datapack_26_3 import export, exact_source_commit


class ExportTests(unittest.TestCase):
    def test_repeat_produces_exact_immutable_datapack(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            receipts = []
            payloads = []
            for idx in (1, 2):
                out = root / str(idx) / "candidate.zip"
                manifest = root / str(idx) / "candidate.json"
                rec = export(out, manifest, world_id="lantern-rdte",
                             release_id="core-restore-26-3")
                receipts.append(rec)
                payloads.append(out.read_bytes())
                self.assertEqual(json.loads(manifest.read_text()), rec)
                self.assertEqual(rec["sha256"], hashlib.sha256(payloads[-1]).hexdigest())
                self.assertEqual(rec["producer"],
                                 "SupraCraft/mc-server-images@" + exact_source_commit())
                self.assertTrue(rec["artifact_format_verified"])
                self.assertFalse(rec["world_save_included"])
                self.assertFalse(rec["collage_deployed"])
                self.assertFalse(rec["minecraft_runtime_verified_by_this_export"])
                with zipfile.ZipFile(out) as zf:
                    self.assertEqual(sorted(zf.namelist()),
                                     sorted([x["path"] for x in rec["members"]]))
                    for info in zf.infolist():
                        self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                        self.assertFalse(info.filename.startswith("/"))
                        self.assertNotIn("..", info.filename.split("/"))
                        self.assertEqual(hashlib.sha256(zf.read(info)).hexdigest(),
                                         next(x["sha256"] for x in rec["members"]
                                              if x["path"] == info.filename))
                    metadata = json.loads(zf.read("pack.mcmeta"))
                    self.assertEqual(metadata["pack"]["min_format"], [121, 0])
                    self.assertEqual(metadata["pack"]["max_format"], [121, 0])
            self.assertEqual(receipts[0], receipts[1])
            self.assertEqual(payloads[0], payloads[1])

    def test_invalid_identity_refused_without_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            for bad in ("../other", "Two Rivers", "", "some/thing", "-invalid"):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    export(root / "candidate.zip", root / "candidate.json",
                           world_id=bad, release_id="release-1")
                self.assertFalse((root / "candidate.zip").exists())

    def test_distinct_manifest_not_overwritten_by_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            with self.assertRaises(ValueError):
                export(root / "x.zip", root / "x.zip",
                       world_id="world-1", release_id="release-1")


if __name__ == "__main__":
    unittest.main()
