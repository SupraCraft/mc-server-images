#!/usr/bin/env python3
"""OP-1 disposable real player-path qualification: Velocity 4.2.0 b30 -> Paper 26.3 b177.

This is an *offline-authentication, loopback-only protocol test*. It cannot
qualify Microsoft account verification, VIP membership or operational ingress.
Independent Mineflayer 26.3 must actually spawn via the proxy; both direct
backend and wrong-forwarding-secret paths must fail closed. No persistent world,
Docker socket, TrueNAS, secret or patched server artifact is published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import tomllib
import uuid
import zipfile

import yaml

from qualify_velocity_paper_263_link import (
    BACKEND_PORT, PROXY_PORT, Refused, graceful_stop, load_pins,
    make_velocity_config, pinned_artifact, replace_exact_value, require,
    wait_status,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOT = ROOT / "tools/probe_velocity_forwarding_263.js"
BOT_NAME = "SupraProbe263"


def velocity_config(template: str) -> str:
    """Start from exact 4.2.0 template and its previously verified loopback topology."""
    config = make_velocity_config(template)
    config = replace_exact_value(config, "player-info-forwarding-mode", '"modern"')
    parsed = tomllib.loads(config)
    require(parsed["online-mode"] is False, "RDTE_OFFLINE_PROXY_MODE_DRIFT")
    require(parsed["bind"] == f"127.0.0.1:{PROXY_PORT}", "PROXY_NOT_LOOPBACK")
    require(parsed["player-info-forwarding-mode"].lower() == "modern", "FORWARDING_MODE_DRIFT")
    require(parsed["servers"]["lobby"] == f"127.0.0.1:{BACKEND_PORT}", "BACKEND_TARGET_DRIFT")
    return config


def patch_paper_global(path: pathlib.Path, secret: str) -> None:
    """Patch Paper's real generated version-specific schema, not a guessed whole config."""
    require(path.is_file(), "PAPER_GENERATED_GLOBAL_CONFIG_MISSING")
    original = yaml.safe_load(path.read_text())
    require(type(original) is dict and type(original.get("proxies")) is dict
            and type(original["proxies"].get("velocity")) is dict,
            "PAPER_PROXY_SCHEMA_DRIFT")
    target = original["proxies"]["velocity"]
    require({"enabled", "online-mode", "secret"}.issubset(target),
            "PAPER_FORWARDING_KEYS_DRIFT")
    target["enabled"] = True
    target["online-mode"] = False  # test uses offline-mode Velocity, never operational identity
    target["secret"] = secret
    path.write_text(yaml.safe_dump(original, sort_keys=False))
    roundtrip = yaml.safe_load(path.read_text())
    require(roundtrip["proxies"]["velocity"] == target,
            "PAPER_PROXY_CONFIG_READBACK_MISMATCH")


def start_java(jar: pathlib.Path, home: pathlib.Path, handles: list) -> subprocess.Popen:
    handle = (home / (jar.stem + ".log")).open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["java", "-Xms256M", "-Xmx1536M", "-jar", str(jar), "nogui"],
        cwd=home, stdin=subprocess.PIPE, stdout=handle,
        stderr=subprocess.STDOUT, text=True,
    )
    handles.append((proc, handle))
    return proc


