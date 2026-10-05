#!/usr/bin/env python3
"""Public RDTE oracle for the Two Rivers active-4X vertical slice W0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_sim import Active4XSimulation, run_intervention_matrix


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    projection = json.loads(args.scenario.read_text("utf-8"))
    scenario = projection["scenario"]
    required = scenario["acceptance"]["require_distinct_decisions"]

    matrix = run_intervention_matrix(scenario, required)
    replay_checks = {}
    summaries = {}

    for name in required:
        replay = Active4XSimulation(scenario, name).run()
        result = matrix[name]
        replay_checks[name] = (
            replay["deterministic_digest"] == result["deterministic_digest"]
        )
        summaries[name] = {
            "first_decisions": result["first_decisions"],
            "balance_passed": result["balance"]["passed"],
            "deterministic_digest": result["deterministic_digest"],
            "decision_count": len(result["decisions"]),
            "event_count": len(result["ledger"]),
            "contract_count": len(result["state"]["contracts"]),
            "fulfilled_contract_count": sum(
                1
                for row in result["state"]["contracts"].values()
                if row.get("status") == "fulfilled"
            ),
            "iron_ford_claimed_by": result["state"]["sites"]["iron_ford"].get(
                "claimed_by"
            ),
            "final_capabilities": {
                sid: row["capabilities"]
                for sid, row in result["state"]["settlements"].items()
            },
        }

    signatures = {
        name: tuple(sorted(matrix[name]["first_decisions"].items()))
        for name in required
    }
    distinct_decisions = len(set(signatures.values())) == len(required)
    balances = all(matrix[name]["balance"]["passed"] for name in required)
    replay_equal = all(replay_checks.values())

    baseline = matrix["none"]
    has_trade = any(
        row["kind"] == "trade_contract_created" for row in baseline["ledger"]
    ) and any(
        row["kind"] == "trade_contract_fulfilled" for row in baseline["ledger"]
    )
    autonomous_progress = (
        sum(1 for row in baseline["ledger"] if row["kind"] == "production_completed")
        >= 8
        and sum(1 for row in baseline["ledger"] if row["kind"] == "consumption")
        >= 12
        and sum(1 for row in baseline["ledger"] if row["kind"] == "decision_committed")
        >= 6
    )

    targeted = {
        "feed_changes_kilnreach": (
            matrix["feed_kilnreach"]["first_decisions"]["kilnreach"]
            == "claim_iron_ford"
        ),
        "brick_aid_changes_stoneford": (
            matrix["supply_stoneford_bricks"]["first_decisions"]["stoneford"]
            == "build_granary"
        ),
        "route_disruption_changes_kilnreach": (
            matrix["sabotage_kilnreach_route"]["first_decisions"]["kilnreach"]
            == "secure_route"
        ),
    }

    checks = {
        "distinct_intervention_decisions": distinct_decisions,
        "resource_balance": balances,
        "deterministic_replay": replay_equal,
        "baseline_trade_contract": has_trade,
        "autonomous_progress_without_player": autonomous_progress,
        **targeted,
        "world_scan_false": scenario["acceptance"]["world_scan"] is False,
    }
    passed = all(checks.values())

    out = {
        "schema": "supracraft.active4x-two-rivers-rdte/v0.1",
        "scenario_id": scenario["id"],
        "source_authority": projection["source_authority"],
        "source_checkpoint": projection["source_checkpoint"],
        "horizon": scenario["horizon"],
        "checks": checks,
        "branches": summaries,
        "candidate_primitives_exercised": [
            "Event",
            "DecisionReceipt",
            "Obligation/Contract",
            "Intent",
        ],
        "deployment_stage": "D0_pure_deterministic_ci",
        "minecraft_runtime_required": False,
        "world_scan": False,
        "result": "PASS" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
