#!/usr/bin/env python3
"""Read-only, fail-closed Two Rivers D4 eligibility check.

Checks existing receipts; does not run D4 or validate human identity/provenance.
Authenticity of the stock-client HIL receipt requires separate owner review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HIL_CHECKS = frozenset({
    "stock_client_attested_exact_26_3", "trade_legible",
    "construction_help_legible", "construction_obstruction_legible",
    "caravan_encounter", "damage_consequence_legible", "logout_rejoin",
    "restart_recovery_persists", "semantic_revision_monotonic",
    "human_legibility_attested", "no_manual_admin_commands_required",
    "world_scan_false",
})
REHEARSAL_CHECKS = frozenset({
    "exact_26_3_rehearsal_client", "trade_path",
    "construction_help_path", "construction_obstruction_path",
    "damage_path", "caravan_encounter_path", "restart_recovery_path",
    "semantic_revision_monotonic", "stock_client_hil_not_claimed",
    "world_scan_false",
})


def load_receipt(path: Path, label: str, problems: list[str]) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        problems.append(f"{label}:missing_or_invalid_json")
        return {}
    if not isinstance(data, dict):
        problems.append(f"{label}:not_an_object")
        return {}
    return data


def validate_hil(x: dict, problems: list[str]) -> None:
    if x.get("schema") != "supracraft.active4x-two-rivers-d3-hil-result/v0.1":
        problems.append("hil:schema")
    if x.get("deployment_stage") != "D3_stock_client_hil" or x.get("result") != "PASS":
        problems.append("hil:not_pass")
    minecraft = x.get("minecraft") if isinstance(x.get("minecraft"), dict) else {}
    if minecraft.get("edition") != "java" or minecraft.get("version") != "26.3" or minecraft.get("stock_client_attested") is not True:
        problems.append("hil:exact_stock_client_attestation")
    if x.get("human_legibility_attested") is not True:
        problems.append("hil:human_legibility")
    if x.get("world_scan") is not False:
        problems.append("hil:world_scan")
    player = x.get("player")
    if not isinstance(player, str) or not player.strip() or player in {"TwoRiversHIL", "TwoRiversD2B", "TwoRiversD3Witness"}:
        problems.append("hil:distinct_stock_player")
    checks = x.get("checks") if isinstance(x.get("checks"), dict) else {}
    if any(checks.get(k) is not True for k in HIL_CHECKS):
        problems.append("hil:incomplete_original_checks")
    actor = x.get("actor") if isinstance(x.get("actor"), dict) else {}
    if actor.get("result") != "delivered":
        problems.append("hil:actor_not_delivered")
    director = x.get("director") if isinstance(x.get("director"), dict) else {}
    apply = director.get("apply") if isinstance(director.get("apply"), dict) else {}
    state = director.get("state") if isinstance(director.get("state"), dict) else {}
    if apply.get("accepted") is not True or apply.get("revision") != 1 or state.get("revision") != 1:
        problems.append("hil:director_revision")


def validate_rehearsal(x: dict, problems: list[str]) -> None:
    if x.get("schema") != "supracraft.active4x-two-rivers-d3-rehearsal/v0.1":
        problems.append("rehearsal:schema")
    if x.get("deployment_stage") != "D3_automated_rehearsal" or x.get("result") != "PASS":
        problems.append("rehearsal:not_pass")
    if x.get("world_scan") is not False or x.get("stock_client_hil_required") is not True:
        problems.append("rehearsal:scope_or_hil_claim")
    checks = x.get("checks") if isinstance(x.get("checks"), dict) else {}
    if any(checks.get(k) is not True for k in REHEARSAL_CHECKS):
        problems.append("rehearsal:incomplete_original_checks")
    interaction = x.get("interaction_client") if isinstance(x.get("interaction_client"), dict) else {}
    minecraft = interaction.get("minecraft") if isinstance(interaction.get("minecraft"), dict) else {}
    if interaction.get("result") != "PASS" or minecraft.get("edition") != "java" or minecraft.get("version") != "26.3":
        problems.append("rehearsal:client")
    caravan = interaction.get("caravan") if isinstance(interaction.get("caravan"), dict) else {}
    distance = caravan.get("min_distance")
    if caravan.get("seen") is not True or not isinstance(distance, (int, float)) or isinstance(distance, bool) or not 0 <= distance <= 32:
        problems.append("rehearsal:caravan_proximity")
    actor = x.get("caravan_actor") if isinstance(x.get("caravan_actor"), dict) else {}
    if actor.get("result") != "delivered" or actor.get("amount") != 4:
        problems.append("rehearsal:delivery")
    director = x.get("director") if isinstance(x.get("director"), dict) else {}
    state = director.get("state") if isinstance(director.get("state"), dict) else {}
    if state.get("revision") != 1:
        problems.append("rehearsal:revision")


def assess(hil: Path, rehearsal: Path) -> dict:
    problems: list[str] = []
    validate_rehearsal(load_receipt(rehearsal, "rehearsal", problems), problems)
    validate_hil(load_receipt(hil, "hil", problems), problems)
    return {
        "schema": "supracraft.active4x-two-rivers-d4-admission/v0.1",
        "gate": "D4_preflight",
        "eligible_for_provenance_review": not problems,
        "decision": "EVIDENCE_READY_FOR_REVIEW" if not problems else "HOLD",
        "reasons": sorted(set(problems)),
        "caveat": "Static receipt validation is not proof of human participation or GitHub evidence provenance. D4 execution also requires authorized D3-HIL evidence review.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hil", type=Path, default=Path("probes/active4x/two-rivers-d3-hil-result.json"))
    parser.add_argument("--rehearsal", type=Path, default=Path("probes/active4x/two-rivers-d3-rehearsal-result.json"))
    args = parser.parse_args()
    answer = assess(args.hil, args.rehearsal)
    print(json.dumps(answer, indent=2, sort_keys=True))
    return 0 if answer["eligible_for_provenance_review"] else 2


if __name__ == "__main__":
    sys.exit(main())