def run_bot(port: int, expect_spawn: bool, stage: str = 'UNNAMED') -> dict:
    env = os.environ.copy()
    env.update({"MC_FORWARD_PORT": str(port), "MC_FORWARD_USERNAME": BOT_NAME})
    done = subprocess.run(["node", str(BOT)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=65)
    try:
        row = json.loads(done.stdout.strip())
    except json.JSONDecodeError as exc:
        raise Refused("BOT_RESULT_NOT_JSON") from exc
    require(done.returncode == 0 and row.get("schema") == "supracraft.forwarding-client/1",
            "BOT_RUNTIME_FAILED")
    require(row.get("requested_version") == "26.3", "BOT_CLIENT_VERSION_DRIFT")
    diagnostic = json.dumps({
        "stage": stage, "spawned": row.get("spawned"),
        "protocol": row.get("protocol"), "kicked": str(row.get("kicked"))[:160],
        "ended": row.get("ended"), "error": str(row.get("error"))[:160],
        "timed_out": row.get("timed_out")
    }, sort_keys=True)
    require(row.get("timed_out") is False, "BOT_TIMED_OUT_" + diagnostic)
    require(row.get("spawned") is expect_spawn,
            "UNEXPECTED_BOT_SPAWN_OR_DENIAL_" + diagnostic)
    if expect_spawn:
        require(row.get("protocol") == 777, "PROXIED_BOT_PROTOCOL_DRIFT")
        require(not row.get("error") and not row.get("kicked"), "PROXY_BOT_ERROR")
    else:
        require(bool(row.get("kicked") or row.get("error") or row.get("ended")),
                "DENIAL_NOT_OBSERVED")
    return {k: row.get(k) for k in
            ("requested_version", "spawned", "protocol", "username",
             "kicked", "ended", "error")}


def expected_offline_uuid(name: str) -> str:
    """Independent Mojang offline UUID oracle for explicitly offline-mode RDTE."""
    raw = hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest()
    return str(uuid.UUID(bytes=raw, version=3))


def paper_usercache(home: pathlib.Path) -> str:
    path = home / "usercache.json"
    require(path.is_file(), "PAPER_USERCACHE_MISSING_AFTER_PROXY_LOGIN")
    rows = json.loads(path.read_text())
    matching = [row for row in rows if row.get("name") == BOT_NAME]
    require(len(matching) == 1, "PAPER_FORWARDING_PRINCIPAL_NOT_UNIQUE")
    value = str(uuid.UUID(matching[0]["uuid"]))
    return value


def execute(discovery: dict) -> dict:
    require(discovery.get("classification") == "READ_ONLY_CANDIDATES_DISCOVERED",
            "OFFICIAL_DISCOVERY_NOT_ACCEPTED")
    pins = load_pins()
    require(not pins["selection"]["operational"] and
            pins["selection"]["physical_trueNAS_apply"] == "HOLD",
            "RDTE_HOLD_GUARD_FAILED")
    with tempfile.TemporaryDirectory(prefix="supracraft-op1-forwarding-") as td:
        root = pathlib.Path(td)
        paper = root / "paper"
        velocity = root / "velocity"
        paper.mkdir()
        velocity.mkdir()
        pjar, vjar = paper / "paper.jar", velocity / "velocity.jar"
        paper_digest = pinned_artifact(discovery["stable"]["paper"], pins["paper"], pjar)
        velocity_digest = pinned_artifact(discovery["stable"]["velocity"], pins["velocity"], vjar)
        with zipfile.ZipFile(vjar) as archive:
            template = archive.read("default-velocity.toml").decode("utf-8")
        vconfig = velocity_config(template)
        (paper / "eula.txt").write_text("eula=true\n")
        (paper / "server.properties").write_text(
            f"server-ip=127.0.0.1\nserver-port={BACKEND_PORT}\n"
            "online-mode=false\nenforce-secure-profile=false\n"
            "white-list=false\nenforce-whitelist=false\n"
            "max-players=3\nview-distance=2\nsimulation-distance=2\n"
            "spawn-protection=0\nenable-rcon=false\nenable-query=false\n"
            "motd=SUPRACRAFT_OP1_PAPER\n"
        )
        secret = os.urandom(32).hex()
        wrong = os.urandom(32).hex()
        handles = []
        try:
            p = start_java(pjar, paper, handles)
            wait_status(p, BACKEND_PORT, "PAPER_BOOTSTRAP")
            graceful_stop(p, "PAPER")
            patch_paper_global(paper / "config/paper-global.yml", secret)
            p = start_java(pjar, paper, handles)
            wait_status(p, BACKEND_PORT, "PAPER_FORWARDING")
            # First, an unauthorized client goes directly to the loopback backend.
            bypass = run_bot(BACKEND_PORT, False, "DIRECT_BACKEND")
            # Second, an actual proxy with the wrong forwarding credential is denied.
            (velocity / "velocity.toml").write_text(vconfig)
            (velocity / "forwarding.secret").write_text(wrong + "\n")
            (velocity / "forwarding.secret").chmod(0o600)
            v = start_java(vjar, velocity, handles)
            wait_status(v, PROXY_PORT, "VELOCITY_BAD_SECRET")
            mismatch = run_bot(PROXY_PORT, False, "WRONG_SECRET_PROXY")
            graceful_stop(v, "VELOCITY")
            # Finally, the matching ephemeral secret allows a genuine client spawn.
            (velocity / "forwarding.secret").write_text(secret + "\n")
            v = start_java(vjar, velocity, handles)
            wait_status(v, PROXY_PORT, "VELOCITY_CORRECT_SECRET")
            good = run_bot(PROXY_PORT, True, "CORRECT_SECRET_PROXY")
            time.sleep(1)
            require((paper / "world/level.dat").is_file(), "PAPER_WORLD_MISSING")
            graceful_stop(v, "VELOCITY")
            graceful_stop(p, "PAPER")
            backend_uuid = paper_usercache(paper)
            expected_uuid = expected_offline_uuid(BOT_NAME)
            require(backend_uuid == expected_uuid,
                    "FORWARDED_OFFLINE_UUID_MISMATCH")
            backend_log = (paper / "paper.log").read_text(errors="replace")
            require(BOT_NAME in backend_log and "joined the game" in backend_log,
                    "BACKEND_SPAWN_INDEPENDENT_LOG_MISSING")
            return {
                "schema": "supracraft.velocity-paper-player-path/1",
                "classification": "REAL_LOOPBACK_OFFLINE_PLAYER_FORWARDING",
                "qualification": "RDTE_PROTOCOL_ONLY_NOT_ACCOUNT_AUTHENTICATION",
                "source": {"paper_build": 177, "paper_sha256": paper_digest,
                           "velocity_build": 30, "velocity_sha256": velocity_digest,
                           "minecraft_version": "26.3", "protocol": 777},
                "direct_backend_denied": not bypass["spawned"],
                "wrong_secret_denied": not mismatch["spawned"],
                "proxy_player_spawned": good["spawned"],
                "backend_usercache_uuid": backend_uuid,
                "expected_proxy_offline_uuid": expected_uuid,
                "forwarded_uuid_matches_independent_oracle": True,
                "backend_log_join_independently_observed": True,
                "test_network": "127.0.0.1_only",
                "account_authentication_qualified": False,
                "vip_admission_qualified": False,
                "multiple_realm_isolation_qualified": False,
                "vanillacord_qualified": False,
                "physical_truenas_apply": "HOLD",
                "operational_selection": False,
            }
        finally:
            for proc, handle in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=20)
                finally:
                    handle.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(json.loads(args.discovery.read_text()))
    except Exception as exc:
        result = {"schema": "supracraft.velocity-paper-player-path/1",
                  "classification": "FAIL",
                  "failure_type": type(exc).__name__,
                  "failure": str(exc)[:650],
                  "operational_selection": False,
                  "physical_truenas_apply": "HOLD"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure": result.get("failure")}, sort_keys=True))
    return 0 if result["classification"] == "REAL_LOOPBACK_OFFLINE_PLAYER_FORWARDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
