import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tour_pack", ROOT / "tools" / "worldgen_tour_pack.py")
tour_pack = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(tour_pack)


class TourPackTests(unittest.TestCase):
    def test_writes_versioned_pack_manifest_and_functions(self):
        with tempfile.TemporaryDirectory() as td:
            world = pathlib.Path(td) / "world"
            sites = [{
                "site_id": "spawn",
                "category": "spawn-progression",
                "position": [0, 100, 0],
                "look_at": [0, 64, 0],
                "reason": "Spawn overview",
            }]
            manifest = tour_pack.write_tour_pack(world, 121, "bootstrap-normal", sites)
            pack = world / "datapacks" / "supracraft_benchmark"
            meta = json.loads((pack / "pack.mcmeta").read_text())
            self.assertEqual([121, 0], meta["pack"]["min_format"])
            self.assertEqual([121, 0], meta["pack"]["max_format"])
            self.assertTrue((pack / "data" / "supracraft" / "function" / "tour" / "start.mcfunction").exists())
            self.assertEqual("/function supracraft:tour/start", manifest["tour_start_command"])
            self.assertEqual("file/supracraft_benchmark", manifest["pack_id"])

    def test_rejects_unsafe_site_id(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                tour_pack.write_tour_pack(
                    pathlib.Path(td) / "world",
                    121,
                    "x",
                    [{"site_id": "../bad", "category": "anomaly-defect", "position": [0, 0, 0], "reason": "bad"}],
                )


if __name__ == "__main__":
    unittest.main()
