#!/usr/bin/env python3
"""Public W5 persistence/recovery oracle for Two Rivers."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_persistence_w5 import (
    RevisionStore,
    conserved_resource_total,
    deliver_in_transit_cargo,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    p = json.loads(args.projection.read_text("utf-8"))
    initial = p["case"]["initial_state"]
    operation = p["case"]["delivery_operation"]
    cargo_id = operation["cargo_id"]
    op_id = operation["operation_id"]

    initial_total = conserved_resource_total(initial, "grain")

    store = RevisionStore(initial)
    delivery_state = deliver_in_transit_cargo(store.state, cargo_id)
    delivery_commit = store.commit(
        int(operation["expected_revision"]),
        op_id,
        delivery_state,
    )
    after_delivery = store.snapshot()

    stale_state = copy.deepcopy(store.state)
    stale_state["history"].append({"kind": "stale_should_not_commit"})
    stale = store.commit(0, "stale:new-op", stale_state)

    restored = RevisionStore.restore(after_delivery)
    duplicate = restored.commit(
        0,
        op_id,
        delivery_state,
    )
    after_duplicate = restored.snapshot()

    replay = RevisionStore(initial)
    replay.commit(
        int(operation["expected_revision"]),
        op_id,
        deliver_in_transit_cargo(replay.state, cargo_id),
    )
    replay_snapshot = replay.snapshot()

    corrupted = copy.deepcopy(after_delivery)
    corrupted["state"]["settlements"]["kilnreach"]["grain"] = 999
    corruption_rejected = False
    try:
        RevisionStore.restore(corrupted)
    except ValueError:
        corruption_rejected = True

    continued_state = copy.deepcopy(restored.state)
    continued_state["history"].append({"kind": "post_restart_checkpoint"})
    continued = restored.commit(
        restored.revision,
        "checkpoint:post-restart",
        continued_state,
    )

    delivered_events = [
        row for row in after_duplicate["state"]["history"]
        if row.get("kind") == "cargo_delivered"
    ]

    checks = {
        "monotonic_revision": (
            delivery_commit.get("accepted") is True
            and delivery_commit.get("revision") == 1
            and continued.get("accepted") is True
            and continued.get("revision") == 2
        ),
        "stale_proposal_rejected": (
            stale.get("accepted") is False
            and stale.get("reason") == "stale_revision"
        ),
        "duplicate_operation_rejected": (
            duplicate.get("accepted") is False
            and duplicate.get("reason") == "duplicate_operation"
        ),
        "restart_no_duplicate_delivery": (
            after_duplicate["state"]["settlements"]["kilnreach"]["grain"] == 6
            and len(delivered_events) == 1
        ),
        "snapshot_integrity_checked": corruption_rejected,
        "snapshot_replay_equality": after_delivery == replay_snapshot,
        "resource_conservation": (
            conserved_resource_total(after_delivery["state"], "grain")
            == initial_total
        ),
        "world_scan_false": p["acceptance"]["world_scan"] is False,
    }
    passed = all(checks.values())

    result = {
        "schema": "supracraft.active4x-two-rivers-w5-rdte/v0.1",
        "source_authority": p["source_authority"],
        "source_checkpoint": p["source_checkpoint"],
        "checks": checks,
        "delivery_commit": delivery_commit,
        "stale_result": stale,
        "duplicate_retry_result": duplicate,
        "after_delivery_snapshot": after_delivery,
        "replay_snapshot_digest": replay_snapshot["snapshot_digest"],
        "post_restart_revision": continued.get("revision"),
        "deployment_stage": "D0_pure_deterministic_ci",
        "world_scan": False,
        "result": "PASS" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
