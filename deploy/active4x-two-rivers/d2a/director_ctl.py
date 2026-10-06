#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from active4x_persistence_w5 import RevisionStore

STATE_DIR = Path("/state")
STORE_PATH = STATE_DIR / "store.json"


def atomic_write(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", "utf-8")
    tmp.replace(path)


def load_store() -> RevisionStore:
    if not STORE_PATH.exists():
        raise RuntimeError("director state is not initialized")
    return RevisionStore.restore(json.loads(STORE_PATH.read_text("utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    apply = sub.add_parser("apply")
    apply.add_argument("--operation-id", required=True)
    args = ap.parse_args()

    store = load_store()

    if args.command == "show":
        print(
            json.dumps(
                {
                    "revision": store.revision,
                    "applied": sorted(store.applied),
                    "history": store.state.get("history", []),
                    "snapshot_digest": store.snapshot()["snapshot_digest"],
                },
                sort_keys=True,
            )
        )
        return 0

    next_state = copy.deepcopy(store.state)
    next_state.setdefault("history", []).append(
        {
            "operation_id": args.operation_id,
            "kind": "staging_operation",
        }
    )
    next_state["last_operation"] = args.operation_id
    result = store.commit(store.revision, args.operation_id, next_state)

    if result["accepted"]:
        atomic_write(STORE_PATH, store.snapshot())

    print(
        json.dumps(
            {
                **result,
                "history_count": len(store.state.get("history", [])),
                "snapshot_digest": store.snapshot()["snapshot_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
