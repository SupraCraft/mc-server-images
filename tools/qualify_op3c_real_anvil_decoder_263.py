#!/usr/bin/env python3
"""Read-only, public-$0 OP-3C real-world source qualification of the G4 Anvil decoder.

Uses the unchanged accepted OP-3C 26.3 real offline-player/rollback lifecycle,
interposing only a process-local, read-only witness at each *stopped* checkpoint.
No TrueNAS, private code, remote world, secrets, stock player, or G4 admission.
No region bytes, Minecraft server binaries or logs are retained or published.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import qualify_vanilla_datapack_player_263 as op3c
from qualify_vanilla_263_oci_disposable import (
    OVERWORLD_REGION_COMPONENTS, REGION_NAME,
    MIN_REGION_BYTES, MAX_REGION_BYTES, stopped_world_region_witness,
)

ROOT = Path(__file__).resolve().parents[1]
DECODER = ROOT / ".deps/agent-dispatch/scripts/qualify_native_vanilla263_anvil_blocks.py"
PINNED_G4_REF = "e400f3a1719a21cf91ebc86ba8d44efea05c1325"
STAGES = ("preaction", "candidate", "rollback")
SCHEMA = "supracraft.op3c-real-vanilla263-g4-anvil-source-qualification/1"


def sanitized_reason(error: Exception, *, g4_refused_type: type) -> str:
    """Never print an arbitrary exception, provider URL, source or filesystem path."""
    if type(error) is g4_refused_type:
        code = str(error)
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,79}", code):
            return code
    return "DECODER_UNEXPECTED_EXCEPTION"


def load_pinned_decoder():
    if not DECODER.is_file() or DECODER.is_symlink():
        raise ValueError("PINNED_DECODER_ABSENT")
    spec = importlib.util.spec_from_file_location("pinned_g4_anvil_blocks", DECODER)
    if spec is None or spec.loader is None:
        raise ValueError("PINNED_DECODER_LOAD_REFUSED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def qualify(*, candidate: Path, manifest: dict, evidence: dict, out: Path) -> int:
    decoder = load_pinned_decoder()
    observations: list[dict] = []
    original = op3c.stopped_world_region_witness

    def observe_stopped_world(world: Path) -> dict:
        # The original OP-3C flow invokes this only after stop_server(proc)==0.
        stage_index = len(observations)
        if stage_index >= len(STAGES):
            raise ValueError("REGION_OBSERVER_CHECKPOINT_OVERFLOW")
        stage = STAGES[stage_index]
        witness = stopped_world_region_witness(world)
        entry = {
            "stage": stage, "classification": "REFUSED",
            "reason": "REGION_NOT_BOUNDED_PRESENT",
            "region_sha256": None, "decoder_matched": False,
            "server_origin_authenticated": False,
            "native_truenas_oracle_pass": False,
        }
        if witness["classification"] == "REGION_FILE_BOUNDED_PRESENT":
            source = world.joinpath(*OVERWORLD_REGION_COMPONENTS) / REGION_NAME
            if not source.is_symlink() and source.is_file():
                raw = source.read_bytes()
                if MIN_REGION_BYTES <= len(raw) <= MAX_REGION_BYTES:
                    entry["region_sha256"] = hashlib.sha256(raw).hexdigest()
                    try:
                        result = decoder.inspect(raw, stage)
                    except Exception as exc:
                        entry["reason"] = sanitized_reason(
                            exc, g4_refused_type=decoder.Refused)
                    else:
                        entry["classification"] = "UNTRUSTED_REAL_OP3C_REGION_DECODED"
                        entry["reason"] = "NONE"
                        entry["decoder_matched"] = (
                            result.get("block_state_expectations_matched") is True
                            and result.get("native_guest_server_owned_bytes_proven") is False
                            and result.get("backend_independent_world_oracle_pass") is False)
        observations.append(entry)
        return witness  # Preserve existing independent OP-3C presence readback.

    receipt = {
        "schema": SCHEMA, "decoder_source_ref": PINNED_G4_REF,
        "classification": "SOURCE_DIAGNOSTIC_INCOMPLETE",
        "stages": observations, "real_op3c_player_qualified": False,
        "decoder_all_three_stages_qualified": False,
        "raw_world_bytes_published": False, "server_binary_published": False,
        "native_truenas_oracle_pass": False, "collage_mutation_authorized": False,
        "physical_truenas_apply": "HOLD", "g4_acceptance": "HOLD",
        "op4o_022_admitted": False,
    }
    op3c.stopped_world_region_witness = observe_stopped_world
    try:
        # Only read-only interposition; no change to core player, snapshot,
        # independent fixture predicate, or disposable-world cleanup.
        result = op3c.execute(candidate, manifest, evidence)
        receipt["real_op3c_player_qualified"] = (
            result.get("classification") ==
            "REAL_OFFLINE_PLAYER_ACTION_CAUSAL_ARTIFACT_AND_ROLLBACK"
            and result.get("rollback_exact_snapshot_before_restart") is True
            and result.get("temporary_world_retired") is True)
        receipt["real_op3c_version"] = result.get("minecraft_version")
        receipt["real_op3c_protocol"] = result.get("protocol")
        receipt["server_sha256"] = result.get("server_sha256")
    except Exception:
        # A driver failure is not itself an Anvil parser error; never emit
        # raw subprocess/provider exception text into public artifacts.
        receipt["classification"] = "OP3C_DRIVER_INCOMPLETE"
    finally:
        op3c.stopped_world_region_witness = original

    receipt["decoder_all_three_stages_qualified"] = (
        receipt["real_op3c_player_qualified"]
        and len(observations) == len(STAGES)
        and all(v["stage"] == stage and v["decoder_matched"]
                for v, stage in zip(observations, STAGES))
        and len({v["region_sha256"] for v in observations}) == len(STAGES))
    if receipt["real_op3c_player_qualified"]:
        receipt["classification"] = (
            "REAL_OP3C_DECODER_THREE_STAGE_SOURCE_PASS"
            if receipt["decoder_all_three_stages_qualified"]
            else "REAL_OP3C_DECODER_REJECTED_OR_INCOMPLETE")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "classification": receipt["classification"],
        "decoder_all_three_stages_qualified": receipt["decoder_all_three_stages_qualified"],
        "stage_reasons": [s["reason"] for s in observations],
    }, sort_keys=True))
    # A valid diagnostic failure does not silently count as decoder acceptance.
    # CI can retain a bounded first-failure artifact without replaying native G4.
    return 0 if receipt["real_op3c_player_qualified"] else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    return qualify(candidate=a.candidate, manifest=json.loads(a.manifest.read_text()),
                   evidence=json.loads(a.evidence.read_text()), out=a.out)


if __name__ == "__main__":
    raise SystemExit(main())
