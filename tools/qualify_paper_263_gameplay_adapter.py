#!/usr/bin/env python3
"""S4 Paper 26.3 adapter: real direct-vs-proxied player/world gameplay.

Independent bounded Paper qualification. Reuses accepted S3 gameplay/world
oracles and S2A Paper config; no inherited vanilla gameplay acceptance.
Offline-loopback ephemeral public CI ONLY; physical TrueNAS APPLY HOLD.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
import yaml

from minecraft_world_agent import tree_hash
from probe_core_restoration_datapack_26_3 import (
    BOT_NAME, initial_predicate, restored_predicate, stop_server,
)
from qualify_vanilla_datapack_player_263 import configure_fixture
from qualify_vanilla_direct_proxy_263_equivalence import (
    PACK_SHA, clone, player_action, same_baseline, semantic_equivalence, stage_check, config,
)
from qualify_vanilla_world_artifact_activation_263 import (
    Refused, oracle, require, validate_candidate,
)
from qualify_velocity_paper_263_forwarding import (
    expected_offline_uuid, patch_paper_global, run_bot, start_java, velocity_config,
)
from qualify_velocity_paper_263_link import (
    BACKEND_PORT, PROXY_PORT, graceful_stop, load_pins,
    pinned_artifact, wait_status,
)
from qualify_velocity_vanillacord_263_forwarding import backend_join_log, backend_usercache

SCHEMA = "supracraft.s4-paper263-direct-proxy-gameplay/1"
PASS = "REAL_PAPER263_GAMEPLAY_ADAPTER_DIRECT_PROXY"


def paper_mode(path: Path, secret: str | None) -> None:
    require(path.is_file(), "S4_PAPER_GLOBAL_CONFIG_ABSENT")
    data = yaml.safe_load(path.read_text())
    require(type(data) is dict and type(data.get("proxies")) is dict and
            type(data["proxies"].get("velocity")) is dict, "S4_PAPER_SCHEMA_DRIFT")
    record = data["proxies"]["velocity"]
    require({"enabled", "online-mode", "secret"}.issubset(record),
            "S4_PAPER_KEYS_MISSING")
    if secret is None:
        require(record["enabled"] is False, "S4_DIRECT_BACKEND_PROXY_MODE_DRIFT")
    else:
        require(record["enabled"] is True and
                record["online-mode"] is False and
                record["secret"] == secret, "S4_PAPER_FORWARDING_CONFIG_DRIFT")


def scoped_pins(discovery: dict, manifest: dict) -> dict:
    require(discovery.get("classification") == "READ_ONLY_CANDIDATES_DISCOVERED",
            "S4_OFFICIAL_DISCOVERY_REFUSED")
    pins = load_pins()
    require(pins["paper"]["minecraft_version"] == "26.3"
            and pins["paper"]["build"] == 177
            and pins["velocity"]["version"] == "4.2.0"
            and pins["velocity"]["build"] == 30,
            "S4_PIN_DRIFT")
    require(pins["selection"]["operational"] is False
            and pins["selection"]["physical_trueNAS_apply"] == "HOLD",
            "S4_OPERATIONAL_HOLD_DRIFT")
    require(manifest.get("backend") == "vanilla"
            and manifest.get("minecraft_version") == "26.3"
            and manifest.get("world_id") == "lantern-rdte",
            "S4_DATAPACK_SOURCE_SCOPE_DRIFT")
    return pins


def paper_lane(root: Path, home: Path, common: Path, baseline: str,
               handles: list, label: str,
               proxy: Path | None = None, vjar: Path | None = None,
               vconf: str | None = None) -> dict:
    same_baseline(baseline, tree_hash(home / "world"))
    stage_check(home)
    paper_global = home / "config/paper-global.yml"
    bad_denied = False
    bypass_denied = False
    if proxy is None:
        paper_mode(paper_global, None)
    else:
        require(vjar is not None and vconf is not None,
                "S4_PROXY_ASSEMBLY_INCOMPLETE")
        secret, wrong = os.urandom(32).hex(), os.urandom(32).hex()
        patch_paper_global(paper_global, secret)
        paper_mode(paper_global, secret)
        (proxy / "velocity.toml").write_text(vconf)
        key = proxy / "forwarding.secret"
        key.write_text(wrong + "\n")
        key.chmod(0o600)
    backend = start_java(home / "server.jar", home, handles)
    wait_status(backend, BACKEND_PORT, label + "_BACKEND")
    active_proxy = None
    if proxy is not None:
        bypass_denied = run_bot(BACKEND_PORT, False, label + "_DIRECT_BYPASS")["spawned"] is False
        require(bypass_denied, "S4_DIRECT_BYPASS_NOT_DENIED")
        active_proxy = start_java(vjar, proxy, handles)
        wait_status(active_proxy, PROXY_PORT, label + "_BAD_SECRET")
        bad_denied = run_bot(PROXY_PORT, False, label + "_WRONG_SECRET")["spawned"] is False
        require(bad_denied, "S4_WRONG_SECRET_NOT_DENIED")
        graceful_stop(active_proxy, "VELOCITY")
        key.write_text(secret + "\n")
        active_proxy = start_java(vjar, proxy, handles)
        wait_status(active_proxy, PROXY_PORT, label + "_GOOD_SECRET")
    log = home / "server.log"
    oracle(backend, log, initial_predicate(), label + "_BEFORE")
    action = player_action(root, backend, log,
                           PROXY_PORT if proxy is not None else BACKEND_PORT, label)
    oracle(backend, log, restored_predicate(), label + "_AFTER")
    require(stop_server(backend) == 0, "S4_PAPER_STOP_FAILED")
    if active_proxy is not None:
        graceful_stop(active_proxy, "VELOCITY")
    expected = expected_offline_uuid(BOT_NAME)
    require(backend_usercache(home, BOT_NAME) == expected, "S4_PAPER_UUID_MISMATCH")
    require(backend_join_log(home, BOT_NAME, expected), "S4_PAPER_JOIN_MISSING")
    require((home / "world/level.dat").is_file(), "S4_WORLD_LEVEL_DAT_MISSING")
    changed = tree_hash(home / "world")
    require(changed != baseline, "S4_GAMEPLAY_WORLD_UNCHANGED")
    action["backend_uuid"] = expected
    action["world_effect"] = True
    require(backend.poll() == 0, "S4_RESTORE_ACTIVE_BACKEND_REFUSED")
    shutil.rmtree(home / "world")
    shutil.copytree(common, home / "world", symlinks=False)
    same_baseline(baseline, tree_hash(home / "world"))
    backend = start_java(home / "server.jar", home, handles)
    wait_status(backend, BACKEND_PORT, label + "_RESTART")
    oracle(backend, home / "server.log", initial_predicate(), label + "_RESTORED")
    require(stop_server(backend) == 0, "S4_RESTORE_STOP_FAILED")
    action["rollback_reobserved"] = True
    return {"action": action, "after_world_sha256": changed,
            "restored_world_sha256": baseline,
            "backend_bypass_denied": bypass_denied,
            "wrong_secret_denied": bad_denied}


def execute(candidate: Path, manifest: dict, discovery: dict) -> dict:
    source = validate_candidate(candidate, manifest)
    require(source["sha256"] == PACK_SHA, "S4_IMMUTABLE_PACK_DRIFT")
    pins = scoped_pins(discovery, manifest)
    with tempfile.TemporaryDirectory(prefix="supracraft-s4-paper-") as td:
        root = Path(td)
        jar = root / "paper.jar"
        proxy = root / "velocity"
        proxy.mkdir()
        vjar = proxy / "velocity.jar"
        psha = pinned_artifact(discovery["stable"]["paper"], pins["paper"], jar)
        vsha = pinned_artifact(discovery["stable"]["velocity"], pins["velocity"], vjar)
        with zipfile.ZipFile(vjar) as archive:
            vconf = velocity_config(archive.read("default-velocity.toml").decode("utf-8"))
        baseline = root / "baseline"
        baseline.mkdir()
        shutil.copyfile(jar, baseline / "server.jar")
        (baseline / "eula.txt").write_text("eula=true\n")
        (baseline / "server.properties").write_text(config())
        handles = []
        try:
            backend = start_java(baseline / "server.jar", baseline, handles)
            wait_status(backend, BACKEND_PORT, "S4_PAPER_BASELINE")
            configure_fixture(backend, baseline / "server.log")
            require(stop_server(backend) == 0, "S4_BASELINE_STOP_FAILED")
            paper_mode(baseline / "config/paper-global.yml", None)
            common = root / "common"
            shutil.copytree(baseline / "world", common, symlinks=False)
            staged = common / "datapacks/candidate.zip"
            require(not staged.exists(), "S4_CANDIDATE_ALREADY_PRESENT")
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, staged)
            require(hashlib.sha256(staged.read_bytes()).hexdigest() == PACK_SHA,
                    "S4_CANDIDATE_STAGE_DRIFT")
            baseline_sha = tree_hash(common)
            direct, proxied = root / "direct", root / "proxied"
            for path in (direct, proxied):
                clone(path, jar, common, baseline_sha)
                shutil.copytree(baseline / "config", path / "config", symlinks=False)
                paper_mode(path / "config/paper-global.yml", None)
            a = paper_lane(root, direct, common, baseline_sha, handles, "S4_DIRECT")
            b = paper_lane(root, proxied, common, baseline_sha, handles,
                           "S4_PROXY", proxy=proxy, vjar=vjar, vconf=vconf)
            semantic = semantic_equivalence(
                a["action"], b["action"], expected_offline_uuid(BOT_NAME))
            output = {
                "schema": SCHEMA, "classification": PASS,
                "scope": "OFFLINE_PAPER_GAMEPLAY_ONLY",
                "source": {"paper_version": "26.3", "paper_build": 177,
                           "paper_sha256": psha, "protocol": 777,
                           "velocity_version": "4.2.0", "velocity_build": 30,
                           "velocity_sha256": vsha, "datapack_sha256": PACK_SHA},
                "world_id": manifest["world_id"],
                "release_id": manifest["release_id"],
                "shared_baseline_sha256": baseline_sha,
                "direct_paper": a, "proxied_paper": b,
                "semantic_projection": semantic,
                "same_world_baseline": True, "direct_and_proxied_effects": True,
                "backend_bypass_denied": b["backend_bypass_denied"],
                "wrong_secret_denied": b["wrong_secret_denied"],
                "both_worlds_restored": True,
                "microsoft_auth_qualified": False, "vip_qualified": False,
                "all_vanilla_semantics_qualified": False,
                "stock_client_qualified": False, "collage_managed": False,
                "native_truenas_guest_qualified": False,
                "operational_selection": False, "physical_truenas_apply": "HOLD",
            }
        finally:
            for proc, handle in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=15)
                finally:
                    handle.close()
    require(not root.exists(), "S4_TEMP_RESIDUE")
    output["temporary_processes_worlds_secrets_disposed"] = True
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    for key in ("candidate", "manifest", "discovery", "out"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    try:
        result = execute(a.candidate, json.loads(a.manifest.read_text()),
                         json.loads(a.discovery.read_text()))
    except Exception as e:
        value = str(e)
        code = value if re.fullmatch(r"[A-Z0-9_]+", value) else type(e).__name__
        result = {"schema": SCHEMA, "classification": "FAIL",
                  "failure_type": type(e).__name__, "failure_code": code[:100],
                  "operational_selection": False, "physical_truenas_apply": "HOLD"}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure_code": result.get("failure_code")}, sort_keys=True))
    return 0 if result["classification"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
