#!/usr/bin/env python3
"""Falsify public hosting-stack authority boundaries using synthetic fixtures only."""
import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "spec/minecraft-hosting-stack-v1.json").read_text())
VALIDATOR = ROOT / "tools/validate_minecraft_hosting_stack.py"


class TestHostingStackBoundaries(unittest.TestCase):
    def run_fixture(self, fixture):
        with tempfile.TemporaryDirectory(prefix="mc-stack-contract-") as directory:
            root = pathlib.Path(directory)
            (root / "tools").mkdir()
            (root / "spec").mkdir()
            shutil.copyfile(VALIDATOR, root / "tools/validate_minecraft_hosting_stack.py")
            (root / "spec/minecraft-hosting-stack-v1.json").write_text(
                json.dumps(fixture), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(root / "tools/validate_minecraft_hosting_stack.py")],
                capture_output=True, text=True, timeout=5, check=False)

    def test_accepted_public_contract(self):
        result = self.run_fixture(copy.deepcopy(SPEC))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_crossed_ingress_and_world_boundaries_are_rejected(self):
        cases = [
            ("backend made public ingress",
             lambda d: d["ingress"].update(service="paper"),
             "sole player-facing ingress"),
            ("velocity no longer player-facing",
             lambda d: d["ingress"].update(player_facing=False),
             "sole player-facing ingress"),
            ("modern forwarding removed",
             lambda d: d["ingress"].update(capabilities=["velocity_identity_optional"]),
             "modern forwarding capability missing"),
            ("world made non-mutable",
             lambda d: d["world_storage"].update(mutable_runtime_mount=False),
             "World runtime mount must remain explicit"),
        ]
        for label, change, expected in cases:
            with self.subTest(label=label):
                fixture = copy.deepcopy(SPEC)
                change(fixture)
                result = self.run_fixture(fixture)
                self.assertNotEqual(result.returncode, 0, label)
                self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    unittest.main()
