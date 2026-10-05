#!/usr/bin/env python3
"""Two Rivers W2 autonomous expansion composition.

Consumes real DecisionReceipts from the deterministic W0 kernel and composes
them into intent -> designation -> constructible candidate -> work-site task
using the already-qualified construction engine. No Minecraft runtime is needed
for this pure semantic composition rep.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from active4x_sim import Active4XSimulation


def find_decision(
    scenario: dict[str, Any],
    branch: str,
    settlement_id: str,
    action: str,
) -> dict[str, Any]:
    result = Active4XSimulation(scenario, branch).run()
    for receipt in result["decisions"]:
        if (
            receipt["settlement_id"] == settlement_id
            and receipt["selected"]["action"] == action
        ):
            return receipt
    raise ValueError(
        f"no decision receipt for branch={branch} settlement={settlement_id} "
        f"action={action}"
    )


def compose_expansion(
    scenario: dict[str, Any],
    expansion: dict[str, Any],
    shared_engine: str,
) -> dict[str, Any]:
    receipt = find_decision(
        scenario,
        expansion["qualifying_branch"],
        expansion["settlement_id"],
        expansion["decision_action"],
    )

    civilizations = {
        row["id"]: row for row in scenario["civilizations"]
    }
    civ = civilizations[expansion["civilization_id"]]
    civ_caps = set(civ.get("capabilities", []))
    candidate = expansion["selected_candidate"]
    required_civ = set(candidate.get("requires_civilization_capabilities", []))
    missing_civ = sorted(required_civ - civ_caps)

    required_intent_caps = set(expansion["intent"]["required_capabilities"])
    candidate_caps = set(candidate.get("capabilities", []))
    missing_function = sorted(required_intent_caps - candidate_caps)

    context = expansion["build_context"]
    context_caps = set(context.get("requires_capabilities", []))
    missing_context_caps = sorted(context_caps - civ_caps)

    bounds = expansion["designation"]["bounds"]
    minimum = bounds["min"]
    maximum = bounds["max"]
    bounded = (
        len(minimum) == 3
        and len(maximum) == 3
        and all(int(maximum[i]) >= int(minimum[i]) for i in range(3))
    )

    admitted = (
        not missing_civ
        and not missing_function
        and not missing_context_caps
        and bool(candidate.get("work_site_template_id"))
        and bounded
        and bool(context.get("selected_block"))
    )

    intent_id = (
        f"intent.{expansion['settlement_id']}."
        f"{receipt['decision_id']}.{expansion['decision_action']}"
    )
    task_id = f"task.{intent_id}.materialize"

    return {
        "schema": "supracraft.active4x-expansion-plan/v0.1",
        "civilization_id": expansion["civilization_id"],
        "settlement_id": expansion["settlement_id"],
        "qualifying_branch": expansion["qualifying_branch"],
        "decision_receipt": {
            "decision_id": receipt["decision_id"],
            "time": receipt["time"],
            "revision_observed": receipt["revision_observed"],
            "selected": receipt["selected"],
        },
        "intent": {
            "schema": "supracraft.intent/v0.1",
            "intent_id": intent_id,
            "kind": expansion["intent"]["kind"],
            "source_decision_id": receipt["decision_id"],
            "required_capabilities": sorted(required_intent_caps),
        },
        "designation": expansion["designation"],
        "candidate": candidate,
        "material_lowering": {
            "context_id": context["context_id"],
            "role": context["material_role"],
            "selected_block": context["selected_block"],
            "required_capabilities": context["requires_capabilities"],
            "required_resources": context["requires_resources"],
        },
        "task": {
            "schema": "supracraft.task/v0.1",
            "task_id": task_id,
            "kind": "materialize_work_site",
            "source_intent_id": intent_id,
            "work_site_template_id": candidate["work_site_template_id"],
            "construction_engine": shared_engine,
        },
        "checks": {
            "decision_receipt_present": True,
            "civilization_capabilities_admit_candidate": not missing_civ,
            "candidate_satisfies_intent": not missing_function,
            "material_context_admitted": not missing_context_caps,
            "designation_bounded": bounded,
            "constructible_work_site_present": bool(
                candidate.get("work_site_template_id")
            ),
            "shared_construction_engine": (
                shared_engine == "resource_gated_bounded_actuation"
            ),
            "world_scan_false": True,
        },
        "missing": {
            "civilization_capabilities": missing_civ,
            "intent_capabilities": missing_function,
            "material_context_capabilities": missing_context_caps,
        },
        "admitted": admitted,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--w2", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    base_projection = json.loads(args.base.read_text("utf-8"))
    scenario = base_projection["scenario"]
    w2 = json.loads(args.w2.read_text("utf-8"))

    plans = [
        compose_expansion(
            scenario,
            expansion,
            w2["shared_construction_engine"],
        )
        for expansion in w2["expansions"]
    ]

    distinct_materials = {
        plan["material_lowering"]["selected_block"] for plan in plans
    }
    checks = {
        "all_expansions_admitted": all(plan["admitted"] for plan in plans),
        "decision_receipts_drive_intents": all(
            plan["intent"]["source_decision_id"]
            == plan["decision_receipt"]["decision_id"]
            for plan in plans
        ),
        "tasks_reference_same_engine": all(
            plan["task"]["construction_engine"]
            == w2["shared_construction_engine"]
            for plan in plans
        ),
        "civilization_materials_are_distinct": len(distinct_materials) == len(plans),
        "world_scan_false": True,
        "no_second_construction_engine": (
            w2["shared_construction_engine"]
            == "resource_gated_bounded_actuation"
        ),
    }
    passed = all(checks.values())

    out = {
        "schema": "supracraft.active4x-two-rivers-w2-rdte/v0.1",
        "scenario_id": scenario["id"],
        "source_authority": w2["source_authority"],
        "source_checkpoint": w2["source_checkpoint"],
        "plans": plans,
        "checks": checks,
        "candidate_primitives_exercised": ["Intent", "Task", "DecisionReceipt"],
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
