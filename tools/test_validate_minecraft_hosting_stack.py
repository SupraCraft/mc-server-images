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

    def run_raw_text(self, text):
        with tempfile.TemporaryDirectory(prefix="mc-stack-contract-") as directory:
            root = pathlib.Path(directory)
            (root / "tools").mkdir()
            (root / "spec").mkdir()
            shutil.copyfile(VALIDATOR, root / "tools/validate_minecraft_hosting_stack.py")
            (root / "spec/minecraft-hosting-stack-v1.json").write_text(text, encoding="utf-8")
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
             "Velocity must remain sole player-facing ingress"),
            ("velocity no longer player-facing",
             lambda d: d["ingress"].update(player_facing=False),
             "Velocity must remain sole player-facing ingress"),
            ("modern forwarding removed",
             lambda d: d["ingress"].update(capabilities=["velocity_identity_optional"]),
             "Velocity modern forwarding capability missing"),
            ("world made non-mutable",
             lambda d: d["world_storage"].update(mutable_runtime_mount=False),
             "World runtime mount must remain explicit"),
            ("world baked into image",
             lambda d: d["world_storage"].update(baked_into_image=True),
             "world payload/release authority crossed stack boundary"),
            ("docker socket given to world agent",
             lambda d: d["world_agent"].update(docker_socket=True),
             "world-agent must not receive Docker socket"),
            ("foundry missing forbidden exclusion",
             lambda d: d["foundry_boundary"].update(must_not_own=["world_release_policy"]),
             "Foundry exclusion missing:"),
            ("extra backend injected",
             lambda d: d["backends"].update(fabric={"proxy_adapter": "none"}),
             "backends must strictly be"),
            ("Foundry owns erased",
             lambda d: d["foundry_boundary"].update(owns=[]),
             "Foundry required ownership missing or malformed"),
            ("VanillaCord adapter drift",
             lambda d: d["backends"]["vanilla"].update(proxy_adapter="unknown"),
             "vanilla proxy adapter identity drift"),
            ("Paper adapter drift",
             lambda d: d["backends"]["paper"].update(proxy_adapter="unknown"),
             "Paper proxy adapter identity drift"),
            ("restore verb omitted",
             lambda d: d["world_agent"].update(verbs=[v for v in d["world_agent"]["verbs"] if v != "restore"]),
             "world-agent required mechanism verbs missing or malformed"),
            ("agent optional is string",
             lambda d: d["world_agent"].update(optional="false"),
             "world-agent optional must be Boolean true"),
            ("ingress capabilities type confusion",
             lambda d: d["ingress"].update(capabilities=["modern_forwarding", {"bad": "object"}]),
             "Velocity modern forwarding capability missing"),
            ("wrong authority",
             lambda d: d.update(authority="other"),
             "authority must be 'SupraCraft/mc-server-images#53'"),
        ]
        for label, change, expected in cases:
            with self.subTest(label=label):
                fixture = copy.deepcopy(SPEC)
                change(fixture)
                result = self.run_fixture(fixture)
                self.assertNotEqual(result.returncode, 0, label)
                self.assertIn(expected, result.stdout)

    def test_duplicate_json_keys_are_rejected(self):
        # Root duplicate
        raw_duplicate = (ROOT / "spec/minecraft-hosting-stack-v1.json").read_text(encoding="utf-8")
        # Inject duplicate root key
        raw_with_dup = raw_duplicate.replace('"schema_version": "1",', '"schema_version": "1",\n  "schema_version": "2",')
        result = self.run_raw_text(raw_with_dup)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate JSON key detected", result.stdout)

        # Ingress duplicate key
        raw_with_dup_ingress = raw_duplicate.replace('"service": "velocity",', '"service": "velocity",\n    "service": "paper",')
        result = self.run_raw_text(raw_with_dup_ingress)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate JSON key detected", result.stdout)


if __name__ == "__main__":
    unittest.main()