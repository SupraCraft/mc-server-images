#!/usr/bin/env python3
"""OP-3C: genuine offline-protocol Mineflayer action on exact exported vanilla datapack.

Owns only a temporary vanilla world; uses shared OP-3 candidate/rollback
oracles and existing standalone Mineflayer core-placement worker.
Not stock Mojang client, account authentication, COLLAGE orchestration,
TrueNAS or Two Rivers operational gameplay qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import uuid
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from minecraft_world_agent import tree_hash
from qualify_vanilla_263_oci_disposable import stopped_world_region_witness
from probe_core_restoration_datapack_26_3 import (
    BOT_NAME, wait_file, send, initial_predicate, restored_predicate, stop_server
)
from qualify_vanilla_world_artifact_activation_263 import (
    Refused, PORT, baseline_without_pack_predicate, digest, launch, oracle,
    require, server_config, validate_candidate
)
from smoke_vanilla_runtime import download_verified_server

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CLIENT = "26.3"
EXPECTED_PROTOCOL = 777
WORKER = ROOT / "tools/probe_mineflayer_core_place.js"


def offline_bot_uuid(username: str = BOT_NAME) -> str:
    """Minecraft Java offline-mode UUIDv3, never an online account identity."""
    import hashlib as _hashlib
    return str(uuid.UUID(bytes=_hashlib.md5(
        ("OfflinePlayer:" + username).encode()).digest(), version=3))


def install_disposable_operator(home: Path) -> None:
    """Only one exact synthetic bot operator in temporary offline fixture."""
    (home / "ops.json").write_text(json.dumps([{
        "uuid": offline_bot_uuid(),
        "name": BOT_NAME,
        "level": 4,
        "bypassesPlayerLimit": False,
    }], sort_keys=True)+"\n")




def validate_client_result(result: dict, exit_code: int,
                           joined_log: str, *, operator_setup: bool = False) -> dict:
    require(type(result) is dict and
            result.get("schema") == "supracraft.mineflayer-core-placement/v0.1",
            "PLAYER_RESULT_SCHEMA")
    require(exit_code == 0 and result.get("placed") is True and
            result.get("error") is None and
            result.get("before") == "air" and
            result.get("after") == "redstone_block" and
            result.get("core_item") == "redstone_block",
            "PLAYER_PLACEMENT_NOT_PROVED")
    require(result.get("requested_version") == EXPECTED_CLIENT and
            result.get("protocol_version") == EXPECTED_PROTOCOL and
            result.get("negotiated_version") == EXPECTED_CLIENT,
            "PLAYER_PROTOCOL_DRIFT")
    milestones = result.get("milestones", {})
    require(type(milestones) is dict and
            all(isinstance(milestones.get(k), int)
                for k in ("connect", "login", "spawn", "placed")),
            "PLAYER_LOGIN_OR_SPAWN_UNPROVEN")
    require(BOT_NAME + " joined the game" in joined_log,
            "PLAYER_BACKEND_JOIN_NOT_OBSERVED")
    if operator_setup:
        require(result.get("operator_fixture_source") ==
                    "mineflayer_signed_chat_commands" and
                isinstance(milestones.get("operator_commands_sent"), int) and
                milestones["spawn"] <= milestones["operator_commands_sent"]
                <= milestones["placed"],
                "OFFLINE_OPERATOR_BOT_COMMANDS_UNPROVEN")
    return {
        "username": BOT_NAME,
        "requested_version": result["requested_version"],
        "negotiated_version": result["negotiated_version"],
        "protocol": result["protocol_version"],
        "server_join_independently_observed": True,
        "client_saw_air_before": True,
        "client_saw_redstone_after": True,
        "action": "mineflayer.placeBlock",
        "offline_mode": True,
    }


def configure_fixture(proc: subprocess.Popen, log: Path) -> None:
    send(proc, "forceload add 0 0")
    send(proc, "fill -2 69 -2 4 69 3 minecraft:stone")
    send(proc, "fill -2 70 -2 4 72 3 minecraft:air")
    send(proc, "setblock 0 70 0 minecraft:air")
    send(proc, "setblock 2 70 0 minecraft:iron_bars")
    send(proc, "setblock 1 70 1 minecraft:black_concrete")
    oracle(proc, log, initial_predicate(), "OP3C_FIXTURE_BASELINE")


def player_places_core(root: Path, proc: subprocess.Popen,
                       server_log: Path, stage: str, *,
                       operator_setup: bool = False) -> dict:
    ready = root / (stage + "-bot.ready")
    result_file = root / (stage + "-bot-result.json")
    env = dict(os.environ, MC_PORT=str(PORT),
               BOT_READY_FILE=str(ready), BOT_RESULT_FILE=str(result_file),
               BOT_OPERATOR_SETUP="1" if operator_setup else "0")
    client = subprocess.Popen(
        ["node", str(WORKER)],
        cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    output = ""
    try:
        wait_file(ready, client, 45)
        if not operator_setup:
            send(proc, "gamemode survival " + BOT_NAME)
            send(proc, "give " + BOT_NAME + " minecraft:redstone_block 1")
            send(proc, "tp " + BOT_NAME + " 0.5 70.0 2.5 180 0")
        try:
            output, _ = client.communicate(timeout=75)
        except subprocess.TimeoutExpired as e:
            raise Refused("PLAYER_CORE_ACTION_TIMEOUT_" + stage) from e
        require(result_file.is_file(), "PLAYER_RESULT_ABSENT_" + stage)
        result = json.loads(result_file.read_text())
        return validate_client_result(result, client.returncode,
                                      server_log.read_text(errors="replace"),
                                      operator_setup=operator_setup)
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(timeout=10)
        # Never store worker stdout or an unsanitized world in public evidence.


def execute(candidate: Path, manifest: dict, evidence: dict, *,
            operator_setup: bool = False) -> dict:
    accepted = validate_candidate(candidate, manifest)
    info = evidence["artifact_version_json"]
    require(info.get("id") == "26.3" and
            info.get("protocol_version") == EXPECTED_PROTOCOL and
            info.get("java_version") == 25, "VANILLA_SOURCE_VERSION_DRIFT")
    require(WORKER.is_file(), "PROVEN_PLAYER_WORKER_MISSING")
    with tempfile.TemporaryDirectory(prefix="supracraft-op3c-player-") as tmp:
        root = Path(tmp)
        home = root / "server"
        home.mkdir()
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        # Keep the official pinned sha256 as an independent predicate.
        require(digest(jar.read_bytes()) == evidence["server_artifact"]["sha256"],
                "SERVER_SHA256_MISMATCH")
        server_config(home)
        if operator_setup:
            install_disposable_operator(home)
        active = home / "world"
        snapshot = root / "snapshot" / "baseline-world"
        handles = []
        stages = []
        try:
            proc, log = launch(home, jar, evidence, "client-baseline", handles)
            configure_fixture(proc, log)
            require(stop_server(proc) == 0, "BASELINE_SAVE_STOP_FAILED")
            baseline_region = stopped_world_region_witness(active)
            stages.append("baseline_quiesced")
            baseline_sha = tree_hash(active)
            snapshot.parent.mkdir()
            shutil.copytree(active, snapshot, symlinks=False)
            require(tree_hash(snapshot) == baseline_sha,
                    "BASELINE_SNAPSHOT_READBACK_MISMATCH")
            stages.append("snapshot_readback_verified")
            packs = active / "datapacks"
            packs.mkdir(exist_ok=True)
            staged = packs / "candidate.zip"
            require(not staged.exists(), "OVERWRITE_REFUSED")
            shutil.copyfile(candidate, staged)
            require(digest(staged.read_bytes()) == accepted["sha256"],
                    "STAGED_CANDIDATE_DIGEST_MISMATCH")
            stages.append("candidate_activated_offline")

            proc, log = launch(home, jar, evidence, "client-with-pack", handles)
            oracle(proc, log, initial_predicate(), "OP3C_BEFORE_PLAYER")
            candidate_player = player_places_core(root, proc, log, "candidate",
                                                  operator_setup=operator_setup)
            oracle(proc, log, restored_predicate(),
                   "OP3C_PLAYER_CAUSED_PACK_CONSEQUENCE")
            stages.append("player_placed_core_and_pack_reacted")
            require(stop_server(proc) == 0, "PLAYER_CANDIDATE_STOP_FAILED")
            candidate_region = stopped_world_region_witness(active)
            candidate_sha = tree_hash(active)
            require(candidate_sha != baseline_sha and staged.is_file(),
                    "ACTIVATED_WORLD_NOT_PERSISTED")
            stages.append("candidate_quiesced")

            # Deliberate fault response: restore exact saved pre-candidate
            # snapshot only while server is stopped.
            require(proc.poll() == 0, "ACTIVE_SERVER_RESTORE_REFUSED")
            stages.append("inject_post_client_health_failure")
            shutil.rmtree(active)
            shutil.copytree(snapshot, active, symlinks=False)
            restored_sha = tree_hash(active)
            require(restored_sha == baseline_sha and
                    not (active / "datapacks/candidate.zip").exists(),
                    "FAILED_TO_ROLLBACK_EXACT_WORLD")
            stages.append("snapshot_restored_exact_bytes")

            proc, log = launch(home, jar, evidence, "client-after-rollback", handles)
            oracle(proc, log, initial_predicate(), "OP3C_ROLLBACK_BASELINE")
            rollback_player = player_places_core(root, proc, log, "rollback",
                                                 operator_setup=operator_setup)
            oracle(proc, log, baseline_without_pack_predicate(),
                   "OP3C_SAME_PLAYER_ACTION_NO_PACK_CONSEQUENCE")
            require(stop_server(proc) == 0, "PLAYER_ROLLBACK_STOP_FAILED")
            rollback_region = stopped_world_region_witness(active)
            stages.append("same_player_action_did_not_restore_without_pack")

            return {
                "schema": "supracraft.op3c-vanilla-client-world-artifact/1",
                "classification": "REAL_OFFLINE_PLAYER_ACTION_CAUSAL_ARTIFACT_AND_ROLLBACK",
                "producer": accepted["producer"],
                "source_artifact_sha256": accepted["sha256"],
                "source_archive_size": accepted["archive_size"],
                "minecraft_version": "26.3", "protocol": 777,
                "server_sha256": evidence["server_artifact"]["sha256"],
                "world_id": manifest["world_id"],
                "release_id": manifest["release_id"],
                "baseline_world_sha256": baseline_sha,
                "standalone_stopped_region_witnesses": {
                    "baseline": baseline_region,
                    "candidate": candidate_region,
                    "rollback": rollback_region,
                },
                "candidate_world_sha256": candidate_sha,
                "restored_world_sha256": restored_sha,
                "stages": stages,
                "candidate_player": candidate_player,
                "postrollback_player": rollback_player,
                "player_caused_datapack_effect": True,
                "same_player_action_without_datapack_no_effect": True,
                "rollback_exact_snapshot_before_restart": True,
                "mineflayer_offline_protocol_qualified": True,
                "operator_bot_fixture_commands_qualified": operator_setup,
                "stock_mojang_client_qualified": False,
                "authenticated_account_qualified": False,
                "collage_deployed": False, "truenas_deployed": False,
                "full_two_rivers_world_qualified": False,
                "human_automation_agent_parity_qualified": False,
                "physical_truenas_apply": "HOLD",
                "operational_selection": False,
                "temporary_world_retired": True,
            }
        finally:
            for proc, out in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=12)
                finally:
                    out.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--operator-setup", action="store_true")
    args = p.parse_args()
    try:
        result = execute(args.candidate, json.loads(args.manifest.read_text()),
                         json.loads(args.evidence.read_text()),
                         operator_setup=args.operator_setup)
        code = 0
    except Exception as exc:
        result = {
            "schema": "supracraft.op3c-vanilla-client-world-artifact/1",
            "classification": "FAIL",
            "error_type": type(exc).__name__,
            "failure": str(exc)[:250],
            "physical_truenas_apply": "HOLD",
            "operational_selection": False,
        }
        code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure": result.get("failure")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
