#!/usr/bin/env python3
"""Two Rivers W1 trade/route-disruption extension.

This bounded RDTE layer extends the W0 kernel with one additional primitive:
disruption of one in-transit cargo obligation. The disrupted quantity moves to an
explicit loss sink, the contract is breached, the destination remembers the
route disruption, and a later autonomous decision may respond.
"""

from __future__ import annotations

from typing import Any

from active4x_sim import Active4XSimulation


class TradeDisruptionSimulation(Active4XSimulation):
    def _handle_intervention(self, event) -> None:
        payload = event.payload
        if payload.get("kind") != "disrupt_first_cargo":
            return super()._handle_intervention(event)

        matches = [
            row
            for row in self.cargo.values()
            if row.get("status") == "in_transit"
            and row.get("dest") == payload["dest_settlement"]
            and row.get("resource") == payload["resource"]
        ]
        matches.sort(key=lambda row: row["cargo_id"])
        if not matches:
            self._append_ledger(
                "cargo_disruption_missed",
                "player",
                {
                    "dest": payload["dest_settlement"],
                    "resource": payload["resource"],
                },
            )
            return

        cargo = matches[0]
        cargo["status"] = "disrupted"
        cargo["disrupted_at"] = self.time
        self.sinks["lost"][cargo["resource"]] += int(cargo["amount"])

        contract = self.contracts[cargo["contract_id"]]
        contract["status"] = "breached"
        contract["breached_at"] = self.time
        contract["breach_reason"] = "cargo_disrupted"

        dest = self.settlements[cargo["dest"]]
        if "route_disrupted" not in dest["memories"]:
            dest["memories"].append("route_disrupted")

        source_civ = self.settlements[cargo["source"]]["civilization_id"]
        dest_civ = dest["civilization_id"]
        relation = self._relation(source_civ, dest_civ)
        trust_delta = int(payload.get("trust_delta", -4))
        relation["trust"] = int(relation.get("trust", 0)) + trust_delta

        self._append_ledger(
            "cargo_disrupted",
            "player",
            {
                "cargo_id": cargo["cargo_id"],
                "contract_id": cargo["contract_id"],
                "source": cargo["source"],
                "dest": cargo["dest"],
                "resource": cargo["resource"],
                "amount": cargo["amount"],
                "trust_delta": trust_delta,
            },
        )


    def _candidate_decisions(self, settlement_id: str):
        candidates = super()._candidate_decisions(settlement_id)
        settlement = self.settlements[settlement_id]
        if "route_disrupted" in settlement["memories"]:
            for row in candidates:
                if row["action"] == "secure_route":
                    # W1 falsifies that a consequential route loss can outrank
                    # immediately repeating the same exposed trade path.
                    row["score"] = max(int(row["score"]), 250)
                    row["reasons"].append("route loss requires mitigation before retry")
        return candidates

    def _handle_cargo_arrival(self, event) -> None:
        cargo = self.cargo[event.payload["cargo_id"]]
        if cargo.get("status") == "disrupted":
            self._append_ledger(
                "cargo_arrival_ignored",
                cargo["cargo_id"],
                {"reason": "status=disrupted"},
            )
            return
        super()._handle_cargo_arrival(event)


def scenario_with_trade_disruption(
    base_scenario: dict[str, Any],
    overlay: dict[str, Any],
) -> dict[str, Any]:
    scenario = dict(base_scenario)
    scenario["interventions"] = {
        key: [dict(row) for row in rows]
        for key, rows in base_scenario.get("interventions", {}).items()
    }
    intervention = overlay["intervention"]
    scenario["interventions"][intervention["id"]] = [
        dict(row) for row in intervention["events"]
    ]
    return scenario
