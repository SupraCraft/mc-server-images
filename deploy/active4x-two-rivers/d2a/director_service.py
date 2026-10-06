#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

from active4x_persistence_w5 import RevisionStore

STATE_DIR = Path(os.environ.get("SUPRACRAFT_STATE_DIR", "/state"))
STORE_PATH = STATE_DIR / "store.json"
READY_PATH = STATE_DIR / "service-ready.json"


def atomic_write(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", "utf-8")
    tmp.replace(path)


def load_or_init() -> RevisionStore:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if STORE_PATH.exists():
        return RevisionStore.restore(json.loads(STORE_PATH.read_text("utf-8")))
    store = RevisionStore(
        {
            "world_id": "two_rivers",
            "deployment": "d2a_staging",
            "history": [],
        }
    )
    atomic_write(STORE_PATH, store.snapshot())
    return store


running = True


def stop(_signum, _frame):
    global running
    running = False


def main() -> int:
    store = load_or_init()
    atomic_write(
        READY_PATH,
        {
            "ready": True,
            "revision": store.revision,
            "snapshot_digest": store.snapshot()["snapshot_digest"],
        },
    )
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
