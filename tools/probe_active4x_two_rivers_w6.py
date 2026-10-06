#!/usr/bin/env python3
"""Public W6 accelerated soak/adversarial oracle for Two Rivers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_soak_w6 import SoakSimulation, evaluate_soak_bounds


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--w6", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    scenario = json.loads(args.base.read_text("utf-8"))["scenario"]
    w6 = json.loads(args.w6.read_text("utf-8"))

    matrix = {}
    all_bounds = True
    all_replay = True

    for horizon in w6["horizons"]:
        for branch in w6["branches"]:
            key = f"{horizon}h:{branch}"
            first = SoakSimulation(scenario, branch).soak_result(int(horizon))
            replay = SoakSimulation(scenario, branch).soak_result(int(horizon))
            checks = evaluate_soak_bounds(first, w6["bounds"])
            replay_equal = (
                first["result"]["deterministic_digest"]
                == replay["result"]["deterministic_digest"]
                and first["metrics"] == replay["metrics"]
            )
            all_bounds = all_bounds and all(checks.values())
            all_replay = all_replay and replay_equal

            matrix[key] = {
                "checks": checks,
                "replay_equal": replay_equal,
                "deterministic_digest": first["result"]["deterministic_digest"],
                "metrics": first["metrics"],
                "final_first_decisions": first["result"]["first_decisions"],
                "final_relation_state": first["result"]["state"]["relations"],
                "final_contract_count": len(first["result"]["state"]["contracts"]),
            }

    checks = {
        "accelerated_24h_72h_soak": len(matrix) == (
            len(w6["horizons"]) * len(w6["branches"])
        ),
        "no_resource_drift": all(
            row["checks"]["resource_balance"] for row in matrix.values()
        ),
        "deterministic_replay": all_replay,
        "bounded_queue_growth": all(
            row["checks"]["queue_bounded"] for row in matrix.values()
        ),
        "no_negative_stocks": all(
            row["checks"]["no_negative_stocks"] for row in matrix.values()
        ),
        "no_runaway_trade_war_oscillation": all(
            row["checks"]["trade_rate_bounded_by_decisions"]
            and row["checks"]["open_contracts_bounded"]
            and row["checks"]["relations_bounded"]
            and row["checks"]["contract_states_valid"]
            for row in matrix.values()
        ),
        "actor_pool_bounded": all(
            row["checks"]["actor_demand_bounded"] for row in matrix.values()
        ),
        "all_branch_bounds": all_bounds,
        "world_scan_false": w6["acceptance"]["world_scan"] is False,
    }
    passed = all(checks.values())

    result = {
        "schema": "supracraft.active4x-two-rivers-w6-rdte/v0.1",
        "source_authority": w6["source_authority"],
        "source_checkpoint": w6["source_checkpoint"],
        "simulated_time_unit": w6["simulated_time_unit"],
        "checks": checks,
        "matrix": matrix,
        "bounds": w6["bounds"],
        "deployment_stage": "D0_accelerated_soak",
        "world_scan": False,
        "result": "PASS" if passed else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
