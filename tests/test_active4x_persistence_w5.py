import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_persistence_w5 import (
    RevisionStore,
    conserved_resource_total,
    deliver_in_transit_cargo,
)

PROJECTION = ROOT / "probes/active4x/two-rivers-w5-persistence-v0.1.json"


class Active4XPersistenceW5Tests(unittest.TestCase):
    def load(self):
        return json.loads(PROJECTION.read_text(encoding="utf-8"))

    def test_delivery_commit_is_monotonic_and_conserved(self):
        projection = self.load()
        initial = projection["case"]["initial_state"]
        cargo_id = projection["case"]["delivery_operation"]["cargo_id"]
        store = RevisionStore(initial)
        before_total = conserved_resource_total(store.state, "grain")
        next_state = deliver_in_transit_cargo(store.state, cargo_id)
        result = store.commit(0, f"deliver:{cargo_id}", next_state)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["revision"], 1)
        self.assertEqual(conserved_resource_total(store.state, "grain"), before_total)
        self.assertEqual(store.state["settlements"]["kilnreach"]["grain"], 6)

    def test_stale_proposal_fails_closed(self):
        projection = self.load()
        initial = projection["case"]["initial_state"]
        cargo_id = projection["case"]["delivery_operation"]["cargo_id"]
        store = RevisionStore(initial)
        store.commit(0, f"deliver:{cargo_id}", deliver_in_transit_cargo(store.state, cargo_id))
        stale_state = copy.deepcopy(store.state)
        stale_state["history"].append({"kind": "stale_should_not_commit"})
        result = store.commit(0, "new-op-on-old-revision", stale_state)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"], "stale_revision")
        self.assertNotIn(
            {"kind": "stale_should_not_commit"},
            store.state["history"],
        )

    def test_restart_duplicate_delivery_is_idempotently_rejected(self):
        projection = self.load()
        initial = projection["case"]["initial_state"]
        cargo_id = projection["case"]["delivery_operation"]["cargo_id"]
        op_id = f"deliver:{cargo_id}"

        store = RevisionStore(initial)
        committed = deliver_in_transit_cargo(store.state, cargo_id)
        self.assertTrue(store.commit(0, op_id, committed)["accepted"])
        snapshot = store.snapshot()

        restored = RevisionStore.restore(snapshot)
        retry = restored.commit(
            0,
            op_id,
            committed,
        )
        self.assertFalse(retry["accepted"])
        self.assertEqual(retry["reason"], "duplicate_operation")
        self.assertEqual(restored.state["settlements"]["kilnreach"]["grain"], 6)
        delivered = [
            row for row in restored.state["history"]
            if row.get("kind") == "cargo_delivered"
        ]
        self.assertEqual(len(delivered), 1)

    def test_snapshot_integrity_fails_closed(self):
        projection = self.load()
        store = RevisionStore(projection["case"]["initial_state"])
        snapshot = store.snapshot()
        snapshot["state"]["settlements"]["kilnreach"]["grain"] = 999
        with self.assertRaises(ValueError):
            RevisionStore.restore(snapshot)

    def test_replay_from_initial_matches_snapshot(self):
        projection = self.load()
        initial = projection["case"]["initial_state"]
        cargo_id = projection["case"]["delivery_operation"]["cargo_id"]
        op_id = f"deliver:{cargo_id}"

        first = RevisionStore(initial)
        first.commit(0, op_id, deliver_in_transit_cargo(first.state, cargo_id))
        expected = first.snapshot()

        replay = RevisionStore(initial)
        replay.commit(0, op_id, deliver_in_transit_cargo(replay.state, cargo_id))
        actual = replay.snapshot()

        self.assertEqual(expected, actual)

    def test_revision_continues_after_restore(self):
        projection = self.load()
        initial = projection["case"]["initial_state"]
        cargo_id = projection["case"]["delivery_operation"]["cargo_id"]

        store = RevisionStore(initial)
        store.commit(0, f"deliver:{cargo_id}", deliver_in_transit_cargo(store.state, cargo_id))
        restored = RevisionStore.restore(store.snapshot())

        next_state = copy.deepcopy(restored.state)
        next_state["history"].append({"kind": "post_restart_checkpoint"})
        result = restored.commit(1, "checkpoint:post-restart", next_state)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["revision"], 2)


if __name__ == "__main__":
    unittest.main()
