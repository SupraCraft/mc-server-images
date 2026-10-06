#!/usr/bin/env python3
"""Instrumentation for Two Rivers W6 accelerated soak qualification."""

from __future__ import annotations

from typing import Any

from active4x_sim import Active4XSimulation


class SoakSimulation(Active4XSimulation):
    """Active4XSimulation with bounded runtime instrumentation."""

    def __init__(self, scenario: dict[str, Any], intervention: str = "none") -> None:
        self.queue_high_water = 0
        self.max_in_transit_cargo = 0
        self.max_open_contracts = 0
        self.negative_stock_observed = False
        self.relation_out_of_bounds = False
        self.samples: list[dict[str, Any]] = []
        super().__init__(scenario, intervention)
        self._sample("initial")

    def _schedule(self, due: int, kind: str, owner: str, payload: dict[str, Any]) -> None:
        super()._schedule(due, kind, owner, payload)
        self.queue_high_water = max(self.queue_high_water, len(self.queue))

    def _sample(self, phase: str) -> None:
        in_transit = sum(
            1 for row in self.cargo.values()
            if row.get("status") == "in_transit"
        )
        open_contracts = sum(
            1 for row in self.contracts.values()
            if row.get("status") == "in_transit"
        )

        negative = False
        for settlement in self.settlements.values():
            if any(int(value) < 0 for value in settlement["stock"].values()):
                negative = True
        if any(int(value) < 0 for value in self.player_stock.values()):
            negative = True

        relation_bad = False
        trusts = []
        for relation in self.relations.values():
            trust = int(relation.get("trust", 0))
            trusts.append(trust)
            if trust < -100 or trust > 100:
                relation_bad = True

        self.max_in_transit_cargo = max(self.max_in_transit_cargo, in_transit)
        self.max_open_contracts = max(self.max_open_contracts, open_contracts)
        self.negative_stock_observed = self.negative_stock_observed or negative
        self.relation_out_of_bounds = self.relation_out_of_bounds or relation_bad

        self.samples.append(
            {
                "time": self.time,
                "phase": phase,
                "queue_depth": len(self.queue),
                "in_transit_cargo": in_transit,
                "open_contracts": open_contracts,
                "trust_values": trusts,
            }
        )

    def _dispatch(self, event) -> None:
        super()._dispatch(event)
        self._sample(event.kind)

    def soak_result(self, horizon: int) -> dict[str, Any]:
        result = self.run(horizon)
        kilnreach_decisions = sum(
            1
            for row in result["decisions"]
            if row["settlement_id"] == "kilnreach"
        )
        contract_count = len(result["state"]["contracts"])
        statuses = {
            row.get("status")
            for row in result["state"]["contracts"].values()
        }

        return {
            "result": result,
            "metrics": {
                "queue_high_water": self.queue_high_water,
                "max_in_transit_cargo": self.max_in_transit_cargo,
                "max_open_contracts": self.max_open_contracts,
                "negative_stock_observed": self.negative_stock_observed,
                "relation_out_of_bounds": self.relation_out_of_bounds,
                "decision_count": len(result["decisions"]),
                "kilnreach_decision_count": kilnreach_decisions,
                "contract_count": contract_count,
                "contract_statuses": sorted(status for status in statuses if status),
                "event_count": len(result["ledger"]),
                "sample_count": len(self.samples),
            },
        }


def evaluate_soak_bounds(
    soak: dict[str, Any],
    bounds: dict[str, Any],
) -> dict[str, bool]:
    result = soak["result"]
    metrics = soak["metrics"]

    contract_rate_ok = (
        metrics["contract_count"] <= metrics["kilnreach_decision_count"]
    )
    contract_states_ok = set(metrics["contract_statuses"]).issubset(
        {"in_transit", "fulfilled", "breached"}
    )

    return {
        "resource_balance": bool(result["balance"]["passed"]),
        "queue_bounded": (
            int(metrics["queue_high_water"])
            <= int(bounds["max_queue_high_water"])
        ),
        "actor_demand_bounded": (
            int(metrics["max_in_transit_cargo"])
            <= int(bounds["max_promoted_actor_demand"])
        ),
        "open_contracts_bounded": (
            int(metrics["max_open_contracts"])
            <= int(bounds["max_open_contracts"])
        ),
        "no_negative_stocks": not bool(metrics["negative_stock_observed"]),
        "relations_bounded": not bool(metrics["relation_out_of_bounds"]),
        "trade_rate_bounded_by_decisions": contract_rate_ok,
        "contract_states_valid": contract_states_ok,
        "world_scan_false": result["world_scan"] is False,
    }
