"""Offline, real-Git tests of stock-client HIL receipt publication safety.

Synthetic receipt content in these tests is never represented as player/HIL evidence.
No network, Minecraft runtime, or world mutation is used.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_active4x_two_rivers_d3_hil import HilError, publish_receipt

BRANCH = "feat/named-place-visual-qualification-v1"


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    return proc.stdout.strip()


def configure(repo: Path) -> None:
    git(repo, "config", "user.name", "Two Rivers CI Fixture")
    git(repo, "config", "user.email", "test@example.invalid")


class HilPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.remote = base / "remote.git"
        self.repo = base / "work"
        git(base, "init", "--bare", str(self.remote))
        git(base, "clone", str(self.remote), str(self.repo))
        configure(self.repo)
        git(self.repo, "switch", "-c", BRANCH)
        (self.repo / "fixture.txt").write_text("initial\n", encoding="utf-8")
        git(self.repo, "add", "fixture.txt")
        git(self.repo, "commit", "-m", "initial fixture")
        git(self.repo, "push", "-u", "origin", BRANCH)
        self.source_head = git(self.repo, "rev-parse", "HEAD")
        self.local_output = self.repo / "probes/active4x/two-rivers-d3-hil-result.local.json"
        self.local_output.parent.mkdir(parents=True)
        self.local_output.write_text('{"fixture":"not real HIL"}\n', encoding="utf-8")
        self.fixture = {"fixture_only": True, "not_human_evidence": True}

    def test_clean_source_publishes_one_descendant_commit(self):
        published = publish_receipt(
            self.repo, self.local_output, self.fixture, self.source_head)
        self.assertNotEqual(published, self.source_head)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD^"), self.source_head)
        self.assertEqual(git(self.repo, "rev-parse", f"origin/{BRANCH}"), published)
        receipt = json.loads((self.repo / "probes/active4x/two-rivers-d3-hil-result.json")
                             .read_text(encoding="utf-8"))
        self.assertTrue(receipt["fixture_only"])

    def test_remote_move_during_play_refuses_rebase_or_publication(self):
        other = Path(self.temp.name) / "other"
        git(Path(self.temp.name), "clone", str(self.remote), str(other))
        configure(other)
        git(other, "switch", "-c", BRANCH, "--track", f"origin/{BRANCH}")
        (other / "fixture.txt").write_text("concurrent update\n", encoding="utf-8")
        git(other, "commit", "-am", "concurrent update")
        git(other, "push", "origin", BRANCH)
        with self.assertRaisesRegex(HilError, "Remote HIL branch advanced"):
            publish_receipt(self.repo, self.local_output, self.fixture, self.source_head)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.source_head)
        self.assertFalse(
            (self.repo / "probes/active4x/two-rivers-d3-hil-result.json").exists())
        self.assertTrue(self.local_output.exists())

    def test_local_source_change_during_play_is_rejected(self):
        (self.repo / "fixture.txt").write_text("changed during play\n", encoding="utf-8")
        git(self.repo, "commit", "-am", "changed during play")
        with self.assertRaisesRegex(HilError, "source revision changed"):
            publish_receipt(self.repo, self.local_output, self.fixture, self.source_head)
        self.assertFalse(
            (self.repo / "probes/active4x/two-rivers-d3-hil-result.json").exists())
        self.assertTrue(self.local_output.exists())


if __name__ == "__main__":
    unittest.main()
