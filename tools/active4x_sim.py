#!/usr/bin/env python3
"""Small deterministic active-4X simulation kernel for bounded RDTE.

The kernel intentionally implements only the primitives earned by the Two Rivers
vertical slice:
- discrete event scheduling;
- stock/flow accounting;
- explicit barter contracts and in-transit cargo;
- transparent bounded utility decisions + DecisionReceipts;
- persistent event ledger;
- player intervention injection points.

It is not a second Minecraft simulation. Exact local embodiment remains a
separate promotion surface.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(order=True)
class ScheduledEvent:
    due: int
    sequence: int
    kind: str
    owner: str
    payload: dict[str, Any]


class Active4XSimulation:
    def __init__(self, scenario: dict[str, Any], intervention: str = "none") -> None:
        if scenario.get("format") != "supracraft/active4x-scenario/v0.1":
            raise ValueError("unsupported active-4X scenario format")
        if scenario.get("acceptance", {}).get("world_scan") is not False:
            raise ValueError("active-4X RDTE forbids world scanning")
        if intervention not in scenario.get("interventions", {}):
            raise ValueError(f"unknown intervention: {intervention}")

        self.scenario = copy.deepcopy(scenario)
        self.intervention = intervention
        self.time = 0
        self.revision = 0
        self.sequence = 0
        self.queue: list[ScheduledEvent] = []
        self.ledger: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.contracts: dict[str, dict[str, Any]] = {}
        self.cargo: dict[str, dict[str, Any]] = {}
        self.produced: dict[str, int] = defaultdict(int)
        self.sinks: dict[str, dict[str, int]] = {
            "consumed": defaultdict(int),
            "embedded": defaultdict(int),
            "lost": defaultdict(int),
        }

        self.civilizations = {
            row["id"]: copy.deepcopy(row)
            for row in scenario.get("civilizations", [])
        }
        self.settlements = {
            row["id"]: {
                **copy.deepcopy(row),
                "stock": copy.deepcopy(row.get("stock", {})),
                "capabilities": list(row.get("capabilities", [])),
                "memories": [],
            }
            for row in scenario.get("settlements", [])
        }
        self.player_stock = copy.deepcopy(scenario.get("player_stock", {}))
        self.sites = {
            row["id"]: copy.deepcopy(row)
            for row in scenario.get("contested_sites", [])
        }
        self.relations: dict[str, dict[str, Any]] = {}
        for row in scenario.get("relations", []):
            key = self._relation_key(row["a"], row["b"])
            self.relations[key] = copy.deepcopy(row)

        self.initial_totals = self._current_resource_totals(include_cargo=False)
        self._schedule_initial_events()

    @staticmethod
    def _relation_key(a: str, b: str) -> str:
        return "|".join(sorted((a, b)))

    def _relation(self, civ_a: str, civ_b: str) -> dict[str, Any]:
        key = self._relation_key(civ_a, civ_b)
        if key not in self.relations:
            raise ValueError(f"missing relationship: {key}")
        return self.relations[key]

    def _other_settlement(self, settlement_id: str) -> dict[str, Any]:
        others = [row for sid, row in self.settlements.items() if sid != settlement_id]
        if len(others) != 1:
            raise ValueError("bounded Two Rivers RDTE expects exactly two settlements")
        return others[0]

    def _schedule(self, due: int, kind: str, owner: str, payload: dict[str, Any]) -> None:
        self.sequence += 1
        heapq.heappush(
            self.queue,
            ScheduledEvent(int(due), self.sequence, kind, owner, copy.deepcopy(payload)),
        )

    def _schedule_initial_events(self) -> None:
        for settlement in self.settlements.values():
            sid = settlement["id"]
            for row in settlement.get("production", []):
                self._schedule(
                    int(row["every"]),
                    "produce",
                    sid,
                    {**row, "repeat_every": int(row["every"])},
                )
            for row in settlement.get("consumption", []):
                self._schedule(
                    int(row["every"]),
                    "consume",
                    sid,
                    {**row, "repeat_every": int(row["every"])},
                )
            self._schedule(
                int(settlement["decision_start"]),
                "decision_review",
                sid,
                {"repeat_every": int(settlement["decision_every"])},
            )

        for row in self.scenario["interventions"][self.intervention]:
            self._schedule(int(row["time"]), "intervention", "player", row)

    def _append_ledger(self, kind: str, owner: str, payload: dict[str, Any]) -> None:
        self.revision += 1
        self.ledger.append(
            {
                "event_id": f"evt-{len(self.ledger)+1:05d}",
                "time": self.time,
                "revision": self.revision,
                "kind": kind,
                "owner": owner,
                "payload": copy.deepcopy(payload),
            }
        )

    def _stock(self, holder: str) -> dict[str, int]:
        if holder == "player":
            return self.player_stock
        if holder in self.settlements:
            return self.settlements[holder]["stock"]
        raise ValueError(f"unknown stock holder: {holder}")

    def _remove_stock(self, holder: str, resource: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        stock = self._stock(holder)
        available = int(stock.get(resource, 0))
        if available < amount:
            raise ValueError(
                f"insufficient {resource} at {holder}: need {amount}, have {available}"
            )
        stock[resource] = available - amount

    def _add_stock(self, holder: str, resource: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        stock = self._stock(holder)
        stock[resource] = int(stock.get(resource, 0)) + amount

    def _transfer(self, source: str, dest: str, resource: str, amount: int) -> None:
        self._remove_stock(source, resource, amount)
        self._add_stock(dest, resource, amount)

    def _current_resource_totals(self, include_cargo: bool = True) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for settlement in self.settlements.values():
            for resource, amount in settlement["stock"].items():
                totals[resource] += int(amount)
        for resource, amount in self.player_stock.items():
            totals[resource] += int(amount)
        if include_cargo:
            for cargo in self.cargo.values():
                if cargo.get("status") == "in_transit":
                    totals[cargo["resource"]] += int(cargo["amount"])
        return dict(totals)

    def _balance_report(self) -> dict[str, Any]:
        current = self._current_resource_totals(include_cargo=True)
        resources = set(self.initial_totals) | set(current) | set(self.produced)
        for sink in self.sinks.values():
            resources |= set(sink)

        rows = {}
        passed = True
        for resource in sorted(resources):
            left = int(current.get(resource, 0))
            left += sum(int(sink.get(resource, 0)) for sink in self.sinks.values())
            right = int(self.initial_totals.get(resource, 0)) + int(
                self.produced.get(resource, 0)
            )
            ok = left == right
            passed = passed and ok
            rows[resource] = {
                "initial": int(self.initial_totals.get(resource, 0)),
                "produced": int(self.produced.get(resource, 0)),
                "current_plus_in_transit": int(current.get(resource, 0)),
                "consumed": int(self.sinks["consumed"].get(resource, 0)),
                "embedded": int(self.sinks["embedded"].get(resource, 0)),
                "lost": int(self.sinks["lost"].get(resource, 0)),
                "balanced": ok,
            }
        return {"passed": passed, "resources": rows}

    def _handle_produce(self, event: ScheduledEvent) -> None:
        resource = event.payload["resource"]
        amount = int(event.payload["amount"])
        self._add_stock(event.owner, resource, amount)
        self.produced[resource] += amount
        self._append_ledger(
            "production_completed",
            event.owner,
            {"resource": resource, "amount": amount, "recipe": event.payload["id"]},
        )
        self._schedule(
            self.time + int(event.payload["repeat_every"]),
            "produce",
            event.owner,
            event.payload,
        )

    def _handle_consume(self, event: ScheduledEvent) -> None:
        resource = event.payload["resource"]
        requested = int(event.payload["amount"])
        stock = self._stock(event.owner)
        available = int(stock.get(resource, 0))
        actual = min(available, requested)
        if actual:
            self._remove_stock(event.owner, resource, actual)
            self.sinks["consumed"][resource] += actual

        settlement = self.settlements[event.owner]
        shortage = actual < requested
        if shortage and "food_shortage" not in settlement["memories"]:
            settlement["memories"].append("food_shortage")
        elif not shortage and resource == "grain":
            settlement["memories"] = [
                x for x in settlement["memories"] if x != "food_shortage"
            ]

        self._append_ledger(
            "consumption",
            event.owner,
            {
                "resource": resource,
                "requested": requested,
                "actual": actual,
                "shortage": shortage,
                "recipe": event.payload["id"],
            },
        )
        self._schedule(
            self.time + int(event.payload["repeat_every"]),
            "consume",
            event.owner,
            event.payload,
        )

    def _handle_intervention(self, event: ScheduledEvent) -> None:
        payload = event.payload
        if payload["kind"] == "player_transfer":
            self._transfer(
                "player",
                payload["to_settlement"],
                payload["resource"],
                int(payload["amount"]),
            )
            self._append_ledger(
                "player_transfer",
                "player",
                {
                    "to": payload["to_settlement"],
                    "resource": payload["resource"],
                    "amount": int(payload["amount"]),
                },
            )
        elif payload["kind"] == "route_disruption":
            settlement = self.settlements[payload["settlement_id"]]
            if "route_disrupted" not in settlement["memories"]:
                settlement["memories"].append("route_disrupted")
            self._append_ledger(
                "route_disruption",
                "player",
                {
                    "settlement_id": payload["settlement_id"],
                    "severity": int(payload.get("severity", 1)),
                },
            )
        else:
            raise ValueError(f"unsupported intervention kind: {payload['kind']}")

    def _candidate_decisions(self, settlement_id: str) -> list[dict[str, Any]]:
        settlement = self.settlements[settlement_id]
        civ = self.civilizations[settlement["civilization_id"]]
        other = self._other_settlement(settlement_id)
        other_civ = self.civilizations[other["civilization_id"]]
        relation = self._relation(civ["id"], other_civ["id"])
        prefs = civ.get("preferences", {})
        stock = settlement["stock"]

        candidates: list[dict[str, Any]] = []

        def add(action: str, score: int, feasible: bool, reasons: list[str]) -> None:
            candidates.append(
                {
                    "action": action,
                    "score": int(score),
                    "feasible": bool(feasible),
                    "reasons": list(reasons),
                }
            )

        route_disrupted = "route_disrupted" in settlement["memories"]
        add(
            "secure_route",
            120 + int(prefs.get("security", 0) / 10),
            route_disrupted,
            ["recent route disruption"] if route_disrupted else ["no route disruption"],
        )

        low_food = int(stock.get("grain", 0)) < 6
        counterpart_surplus = int(other["stock"].get("grain", 0)) >= 8
        payment_available = int(stock.get("bricks", 0)) >= 2
        trade_ok = bool(relation.get("trade_access")) and not bool(relation.get("hostility"))
        add(
            "seek_food_trade",
            100
            + max(0, 6 - int(stock.get("grain", 0))) * 10
            + int(prefs.get("trade", 0) / 10),
            low_food and counterpart_surplus and payment_available and trade_ok,
            [
                f"grain={int(stock.get('grain', 0))}",
                f"counterpart_grain={int(other['stock'].get('grain', 0))}",
                f"bricks={int(stock.get('bricks', 0))}",
                f"trade_access={trade_ok}",
            ],
        )

        has_granary = "grain_storage" in settlement["capabilities"]
        add(
            "build_granary",
            100 + int(prefs.get("expansion", 0) / 10),
            (
                settlement_id == "stoneford"
                and not has_granary
                and int(stock.get("bricks", 0)) >= 4
                and int(stock.get("grain", 0)) >= 8
            ),
            [
                f"bricks={int(stock.get('bricks', 0))}",
                f"grain={int(stock.get('grain', 0))}",
                f"already_has_granary={has_granary}",
            ],
        )

        site = self.sites["iron_ford"]
        add(
            "claim_iron_ford",
            int(site["strategic_value"]) + 20 + int(prefs.get("resource_control", 0) / 10),
            site.get("claimed_by") is None and int(stock.get("grain", 0)) >= 5,
            [
                f"claimed_by={site.get('claimed_by')}",
                f"grain={int(stock.get('grain', 0))}",
            ],
        )

        has_extension = "brickworks_extension" in settlement["capabilities"]
        add(
            "expand_brickworks",
            70 + int(prefs.get("expansion", 0) / 10),
            (
                settlement_id == "kilnreach"
                and not has_extension
                and int(stock.get("bricks", 0)) >= 6
                and int(stock.get("grain", 0)) >= 8
            ),
            [
                f"bricks={int(stock.get('bricks', 0))}",
                f"grain={int(stock.get('grain', 0))}",
                f"already_extended={has_extension}",
            ],
        )

        add("idle", 0, True, ["fallback"])
        return candidates

    def _choose_decision(self, settlement_id: str) -> dict[str, Any]:
        candidates = self._candidate_decisions(settlement_id)
        feasible = [row for row in candidates if row["feasible"]]
        feasible.sort(key=lambda row: (-row["score"], row["action"]))
        selected = feasible[0]

        receipt = {
            "schema": "supracraft.decision-receipt/v0.1",
            "decision_id": f"decision-{len(self.decisions)+1:04d}",
            "time": self.time,
            "revision_observed": self.revision,
            "settlement_id": settlement_id,
            "civilization_id": self.settlements[settlement_id]["civilization_id"],
            "selected": copy.deepcopy(selected),
            "candidates": copy.deepcopy(candidates),
        }
        self.decisions.append(receipt)
        return receipt

    def _new_cargo(
        self,
        contract_id: str,
        source: str,
        dest: str,
        resource: str,
        amount: int,
    ) -> str:
        cargo_id = f"{contract_id}.cargo{len(self.cargo)+1:02d}"
        self._remove_stock(source, resource, amount)
        self.cargo[cargo_id] = {
            "cargo_id": cargo_id,
            "contract_id": contract_id,
            "source": source,
            "dest": dest,
            "resource": resource,
            "amount": amount,
            "status": "in_transit",
            "departed_at": self.time,
        }
        self._schedule(
            self.time + 3,
            "cargo_arrival",
            cargo_id,
            {"cargo_id": cargo_id},
        )
        return cargo_id

    def _create_food_trade(self, needy_id: str) -> str:
        needy = self.settlements[needy_id]
        supplier = self._other_settlement(needy_id)
        contract_id = f"contract-{len(self.contracts)+1:03d}"
        contract = {
            "schema": "supracraft.obligation-contract/v0.1",
            "contract_id": contract_id,
            "created_at": self.time,
            "parties": [needy["civilization_id"], supplier["civilization_id"]],
            "status": "in_transit",
            "terms": [
                {
                    "from": supplier["id"],
                    "to": needy["id"],
                    "resource": "grain",
                    "amount": 4,
                },
                {
                    "from": needy["id"],
                    "to": supplier["id"],
                    "resource": "bricks",
                    "amount": 2,
                },
            ],
            "cargo_ids": [],
        }
        for term in contract["terms"]:
            cargo_id = self._new_cargo(
                contract_id,
                term["from"],
                term["to"],
                term["resource"],
                int(term["amount"]),
            )
            contract["cargo_ids"].append(cargo_id)
        self.contracts[contract_id] = contract
        self._append_ledger(
            "trade_contract_created",
            needy_id,
            {"contract_id": contract_id, "terms": copy.deepcopy(contract["terms"])},
        )
        return contract_id

    def _apply_decision(self, receipt: dict[str, Any]) -> None:
        sid = receipt["settlement_id"]
        settlement = self.settlements[sid]
        action = receipt["selected"]["action"]
        effect: dict[str, Any] = {"action": action}

        if action == "secure_route":
            if "route_guard" not in settlement["capabilities"]:
                settlement["capabilities"].append("route_guard")
            settlement["memories"] = [
                x for x in settlement["memories"] if x != "route_disrupted"
            ]
            effect["capability_added"] = "route_guard"

        elif action == "seek_food_trade":
            active = [
                row
                for row in self.contracts.values()
                if row["status"] == "in_transit"
                and settlement["civilization_id"] in row["parties"]
            ]
            if active:
                effect["contract_id"] = active[0]["contract_id"]
                effect["reused_active_contract"] = True
            else:
                effect["contract_id"] = self._create_food_trade(sid)
                effect["reused_active_contract"] = False

        elif action == "build_granary":
            self._remove_stock(sid, "bricks", 4)
            self.sinks["embedded"]["bricks"] += 4
            settlement["capabilities"].append("grain_storage")
            effect.update({"embedded_bricks": 4, "capability_added": "grain_storage"})

        elif action == "claim_iron_ford":
            site = self.sites["iron_ford"]
            if site.get("claimed_by") is not None:
                raise RuntimeError("claim candidate became stale")
            site["claimed_by"] = settlement["civilization_id"]
            effect["site_id"] = "iron_ford"
            effect["claimed_by"] = settlement["civilization_id"]

        elif action == "expand_brickworks":
            self._remove_stock(sid, "bricks", 4)
            self.sinks["embedded"]["bricks"] += 4
            settlement["capabilities"].append("brickworks_extension")
            effect.update(
                {"embedded_bricks": 4, "capability_added": "brickworks_extension"}
            )

        elif action == "idle":
            effect["state_change"] = False

        else:
            raise ValueError(f"unsupported decision action: {action}")

        receipt["effect"] = copy.deepcopy(effect)
        receipt["revision_committed_from"] = self.revision
        self._append_ledger("decision_committed", sid, effect)
        receipt["revision_after_commit"] = self.revision

    def _handle_decision(self, event: ScheduledEvent) -> None:
        receipt = self._choose_decision(event.owner)
        self._apply_decision(receipt)
        self._schedule(
            self.time + int(event.payload["repeat_every"]),
            "decision_review",
            event.owner,
            event.payload,
        )

    def _handle_cargo_arrival(self, event: ScheduledEvent) -> None:
        cargo_id = event.payload["cargo_id"]
        cargo = self.cargo[cargo_id]
        if cargo["status"] != "in_transit":
            self._append_ledger(
                "cargo_arrival_ignored",
                cargo_id,
                {"reason": f"status={cargo['status']}"},
            )
            return

        self._add_stock(cargo["dest"], cargo["resource"], int(cargo["amount"]))
        cargo["status"] = "delivered"
        cargo["arrived_at"] = self.time
        self._append_ledger(
            "cargo_delivered",
            cargo_id,
            {
                "contract_id": cargo["contract_id"],
                "dest": cargo["dest"],
                "resource": cargo["resource"],
                "amount": cargo["amount"],
            },
        )

        contract = self.contracts[cargo["contract_id"]]
        if all(self.cargo[cid]["status"] == "delivered" for cid in contract["cargo_ids"]):
            contract["status"] = "fulfilled"
            contract["fulfilled_at"] = self.time
            civ_a, civ_b = contract["parties"]
            relation = self._relation(civ_a, civ_b)
            relation["trust"] = int(relation.get("trust", 0)) + 3
            self._append_ledger(
                "trade_contract_fulfilled",
                contract["contract_id"],
                {"trust_delta": 3, "parties": list(contract["parties"])},
            )

    def _dispatch(self, event: ScheduledEvent) -> None:
        self.time = event.due
        if event.kind == "produce":
            self._handle_produce(event)
        elif event.kind == "consume":
            self._handle_consume(event)
        elif event.kind == "intervention":
            self._handle_intervention(event)
        elif event.kind == "decision_review":
            self._handle_decision(event)
        elif event.kind == "cargo_arrival":
            self._handle_cargo_arrival(event)
        else:
            raise ValueError(f"unsupported scheduled event: {event.kind}")

    def run(self, horizon: int | None = None) -> dict[str, Any]:
        final_time = int(self.scenario["horizon"] if horizon is None else horizon)
        while self.queue and self.queue[0].due <= final_time:
            self._dispatch(heapq.heappop(self.queue))
        self.time = final_time
        return self.result()

    def result(self) -> dict[str, Any]:
        first_decisions: dict[str, str] = {}
        for receipt in self.decisions:
            first_decisions.setdefault(
                receipt["settlement_id"],
                receipt["selected"]["action"],
            )

        state = {
            "time": self.time,
            "revision": self.revision,
            "settlements": {
                sid: {
                    "civilization_id": row["civilization_id"],
                    "stock": dict(sorted(row["stock"].items())),
                    "capabilities": sorted(row["capabilities"]),
                    "memories": sorted(row["memories"]),
                }
                for sid, row in sorted(self.settlements.items())
            },
            "player_stock": dict(sorted(self.player_stock.items())),
            "sites": copy.deepcopy(dict(sorted(self.sites.items()))),
            "relations": copy.deepcopy(dict(sorted(self.relations.items()))),
            "contracts": copy.deepcopy(dict(sorted(self.contracts.items()))),
            "cargo": copy.deepcopy(dict(sorted(self.cargo.items()))),
            "sinks": {
                name: dict(sorted(values.items()))
                for name, values in sorted(self.sinks.items())
            },
            "produced": dict(sorted(self.produced.items())),
        }
        digest_payload = {
            "state": state,
            "decisions": self.decisions,
            "ledger": self.ledger,
        }
        digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        return {
            "schema": "supracraft.active4x-simulation-result/v0.1",
            "scenario_id": self.scenario["id"],
            "intervention": self.intervention,
            "world_scan": False,
            "first_decisions": first_decisions,
            "state": state,
            "decisions": copy.deepcopy(self.decisions),
            "ledger": copy.deepcopy(self.ledger),
            "balance": self._balance_report(),
            "deterministic_digest": digest,
        }


def run_intervention_matrix(
    scenario: dict[str, Any],
    interventions: list[str] | None = None,
) -> dict[str, Any]:
    names = interventions or list(scenario.get("interventions", {}).keys())
    results = {
        name: Active4XSimulation(scenario, name).run()
        for name in names
    }
    return results
