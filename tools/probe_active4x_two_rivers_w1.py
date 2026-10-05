#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_sim import Active4XSimulation
from active4x_trade_w1 import TradeDisruptionSimulation, scenario_with_trade_disruption


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--overlay", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    base_projection = json.loads(args.base.read_text("utf-8"))
    overlay = json.loads(args.overlay.read_text("utf-8"))
    base = base_projection["scenario"]
    disrupted_scenario = scenario_with_trade_disruption(base, overlay)

    baseline = Active4XSimulation(base, "none").run()
    disrupted = TradeDisruptionSimulation(
        disrupted_scenario,
        overlay["intervention"]["id"],
    ).run()
    replay = TradeDisruptionSimulation(
        disrupted_scenario,
        overlay["intervention"]["id"],
    ).run()

    contracts = list(disrupted["state"]["contracts"].values())
    kiln_decisions = [
        row["selected"]["action"]
        for row in disrupted["decisions"]
        if row["settlement_id"] == "kilnreach"
    ]

    checks = {
        "baseline_contract_fulfilled": any(
            row.get("status") == "fulfilled"
            for row in baseline["state"]["contracts"].values()
        ),
        "disrupted_contract_breached": any(
            row.get("status") == "breached" for row in contracts
        ),
        "cargo_disruption_recorded": any(
            row["kind"] == "cargo_disrupted" for row in disrupted["ledger"]
        ),
        "disrupted_contract_not_fulfilled": not any(
            row["kind"] == "trade_contract_fulfilled"
            for row in disrupted["ledger"]
        ),
        "later_kilnreach_secure_route": (
            len(kiln_decisions) >= 2 and kiln_decisions[1] == "secure_route"
        ),
        "resource_balance": disrupted["balance"]["passed"],
        "deterministic_replay": (
            disrupted["deterministic_digest"] == replay["deterministic_digest"]
        ),
        "world_scan_false": disrupted["world_scan"] is False,
    }
    passed = all(checks.values())

    out = {
        "schema": "supracraft.active4x-two-rivers-w1-trade-rdte/v0.1",
        "scenario_id": base["id"],
        "source_authority": overlay["source_authority"],
        "source_checkpoint": overlay["source_checkpoint"],
        "checks": checks,
        "baseline": {
            "first_decisions": baseline["first_decisions"],
            "contracts": baseline["state"]["contracts"],
        },
        "disrupted": {
            "first_decisions": disrupted["first_decisions"],
            "kilnreach_decisions": kiln_decisions,
            "contracts": disrupted["state"]["contracts"],
            "relation": disrupted["state"]["relations"],
            "lost_sink": disrupted["state"]["sinks"]["lost"],
        },
        "candidate_primitive": "Obligation/Contract",
        "deployment_stage": "D0_pure_deterministic_ci",
        "result": "PASS" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
