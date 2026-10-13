#!/usr/bin/env python3
"""S3: causal equivalence, exact same world baseline, direct vs proxied vanilla.
RDTE offline localhost only. Reuse S2B and OP3C oracles; no operational APPLY.
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
import tempfile
import zipfile

from minecraft_world_agent import tree_hash
from probe_core_restoration_datapack_26_3 import (
    BOT_NAME, initial_predicate, restored_predicate, send, stop_server, wait_file,
)
from qualify_vanilla_datapack_player_263 import (
    WORKER, configure_fixture, validate_client_result,
)
from qualify_vanilla_world_artifact_activation_263 import (
    oracle, require, validate_candidate,
)
from qualify_velocity_vanillacord_263_forwarding import (
    VC_SHA256, backend_join_log, backend_usercache, download_vanillacord,
    expected_offline_uuid, validate_discovery, vanilla_config, velocity_config,
)
from qualify_velocity_paper_263_forwarding import run_bot, start_java
from qualify_velocity_paper_263_link import (
    BACKEND_PORT, PROXY_PORT, graceful_stop, pinned_artifact, wait_status,
)
from smoke_vanilla_runtime import download_verified_server

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "supracraft.s3-vanilla-direct-proxy-equivalence/1"
PASS = "REAL_VANILLA_DIRECT_PROXY_CAUSAL_EQUIVALENCE"
PACK_SHA = "da25005e8729e6f013f7108ac5b8869dd46323befc78efdae18221b26cafe5f8"


def same_baseline(expected: str, actual: str) -> None:
    require(len(expected) == 64 and expected == actual, "S3_BASELINE_HASH_DRIFT")


def semantic_equivalence(a: dict, b: dict, expected_uuid: str) -> dict:
    fields = ("username", "requested_version", "negotiated_version", "protocol",
              "server_join_independently_observed", "client_saw_air_before",
              "client_saw_redstone_after", "action", "offline_mode")
    require(all(k in a and k in b and a[k] == b[k] for k in fields),
            "S3_CLIENT_SEMANTIC_MISMATCH")
    require(a["username"] == BOT_NAME and a["requested_version"] ==
            a["negotiated_version"] == "26.3" and a["protocol"] == 777 and
            a["action"] == "mineflayer.placeBlock" and
            all(a[k] is True for k in fields[4:7]) and a["offline_mode"] is True,
            "S3_CLIENT_ACTION_NOT_ACCEPTED")
    require(a.get("backend_uuid") == b.get("backend_uuid") == expected_uuid,
            "S3_BACKEND_IDENTITY_MISMATCH")
    require(all(a.get(k) is True and b.get(k) is True
                for k in ("world_effect", "rollback_reobserved")),
            "S3_BACKEND_EFFECT_OR_RESTORE_MISMATCH")
    return {"username": BOT_NAME, "uuid": expected_uuid, "protocol": 777,
            "client_before": "air", "client_after": "redstone_block",
            "server_access_after": "air", "server_feedback_after": "sea_lantern",
            "offline_protocol_only": True}


def config() -> str:
    return (f"server-ip=127.0.0.1\nserver-port={BACKEND_PORT}\n"
            "online-mode=false\nenforce-secure-profile=false\n"
            "network-compression-threshold=-1\nwhite-list=false\n"
            "enforce-whitelist=false\nmax-players=3\nview-distance=3\n"
            "simulation-distance=2\nspawn-protection=0\nenable-rcon=false\n"
            "enable-query=false\ngenerate-structures=false\n"
            "level-seed=4242424242\nsync-chunk-writes=true\n"
            "motd=SUPRACRAFT_S3_VANILLA\n")


def clone(home: Path, jar: Path, common: Path, baseline_sha: str) -> None:
    home.mkdir()
    shutil.copyfile(jar, home / "server.jar")
    (home / "eula.txt").write_text("eula=true\n")
    (home / "server.properties").write_text(config())
    shutil.copytree(common, home / "world", symlinks=False)
    same_baseline(baseline_sha, tree_hash(home / "world"))


def stage_check(home: Path) -> None:
    file = home / "world/datapacks/candidate.zip"
    require(file.is_file() and hashlib.sha256(file.read_bytes()).hexdigest() == PACK_SHA,
            "S3_DATAPACK_STAGE_OR_DIGEST_DRIFT")


def player_action(root: Path, backend: subprocess.Popen, log: Path,
                  port: int, label: str) -> dict:
    ready = root / (label + ".ready")
    out = root / (label + ".json")
    env = dict(os.environ, MC_PORT=str(port),
               BOT_READY_FILE=str(ready), BOT_RESULT_FILE=str(out))
    bot = subprocess.Popen(["node", str(WORKER)], cwd=ROOT, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_file(ready, bot, 50)
        send(backend, "gamemode survival " + BOT_NAME)
        send(backend, "give " + BOT_NAME + " minecraft:redstone_block 1")
        send(backend, "tp " + BOT_NAME + " 0.5 70.0 2.5 180 0")
        try:
            rc = bot.wait(timeout=85)
        except subprocess.TimeoutExpired:
            raise RuntimeError("S3_CLIENT_ACTION_TIMEOUT")
        require(out.is_file(), "S3_CLIENT_RESULT_MISSING")
        return validate_client_result(
            json.loads(out.read_text()), rc, log.read_text(errors="replace"))
    finally:
        if bot.poll() is None:
            bot.kill()
            bot.wait(timeout=10)


def lane(root: Path, home: Path, common: Path, baseline_sha: str,
         handles: list, name: str, vjar: Path | None = None,
         proxy: Path | None = None, vconfig: str | None = None) -> dict:
    """Two independent backend experiments; same exact immutable world input."""
    same_baseline(baseline_sha, tree_hash(home / "world"))
    stage_check(home)
    secret = None
    if proxy is not None:
        require(vjar is not None and vconfig is not None, "S3_PROXY_CONFIG_MISSING")
        secret = os.urandom(32).hex()
        (home / "vanillacord.txt").write_text(vanilla_config(secret))
        (proxy / "velocity.toml").write_text(vconfig)
        key = proxy / "forwarding.secret"
        key.write_text(secret + "\n")
        key.chmod(0o600)
    backend = start_java(home / "server.jar", home, handles)
    wait_status(backend, BACKEND_PORT, name + "_BACKEND")
    active = None
    if proxy is not None:
        bypass = run_bot(BACKEND_PORT, False, "S3_PROXY_BACKEND_BYPASS")
        require(bypass["spawned"] is False, "S3_BACKEND_BYPASS_NOT_DENIED")
        active = start_java(vjar, proxy, handles)
        wait_status(active, PROXY_PORT, name + "_PROXY")
    log = home / "server.log"
    oracle(backend, log, initial_predicate(), name + "_BEFORE")
    action = player_action(root, backend, log,
                           PROXY_PORT if proxy is not None else BACKEND_PORT, name)
    oracle(backend, log, restored_predicate(), name + "_AFTER")
    require(stop_server(backend) == 0, "S3_SAVE_STOP_FAILED")
    if active is not None:
        graceful_stop(active, "VELOCITY")
    uuid = expected_offline_uuid(BOT_NAME)
    require(backend_usercache(home, BOT_NAME) == uuid, "S3_UUID_CACHE_MISMATCH")
    require(backend_join_log(home, BOT_NAME, uuid), "S3_BACKEND_JOIN_MISSING")
    require((home / "world/level.dat").is_file(), "S3_WORLD_NOT_SAVED")
    after_sha = tree_hash(home / "world")
    require(after_sha != baseline_sha, "S3_PLAYER_WORLD_DID_NOT_CHANGE")
    action["backend_uuid"] = uuid
    action["world_effect"] = True
    require(backend.poll() == 0, "S3_REWIND_WITH_ACTIVE_SERVER_DENIED")
    shutil.rmtree(home / "world")
    shutil.copytree(common, home / "world", symlinks=False)
    same_baseline(baseline_sha, tree_hash(home / "world"))
    # Reboot the restored world and re-observe its baseline state independently.
    backend = start_java(home / "server.jar", home, handles)
    wait_status(backend, BACKEND_PORT, name + "_RESTORED")
    oracle(backend, home / "server.log", initial_predicate(), name + "_RESTORE")
    require(stop_server(backend) == 0, "S3_RESTORED_WORLD_STOP_FAILED")
    action["rollback_reobserved"] = True
    return {"action": action,
            "world_hash_after_action_sha256": after_sha,
            "baseline_restored_sha256": baseline_sha,
            "backend_bypass_denied": proxy is not None}


def execute(candidate: Path, manifest: dict,
            evidence: dict, discovery: dict) -> dict:
    accepted = validate_candidate(candidate, manifest)
    require(accepted["sha256"] == PACK_SHA, "S3_SOURCE_PACK_DIGEST_DRIFT")
    pins, sha = validate_discovery(discovery)
    v = evidence["artifact_version_json"]
    require(v["id"] == "26.3" and v["protocol_version"] == 777 and
            v["java_version"] == 25 and evidence["server_artifact"]["sha256"] == sha,
            "S3_MOJANG_POLICY_DRIFT")
    with tempfile.TemporaryDirectory(prefix="supracraft-s3-semantic-") as td:
        root = Path(td)
        original = root / "mojang.jar"
        download_verified_server(evidence, original)
        require(hashlib.sha256(original.read_bytes()).hexdigest() == sha,
                "S3_OFFICIAL_JAR_DIGEST_DRIFT")
        vcjar = root / "vanillacord.jar"
        vcsha = download_vanillacord(vcjar)
        require(vcsha == VC_SHA256, "S3_VC_DIGEST_DRIFT")
        p = subprocess.run(["java", "-jar", str(vcjar), "26.3"], cwd=root,
                           capture_output=True, text=True, timeout=240)
        patched = root / "out/26.3.jar"
        patched_input = root / "in/26.3.jar"
        require(p.returncode == 0 and patched.is_file() and
                patched_input.is_file() and zipfile.is_zipfile(patched) and
                hashlib.sha256(patched_input.read_bytes()).hexdigest() == sha,
                "S3_PATCHED_VANILLA_INTEGRITY")
        proxy = root / "velocity"
        proxy.mkdir()
        vjar = proxy / "velocity.jar"
        vsha = pinned_artifact(discovery["stable"]["velocity"], pins["velocity"], vjar)
        with zipfile.ZipFile(vjar) as zf:
            vconfig = velocity_config(zf.read("default-velocity.toml").decode("utf-8"))
        baseline = root / "baseline"
        baseline.mkdir()
        shutil.copyfile(original, baseline / "server.jar")
        (baseline / "eula.txt").write_text("eula=true\n")
        (baseline / "server.properties").write_text(config())
        handles = []
        try:
            proc = start_java(baseline / "server.jar", baseline, handles)
            wait_status(proc, BACKEND_PORT, "S3_BASELINE")
            configure_fixture(proc, baseline / "server.log")
            require(stop_server(proc) == 0, "S3_BASELINE_STOP_FAILED")
            common = root / "common"
            shutil.copytree(baseline / "world", common, symlinks=False)
            stage = common / "datapacks/candidate.zip"
            require(not stage.exists(), "S3_SOURCE_CANDIDATE_PRESENT")
            stage.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, stage)
            require(hashlib.sha256(stage.read_bytes()).hexdigest() == PACK_SHA,
                    "S3_SOURCE_CANDIDATE_CORRUPT")
            common_sha = tree_hash(common)
            direct = root / "direct"
            proxied = root / "proxied"
            clone(direct, original, common, common_sha)
            clone(proxied, patched, common, common_sha)
            a = lane(root, direct, common, common_sha, handles, "S3_DIRECT")
            b = lane(root, proxied, common, common_sha, handles, "S3_PROXIED",
                     vjar=vjar, proxy=proxy, vconfig=vconfig)
            projection = semantic_equivalence(
                a["action"], b["action"], expected_offline_uuid(BOT_NAME))
            result = {
                "schema": SCHEMA, "classification": PASS,
                "scope": "OFFLINE_LOOPBACK_GAMEPLAY_ONLY",
                "source": {"vanilla": "26.3", "java": 25, "protocol": 777,
                           "mojang_sha256": sha, "vanillacord_sha256": vcsha,
                           "patched_server_sha256": hashlib.sha256(patched.read_bytes()).hexdigest(),
                           "velocity_version": "4.2.0", "velocity_build": 30,
                           "velocity_sha256": vsha, "datapack_sha256": PACK_SHA},
                "world_id": manifest["world_id"], "release_id": manifest["release_id"],
                "shared_baseline_sha256": common_sha,
                "direct": a, "proxied": b, "semantic_projection": projection,
                "same_baseline_world": True, "equivalent_gameplay_effect": True,
                "direct_backend_denied_in_proxied_lane": b["backend_bypass_denied"],
                "both_worlds_rollback_reobserved": True,
                "auth_account_qualified": False, "vip_qualified": False,
                "human_automation_agent_parity_qualified": False,
                "collage_deployment_qualified": False, "truenas_guest_qualified": False,
                "operational_selection": False, "physical_truenas_apply": "HOLD",
            }
        finally:
            for proc, stream in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=15)
                finally:
                    stream.close()
    require(not root.exists(), "S3_TEMP_RUNTIME_NOT_DISPOSED")
    result["temporary_runtimes_worlds_credentials_disposed"] = True
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    for arg in ("candidate", "manifest", "evidence", "discovery", "out"):
        ap.add_argument("--" + arg, required=True, type=Path)
    a = ap.parse_args()
    try:
        result = execute(a.candidate, json.loads(a.manifest.read_text()),
                         json.loads(a.evidence.read_text()),
                         json.loads(a.discovery.read_text()))
    except Exception as ex:
        code = str(ex)
        safe = code if re.fullmatch("[A-Z0-9_]+", code) else type(ex).__name__
        result = {"schema": SCHEMA, "classification": "FAIL",
                  "failure_type": type(ex).__name__, "failure_code": safe[:100],
                  "operational_selection": False, "physical_truenas_apply": "HOLD"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure_code": result.get("failure_code")}, sort_keys=True))
    return 0 if result["classification"] == PASS else 1

if __name__ == "__main__":
    raise SystemExit(main())
