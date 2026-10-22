#!/usr/bin/env python3
"""Bounded causal-attribution audit of paired original-version legacy gameplay.

This is *not* an engine tracing oracle. It independently joins source-authored
command targets to paired world readback and selected command-state transitions.
Never export original world coordinates, commands, NBT or private runner inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

SCHEMA = "supracraft-legacy-causal-attribution-audit/1"
WRITERS = {"setblock", "fill", "clone", "summon"}
# Command direct-target sampling cannot generally establish entity spawning or
# whether a partial fill/clone performed all desired changes.
BLOCK_MUTATORS = {"setblock", "fill", "clone"}
OUTCOME = {
    "scoped_direct_block_target_delta",
    "scoped_candidate_delta_no_changed_command",
    "scoped_effect_unattributable_ambiguous_writers",
    "out_of_scope_or_nonmutator_delta",
    "no_scoped_target_delta",
}


def audit(selection: dict, paired: dict) -> dict:
    if selection.get("schema") != "supracraft-legacy-runtime-probe-selection/1":
        raise ValueError("selection schema")
    if paired.get("schema") != "supracraft-paired-legacy-runtime-probes/1":
        raise ValueError("paired schema")
    if paired.get("minecraft_version") != "1.8.8":
        raise ValueError("original version mismatch")
    if paired.get("paired_control_design") is not True:
        raise ValueError("paired-sham design absent")
    sr = selection.get("selected", [])
    results = paired.get("results", [])
    if len(sr) != 1 or len(results) != 1 or paired.get("probe_count") != 1:
        raise ValueError("requires exactly one paired sensor witness")
    selected, row = sr[0], results[0]
    probe = row.get("probe", {})
    if selected.get("node_id") != probe.get("node_id"):
        raise ValueError("sensor identity mismatch")
    if selected.get("family") != probe.get("family"):
        raise ValueError("sensor family mismatch")
    if selected.get("family") not in {
        "stone_pressure_plate", "wooden_pressure_plate",
        "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
    }:
        raise ValueError("unsupported non-player occupancy probe")
    if row.get("activation_method") != "paired_exact_1.8.8_player_occupancy":
        raise ValueError("player actuation not proven")
    evidence = row.get("evidence", {})
    if not evidence.get("live_sensor_activation_observed"):
        raise ValueError("activated player's sensor was not proven")
    if not row.get("sensor_state", {}).get("changed"):
        raise ValueError("missing paired sensor state transition")
    actors = row.get("player_actor", {})
    for arm in ("control", "activated"):
        if actors.get(arm, {}).get("status") != "ready":
            raise ValueError("missing original-version player "+arm)
        if actors[arm].get("minecraft_version") != "1.8.8":
            raise ValueError("incompatible original-version player "+arm)

    entries = selected.get("candidate_component_commands", [])
    if not isinstance(entries, list) or not entries:
        raise ValueError("empty source-backed command scope")
    candidate = {
        v.get("node_id"): v for v in entries
        if isinstance(v, dict) and isinstance(v.get("node_id"), str)
    }
    if len(candidate) != len(entries):
        raise ValueError("duplicate or malformed command IDs")
    # Source authority must provide real SHA256 values; missing fingerprints
    # must not silently equal missing runtime fingerprints.
    if any(not isinstance(v.get("command_sha256"), str)
           or len(v["command_sha256"]) != 64
           or any(c not in "0123456789abcdef" for c in v["command_sha256"])
           for v in candidate.values()):
        raise ValueError("missing or invalid source command fingerprint")

    receipt = row.get("execution_receipt", {})
    if receipt.get("schema") != "supracraft-legacy-execution-receipt/1":
        raise ValueError("missing original execution receipt")
    scope = set(receipt.get("command_scope", []))
    if not scope or set(candidate) != scope:
        raise ValueError("source command scope mismatch")
    if set(row.get("world_target_source_scope", [])) != scope:
        raise ValueError("world-target source scope mismatch")
    receipt_cmds = {
        c.get("node_id"): c for c in receipt.get("commands", [])
        if isinstance(c, dict) and isinstance(c.get("node_id"), str)
    }
    if set(receipt_cmds) != scope or len(receipt_cmds) != len(receipt.get("commands", [])):
        raise ValueError("execution source scope not complete")
    verified_changed_commands = set()
    for cid, cmd in receipt_cmds.items():
        prev = cmd.get("control") or {}
        after = cmd.get("activated") or {}
        if prev.get("sha256") != candidate[cid].get("command_sha256") or (
            after.get("sha256") != candidate[cid].get("command_sha256")
        ):
            raise ValueError("command byte fingerprint mismatch")
        if prev.get("verb") != candidate[cid].get("verb") or after.get("verb") != candidate[cid].get("verb"):
            raise ValueError("command semantic verb mismatch")
        if any(prev.get(k) != after.get(k) for k in (
            "success_count", "condition_met", "powered", "last_execution",
            "last_output_sha256",
        )):
            verified_changed_commands.add(cid)
    if set(receipt.get("changed_command_ids", [])) != verified_changed_commands:
        raise ValueError("changed command-field receipt inconsistent")
    # This checks direct *source-labelled* targets, not all possible legacy writes.
    targets = receipt.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("target receipt malformed")
    changed_rows = []
    writer_by_target = {}
    for t in targets:
        source = t.get("source")
        if source not in scope:
            raise ValueError("unscoped target")
        verb = t.get("verb")
        # Never let an untrusted target row self-assert that an unrelated
        # read-only/teleport command is a direct block mutator.
        if verb != candidate[source].get("verb") or verb != receipt_cmds[source]["control"].get("verb"):
            raise ValueError("target verb disagrees with exact source command")
        if verb not in WRITERS and t.get("changed"):
            raise ValueError("claimed changed target from non-world-mutating command")
        expected_change = t.get("control") != t.get("activated")
        if t.get("changed") is not expected_change:
            raise ValueError("incorrect paired target change flag")
        key = tuple(t.get("target_position") or [])
        if len(key) != 3:
            raise ValueError("invalid target position")
        if verb in BLOCK_MUTATORS:
            writer_by_target.setdefault(key, set()).add(source)
        if expected_change:
            changed_rows.append((source, key, verb, t))
    changed_sources = {x[0] for x in changed_rows}
    changed_writers = [
        (src, key, verb, t) for src, key, verb, t in changed_rows
        if verb in BLOCK_MUTATORS
    ]
    qualified_ids = {
        src for src, key, _, _ in changed_writers
        if src in verified_changed_commands and len(writer_by_target.get(key, ())) == 1
    }
    ambiguous_count = sum(
        len(writer_by_target.get(key, ())) != 1
        for _, key, _, _ in changed_writers
    )
    counts = Counter(v for _,_,v,_ in changed_rows)
    if not changed_writers:
        outcome = ("out_of_scope_or_nonmutator_delta" if changed_rows
                   else "no_scoped_target_delta")
    elif ambiguous_count:
        outcome = "scoped_effect_unattributable_ambiguous_writers"
    elif not qualified_ids:
        outcome = "scoped_candidate_delta_no_changed_command"
    else:
        outcome = "scoped_direct_block_target_delta"

    # Source-supported correlation only: no per-command tick trace and no
    # verified manipulation of downstream wiring.
    return {
        "schema": SCHEMA,
        "source_version": "1.8.8",
        "evidence_class": "PAIRED_SOURCE_CORRELATION_NOT_CAUSAL_EXCLUSIVITY",
        "sensor_family": selected.get("family"),
        # A plain hash of an enumerable coordinate is reversible; emit no
        # location-derived identity in publicly retained result.
        "direct_candidate_command_count": len(candidate),
        "paired_changed_direct_command_count": len(verified_changed_commands),
        "all_local_command_change_count": int(evidence.get("command_block_change_count", 0)),
        "scoped_target_count": len(targets),
        "scoped_changed_target_count": len(changed_rows),
        "scoped_changed_target_verb_counts": dict(sorted(counts.items())),
        "matched_source_state_and_unique_target_count": len(qualified_ids),
        "changed_target_with_competing_writer_count": ambiguous_count,
        "effect_observation_class": outcome,
        "sensor_state_change_observed": True,
        "live_player_sensor_activation_observed": True,
        "exact_source_command_fingerprint_verified": True,
        "selection_runtime_source_world_join": "UNVERIFIED_NO_SHARED_PINNED_SOURCE_ID",
        "competing_world_writers_outside_selected_command_scope": "UNKNOWN",
        "original_world_effect_observed": bool(changed_rows),
        "native_command_execution_trace": "NOT_RUN",
        "exclusive_downstream_causality": "NOT_PROVEN",
        "restart_persistence": "NOT_RUN",
        "modern_26_3_equivalence": "NOT_RUN",
        "rule_promotion": "HOLD",
        "limits": [
            "State readback identifies source-labelled authored targets, not the actual execution tick.",
            "Other commands and ambient machinery may mutate the same target.",
            "A command-state change and target-state delta do not alone prove exclusive causation.",
            "Static selector may omit upstream and downstream intermediate electrical components.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--paired", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    result = audit(json.loads(a.selection.read_text(encoding="utf-8")),
                   json.loads(a.paired.read_text(encoding="utf-8")))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps({
        "effect_observation_class": result["effect_observation_class"],
        "scoped_changed_target_count": result["scoped_changed_target_count"],
        "matched_source_state_and_unique_target_count": result["matched_source_state_and_unique_target_count"],
        "exclusive_downstream_causality": result["exclusive_downstream_causality"],
    },sort_keys=True))


if __name__=="__main__":
    main()
