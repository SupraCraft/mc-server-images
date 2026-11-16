"""Public, offline exact Java 26.3 keeper-source custody guard contract.

This does not assert official-server cursor acquisition, chunk/entity scope, or
Lantern's private objective. The public runtime workflow separately checks that
the generated datapack boots and its existing acquisition/reissue loop works.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from probe_keeper_core_replenishment_26_3 import CORE, write_datapack  # noqa: E402


class KeeperCursorGuard(unittest.TestCase):
    def test_cursor_and_crafting_must_be_checked_before_reissuing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            result = write_datapack(Path(d))
            command = result["command"]
            required = (
                f"unless items entity @a[limit=1] inventory.* {CORE} ",
                f"unless items entity @a[limit=1] hotbar.* {CORE} ",
                f"unless items entity @a[limit=1] weapon.offhand {CORE} ",
                f"unless items entity @a[limit=1] player.cursor {CORE} ",
                f"unless items entity @a[limit=1] player.crafting.* {CORE} ",
                "unless items block 0 70 0 container.0 ",
                "run item replace block 0 70 0 container.0 ",
            )
            positions = [command.find(text) for text in required]
            self.assertTrue(all(i >= 0 for i in positions), positions)
            self.assertEqual(positions, sorted(positions))
            self.assertEqual(command.count("run item replace block"), 1)
            self.assertTrue(command.startswith("execute unless block"))

    def test_written_tick_matches_source_and_is_well_formed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            result = write_datapack(root)
            folder = root / "world" / "datapacks" / "supracraft_keeper_core_source"
            tick = folder / "data" / "supracraft_keeper_core_source" / "function" / "tick.mcfunction"
            self.assertEqual(tick.read_text("utf-8"), result["command"] + "\n")
            self.assertEqual(json.loads((folder / "pack.mcmeta").read_text("utf-8")),
                             result["metadata"])
            self.assertEqual(
                json.loads((folder / "data/minecraft/tags/function/tick.json").read_text("utf-8")),
                {"values": ["supracraft_keeper_core_source:tick"]},
            )

    def test_output_is_deterministic_without_mutating_repository(self) -> None:
        with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
            self.assertEqual(
                write_datapack(Path(left))["command"],
                write_datapack(Path(right))["command"],
            )


if __name__ == "__main__":
    unittest.main()
