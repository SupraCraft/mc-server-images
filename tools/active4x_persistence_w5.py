#!/usr/bin/env python3
"""Bounded persistence/CAS adapter for Two Rivers W5.

The store is deliberately small: one semantic authority, monotonic revisions,
compare-and-swap admission, idempotent operation IDs, and content-addressed
snapshots. Domain transitions remain deterministic functions over semantic
state rather than hidden database behavior.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _snapshot_core(
    revision: int,
    state: dict[str, Any],
    applied: set[str],
    operation_log: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "revision": int(revision),
        "state": copy.deepcopy(state),
        "applied": sorted(applied),
        "operation_log": copy.deepcopy(operation_log),
    }


class RevisionStore:
    """Single-authority optimistic revision store for bounded RDTE."""

    def __init__(self, initial: dict[str, Any]):
        self.revision = 0
        self.state = copy.deepcopy(initial)
        self.applied: set[str] = set()
        self.operation_log: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        core = _snapshot_core(
            self.revision,
            self.state,
            self.applied,
            self.operation_log,
        )
        return {
            **core,
            "snapshot_digest": _digest(core),
        }

    def commit(
        self,
        expected_revision: int,
        op_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        # Idempotence takes precedence over stale-revision reporting: a retry of
        # an operation already durably committed must never be re-applied.
        if op_id in self.applied:
            return {
                "accepted": False,
                "reason": "duplicate_operation",
                "revision": self.revision,
                "operation_id": op_id,
            }

        if expected_revision != self.revision:
            return {
                "accepted": False,
                "reason": "stale_revision",
                "revision": self.revision,
                "expected_revision": expected_revision,
                "operation_id": op_id,
            }

        before = self.revision
        next_state = copy.deepcopy(state)
        next_digest = _digest(next_state)

        self.state = next_state
        self.applied.add(op_id)
        self.revision += 1
        self.operation_log.append(
            {
                "operation_id": op_id,
                "from_revision": before,
                "to_revision": self.revision,
                "state_digest": next_digest,
            }
        )
        return {
            "accepted": True,
            "revision": self.revision,
            "operation_id": op_id,
            "state_digest": next_digest,
        }

    @classmethod
    def restore(cls, snapshot: dict[str, Any]) -> "RevisionStore":
        core = {
            "revision": int(snapshot["revision"]),
            "state": copy.deepcopy(snapshot["state"]),
            "applied": list(snapshot.get("applied", [])),
            "operation_log": copy.deepcopy(snapshot.get("operation_log", [])),
        }
        expected = snapshot.get("snapshot_digest")
        actual = _digest(core)
        if expected != actual:
            raise ValueError("snapshot digest mismatch")

        obj = cls(core["state"])
        obj.revision = core["revision"]
        obj.applied = set(core["applied"])
        obj.operation_log = core["operation_log"]
        return obj


def deliver_in_transit_cargo(
    state: dict[str, Any],
    cargo_id: str,
) -> dict[str, Any]:
    """Return the deterministic next state for one in-transit cargo delivery."""

    next_state = copy.deepcopy(state)
    cargo = next_state.get("cargo", {}).get(cargo_id)
    if not cargo:
        raise ValueError(f"unknown cargo: {cargo_id}")
    if cargo.get("status") != "in_transit":
        raise ValueError(
            f"cargo must be in_transit before delivery: {cargo_id} "
            f"status={cargo.get('status')}"
        )

    destination = cargo["destination"]
    resource = cargo["resource"]
    amount = int(cargo["amount"])
    if amount <= 0:
        raise ValueError("cargo amount must be positive")

    settlements = next_state.get("settlements", {})
    if destination not in settlements:
        raise ValueError(f"unknown destination settlement: {destination}")

    destination_stock = settlements[destination]
    destination_stock[resource] = int(destination_stock.get(resource, 0)) + amount
    cargo["status"] = "delivered"

    history = next_state.setdefault("history", [])
    history.append(
        {
            "kind": "cargo_delivered",
            "cargo_id": cargo_id,
            "destination": destination,
            "resource": resource,
            "amount": amount,
        }
    )
    return next_state


def conserved_resource_total(
    state: dict[str, Any],
    resource: str,
) -> int:
    """Count settlement stock plus still-in-transit cargo for one resource."""

    total = 0
    for stock in state.get("settlements", {}).values():
        total += int(stock.get(resource, 0))
    for cargo in state.get("cargo", {}).values():
        if (
            cargo.get("resource") == resource
            and cargo.get("status") == "in_transit"
        ):
            total += int(cargo.get("amount", 0))
    return total
