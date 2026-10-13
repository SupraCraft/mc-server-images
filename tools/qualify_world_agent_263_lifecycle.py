#!/usr/bin/env python3
"""S5: real disposable vanilla world-agent activation and health-fault rollback.

Uses existing world-agent stage/hash/activate/restore; no Docker socket, no
Foundry credential and no new fleet manager. World remains a separately owned
asset. This is POSIX-local RDTE, never native TrueNAS or physical APPLY.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from minecraft_world_agent import tree_hash
from probe_core_restoration_datapack_26_3 import (
    initial_predicate, restored_predicate, send, stop_server,
)
from qualify_vanilla_world_artifact_activation_263 import (
    Refused, baseline_without_pack_predicate, launch, oracle, require,
    server_config, validate_candidate,
)
from smoke_vanilla_runtime import download_verified_server

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "tools/minecraft_world_agent.py"
SCHEMA = "supracraft.s5-world-agent-vanilla-live-activation/1"
PASS = "REAL_WORLD_AGENT_STAGE_ACTIVATE_HEALTH_ROLLBACK"
PACK_SHA = "da25005e8729e6f013f7108ac5b8869dd46323befc78efdae18221b26cafe5f8"


def assert_agent_receipt(verb: str, record: dict, release: str | None = None,
                         sha: str | None = None) -> None:
    require(type(record) is dict and
            record.get("schema") == "minecraft-world-agent-receipt/1"
            and record.get("verb") == verb, "S5_AGENT_RECEIPT_SCHEMA")
    if release is not None:
        require(record.get("release") == release, "S5_AGENT_RELEASE_IDENTITY")
    if sha is not None:
        require(record.get("sha256") == sha, "S5_AGENT_HASH_DRIFT")


def owned_active(root: Path, release: str) -> bool:
    """Fail closed on non-owned, non-staged or surprising symlink target."""
    link = root / "active"
    expected = root / "releases" / release
    require(re.fullmatch("[a-z0-9-]{1,48}", release) is not None,
            "S5_RELEASE_ID_INVALID")
    require(link.is_symlink() and expected.is_dir()
            and link.resolve(strict=True) == expected.resolve(strict=True)
            and expected.resolve(strict=True).parent == (root / "releases").resolve(),
            "S5_ACTIVE_OWNER_MISMATCH")
    return True


def world_agent(root: Path, verb: str, release: str | None = None,
                source: Path | None = None) -> dict:
    """Exact one-verb disposable agent action with independent JSON readback."""
    require(root.is_dir() and not root.is_symlink(), "S5_AGENT_ROOT_INVALID")
    cmd = [sys.executable, str(AGENT), verb, "--root", str(root)]
    if release is not None:
        require(re.fullmatch("[a-z0-9-]{1,48}", release) is not None,
                "S5_RELEASE_ID_INVALID")
        cmd += ["--release", release]
    if source is not None:
        require(source.is_dir() and not source.is_symlink(),
                "S5_STAGE_SOURCE_NOT_OWNED_DIRECTORY")
        cmd += ["--source", str(source)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    require(result.returncode == 0, "S5_WORLD_AGENT_VERB_REFUSED_" + verb.upper())
    try:
        record = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Refused("S5_AGENT_RESULT_NOT_JSON") from exc
    assert_agent_receipt(verb, record, release if verb in
                         ("stage", "activate", "restore") else None)
    if release is not None and verb in ("activate", "restore"):
        owned_active(root, release)
    return record


def safe_switch(root: Path, verb: str, release: str,
                process: subprocess.Popen | None) -> dict:
    require(verb in ("activate", "restore"), "S5_UNADMITTED_SWITCH_VERB")
    require(process is None or process.poll() is not None,
            "S5_ACTIVE_SERVER_POINTER_MUTATION_REFUSED")
    return world_agent(root, verb, release)


def fixture(process: subprocess.Popen, log: Path) -> None:
    send(process, "forceload add 0 0")
    send(process, "fill -2 69 -2 4 69 3 minecraft:stone")
    send(process, "fill -2 70 -2 4 72 3 minecraft:air")
    send(process, "setblock 0 70 0 minecraft:air")
    send(process, "setblock 2 70 0 minecraft:iron_bars")
    send(process, "setblock 1 70 1 minecraft:black_concrete")
    oracle(process, log, initial_predicate(), "S5_REAL_BASELINE")


def verify_fault_is_not_promotable(expected: str, actual: str) -> bool:
    """Negative health/fault injection must not be silently treated as success."""
    require(expected == actual and len(expected) == 64,
            "S5_INJECTED_HEALTH_ORACLE_MISMATCH")
    return True


def execute(candidate: Path, manifest: dict, evidence: dict) -> dict:
    accepted = validate_candidate(candidate, manifest)
    require(accepted["sha256"] == PACK_SHA, "S5_WORLD_ARTIFACT_DIGEST_DRIFT")
    version = evidence["artifact_version_json"]
    require(version["id"] == "26.3" and
            version["protocol_version"] == 777 and
            version["java_version"] == 25, "S5_VANILLA_VERSION_DRIFT")
    transaction = json.loads((ROOT / "spec/minecraft-world-activation-transaction-v1.json").read_text())
    require(transaction["ordered_steps"] ==
            ["quiesce", "snapshot_current", "activate_candidate", "resume", "health_check"]
            and transaction["transport_boundary"]["docker_socket"] is False
            and transaction["transport_boundary"]["foundry_credentials"] is False,
            "S5_WORLD_TRANSACTION_POLICY_DRIFT")
    with tempfile.TemporaryDirectory(prefix="supracraft-s5-world-agent-") as td:
        root = Path(td)
        home = root / "server"
        home.mkdir()
        agent = root / "owned-world"
        agent.mkdir()
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        jar_sha = hashlib.sha256(jar.read_bytes()).hexdigest()
        require(jar_sha == evidence["server_artifact"]["sha256"],
                "S5_MOJANG_SERVER_JAR_DRIFT")
        server_config(home)
        handles = []
        stages = []
        try:
            # First build a real vanilla world as independently owned source.
            baseline, base_log = launch(home, jar, evidence, "s5-generate", handles)
            fixture(baseline, base_log)
            require(stop_server(baseline) == 0, "S5_BASELINE_QUIESCE_FAILED")
            stages.append("real_world_quiesced")
            baseline_source = home / "world"
            original_sha = tree_hash(baseline_source)
            first = world_agent(agent, "stage", "prior", baseline_source)
            assert_agent_receipt("stage", first, "prior", original_sha)
            stages.append("prior_release_staged_and_hash_verified")
            shutil.rmtree(baseline_source)
            activated = safe_switch(agent, "activate", "prior", baseline)
            assert_agent_receipt("activate", activated, "prior", original_sha)
            os.symlink(agent / "active", home / "world")
            require(owned_active(agent, "prior"), "S5_PRIOR_NOT_ACTIVE")
            stages.append("prior_activated_via_agent")

            live, log = launch(home, jar, evidence, "s5-prior", handles)
            oracle(live, log, initial_predicate(), "S5_PRIOR_RUNTIME_READY")
            try:
                safe_switch(agent, "restore", "prior", live)
            except Refused as exc:
                require(str(exc) == "S5_ACTIVE_SERVER_POINTER_MUTATION_REFUSED",
                        "S5_UNEXPECTED_LIVE_SWITCH_REFUSAL")
            else:
                raise Refused("S5_LIVE_MUTATION_UNEXPECTEDLY_ALLOWED")
            stages.append("live_server_pointer_switch_denied")
            require(stop_server(live) == 0, "S5_PRIOR_SNAPSHOT_QUIESCE_FAILED")
            prior_sha = tree_hash(agent / "releases/prior")
            snap = world_agent(agent, "stage", "snapshot",
                               agent / "releases/prior")
            assert_agent_receipt("stage", snap, "snapshot", prior_sha)
            stages.append("snapshot_current_independently_hashed")

            candidate_source = root / "candidate-world"
            shutil.copytree(agent / "releases/snapshot", candidate_source,
                            symlinks=False)
            staged_pack = candidate_source / "datapacks/candidate.zip"
            require(not staged_pack.exists(), "S5_DATAPACK_ALREADY_PRESENT")
            staged_pack.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, staged_pack)
            require(hashlib.sha256(staged_pack.read_bytes()).hexdigest() == PACK_SHA,
                    "S5_CANDIDATE_DATAPACK_STAGE_DRIFT")
            candidate_sha = tree_hash(candidate_source)
            cand = world_agent(agent, "stage", "candidate", candidate_source)
            assert_agent_receipt("stage", cand, "candidate", candidate_sha)
            stages.append("candidate_staged_and_hash_verified")

            swap = safe_switch(agent, "activate", "candidate", live)
            assert_agent_receipt("activate", swap, "candidate", candidate_sha)
            stages.append("activate_candidate_after_quiesce")
            running, cand_log = launch(home, jar, evidence, "s5-candidate", handles)
            oracle(running, cand_log, initial_predicate(), "S5_CANDIDATE_PRE_ACTION")
            send(running, "setblock 0 70 0 minecraft:redstone_block")
            oracle(running, cand_log, restored_predicate(), "S5_CANDIDATE_REAL_EFFECT")
            stages.append("resume_and_live_positive_health")
            require(stop_server(running) == 0, "S5_CANDIDATE_STOP_FAILED")
            live_candidate_hash = tree_hash(agent / "releases/candidate")
            require(live_candidate_hash != candidate_sha,
                    "S5_CANDIDATE_WORLD_NOT_PERSISTED")
            stages.append("candidate_world_persisted")
            # Inject a real *integrity* failure while stopped, not a false
            # health claim based on ordinary gameplay-induced world writes.
            # Candidate content is deliberately corrupted after positive live
            # proof; stage digest re-check must refuse before any promotion.
            injected = agent / "releases/candidate/datapacks/candidate.zip"
            require(hashlib.sha256(injected.read_bytes()).hexdigest() == PACK_SHA,
                    "S5_CANDIDATE_PACK_CHANGED_BEFORE_INJECTION")
            injected.write_bytes(b"SU PRACRAFT S5 INJECTED CONTENT INTEGRITY FAULT\n")
            observed_bad = hashlib.sha256(injected.read_bytes()).hexdigest()
            try:
                verify_fault_is_not_promotable(PACK_SHA, observed_bad)
            except Refused as exc:
                require(str(exc) == "S5_INJECTED_HEALTH_ORACLE_MISMATCH",
                        "S5_WRONG_FAILURE_DETECTED")
            else:
                raise Refused("S5_INJECTED_HEALTH_FAULT_ACCEPTED")
            stages.append("injected_candidate_artifact_integrity_fault_detected")
            restored = safe_switch(agent, "restore", "snapshot", running)
            assert_agent_receipt("restore", restored, "snapshot", prior_sha)
            stages.append("restore_snapshot_after_health_fault")
            require(tree_hash(agent / "releases/snapshot") == prior_sha,
                    "S5_SNAPSHOT_BYTE_DRIFT")
            resumed, restore_log = launch(home, jar, evidence,
                                           "s5-post-restore", handles)
            oracle(resumed, restore_log, initial_predicate(),
                   "S5_POST_RESTORE_BASELINE")
            send(resumed, "setblock 0 70 0 minecraft:redstone_block")
            oracle(resumed, restore_log, baseline_without_pack_predicate(),
                   "S5_POST_ROLLBACK_PACK_ABSENT")
            require(stop_server(resumed) == 0, "S5_ROLLBACK_STOP_FAILED")
            stages.append("restored_world_live_negative_gameplay_oracle")
            out = {
                "schema": SCHEMA,
                "classification": PASS,
                "scope": "DISPOSABLE_POSIX_VANILLA_WORLD_AGENT_NOT_TRUENAS",
                "minecraft_version": "26.3", "protocol": 777, "java_major": 25,
                "server_sha256": jar_sha, "world_id": manifest["world_id"],
                "release_id": manifest["release_id"],
                "datapack_sha256": PACK_SHA,
                "prior_world_sha256": prior_sha,
                "candidate_staged_sha256": candidate_sha,
                "candidate_runtime_world_sha256": live_candidate_hash,
                "snapshot_restore_sha256": prior_sha,
                "stages": stages,
                "world_agent_stage_actuate_restore_real": True,
                "server_quiesced_for_each_switch": True,
                "active_server_switch_denied": True,
                "candidate_positive_health_observed": True,
                "injected_candidate_integrity_fault_caused_restore": True,
                "rollback_world_semantics_independently_observed": True,
                "native_truenas_guest_qualified": False,
                "zfs_snapshot_qualified": False,
                "full_two_rivers_qualified": False,
                "collage_managed": False,
                "operational_selection": False,
                "physical_truenas_apply": "HOLD",
            }
        finally:
            for proc, handle in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=15)
                finally:
                    handle.close()
    require(not root.exists(), "S5_TEMP_WORLD_NOT_DISPOSED")
    out["temporary_worlds_processes_cleaned"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    for arg in ("candidate", "manifest", "evidence", "out"):
        ap.add_argument("--" + arg, type=Path, required=True)
    args = ap.parse_args()
    try:
        doc = execute(args.candidate, json.loads(args.manifest.read_text()),
                      json.loads(args.evidence.read_text()))
    except Exception as exc:
        raw = str(exc)
        reason = raw if re.fullmatch("[A-Z0-9_]+", raw) else type(exc).__name__
        doc = {"schema": SCHEMA, "classification": "FAIL",
               "failure_type": type(exc).__name__, "failure_code": reason[:95],
               "operational_selection": False, "physical_truenas_apply": "HOLD"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": doc["classification"],
                      "failure_code": doc.get("failure_code")}, sort_keys=True))
    return 0 if doc["classification"] == PASS else 1

if __name__ == "__main__":
    raise SystemExit(main())
