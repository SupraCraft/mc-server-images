#!/usr/bin/env python3
"""S2B: real offline Velocity 4.2.0 -> VanillaCord 2.9.0 -> vanilla 26.3 login.

Disposable loopback-only protocol identity experiment; NOT Microsoft auth, VIP,
realm entitlement, operational deployment or native TrueNAS qualification.
Shares the independently accepted OP-1 Mineflayer and Velocity implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.request
import uuid
import zipfile

from qualify_velocity_paper_263_forwarding import (
    BOT_NAME, expected_offline_uuid, run_bot, start_java, velocity_config,
)
from qualify_velocity_paper_263_link import (
    BACKEND_PORT, PROXY_PORT, Refused, graceful_stop, load_pins,
    pinned_artifact, require, wait_status,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ROOT / "spec/operational-runtime-lanes-v1.json"
VC_URL = ("https://github.com/SupraCraft/VanillaCord/releases/download/"
          "v2.9.0/supracraft-vanillacord-2.9.0.jar")
VC_SHA256 = "24e850a261dbf108e2f7ac412c34651ffae753543665ec47d5e40ff9c8981719"
VC_RELEASE_ID = 411870504
VC_ASSET_ID = 637946822
MAX_VC_BYTES = 8 * 1024 * 1024
SCHEMA = "supracraft.velocity-vanillacord-player-path/1"
PASS = "REAL_LOOPBACK_OFFLINE_VANILLACORD_FORWARDING"


def trusted_release_location(url: str) -> bool:
    from urllib.parse import urlsplit
    p = urlsplit(url)
    return (p.scheme == "https" and not p.username and not p.password
            and p.port in (None, 443) and p.hostname in {
                "github.com", "release-assets.githubusercontent.com",
                "objects.githubusercontent.com",
            })


def download_vanillacord(target: pathlib.Path) -> str:
    """Exact public release; never substitute current source or a developer build."""
    req = urllib.request.Request(VC_URL, headers={
        "User-Agent": "SupraCraft-S2B-RDTE/1.0",
        "Accept": "application/octet-stream",
    })
    require(trusted_release_location(VC_URL), "VC_RELEASE_SOURCE_UNTRUSTED")
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(req, timeout=90) as response:
        require(trusted_release_location(response.url), "VC_RELEASE_REDIRECT_UNTRUSTED")
        with target.open("wb") as stream:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                require(total <= MAX_VC_BYTES, "VC_RELEASE_TOO_LARGE")
                stream.write(chunk)
                digest.update(chunk)
    require(total == 2457878 and digest.hexdigest() == VC_SHA256,
            "VC_RELEASE_BYTES_OR_DIGEST_DRIFT")
    require(zipfile.is_zipfile(target), "VC_RELEASE_NOT_JAR")
    return digest.hexdigest()


def vanilla_config(secret: str) -> str:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", secret)), "EPHEMERAL_SECRET_INVALID")
    return "version = 2.0\nforwarding = velocity\nseecret = " + secret + "\n"


def validate_vanilla_config(content: str, secret: str) -> None:
    require(content == vanilla_config(secret), "VANILLACORD_CONFIG_READBACK_DRIFT")


def backend_usercache(home: pathlib.Path, name: str) -> str:
    path = home / "usercache.json"
    require(path.is_file(), "VANILLA_USERCACHE_MISSING")
    data = json.loads(path.read_text())
    require(type(data) is list, "VANILLA_USERCACHE_SCHEMA_DRIFT")
    rows = [row for row in data if type(row) is dict and row.get("name") == name]
    require(len(rows) == 1, "VANILLA_USERCACHE_NOT_UNIQUE")
    return str(uuid.UUID(rows[0]["uuid"]))


def backend_join_log(home: pathlib.Path, name: str, expected_uuid: str) -> bool:
    """Independent unmodified vanilla backend log, not a proxy/client assertion."""
    log = (home / "server.log").read_text(errors="replace")
    pattern = (r"UUID of player " + re.escape(name)
               + r" is ([0-9a-fA-F-]{36})")
    matches = re.findall(pattern, log)
    require(len(matches) == 1, "VANILLA_UUID_LOG_MISSING_OR_AMBIGUOUS")
    require(str(uuid.UUID(matches[0])) == expected_uuid, "VANILLA_UUID_LOG_MISMATCH")
    require(bool(re.search(re.escape(name) + r" joined the game", log)),
            "VANILLA_BACKEND_JOIN_LOG_MISSING")
    return True


def stop_vanilla(proc: subprocess.Popen) -> None:
    require(proc.poll() is None and proc.stdin is not None, "VANILLA_PREMATURE_EXIT")
    proc.stdin.write("stop\n")
    proc.stdin.flush()
    require(proc.wait(timeout=50) == 0, "VANILLA_STOP_FAILED")


def validate_discovery(discovery: dict) -> tuple[dict, str]:
    require(discovery.get("classification") == "READ_ONLY_CANDIDATES_DISCOVERED",
            "OFFICIAL_DISCOVERY_NOT_ACCEPTED")
    pins = load_pins()
    require(pins["selection"]["operational"] is False and
            pins["selection"]["physical_trueNAS_apply"] == "HOLD",
            "RDTE_HOLD_GUARD_FAILED")
    vanilla = discovery["stable"]["vanilla"]
    policy = json.loads(POLICY.read_text())
    desired = policy["stable"]["minecraft_java"]
    require(vanilla["approved_release"] == "26.3" and
            desired["version"] == "26.3" and desired["protocol"] == 777 and
            desired["java_major"] == 25 and
            re.fullmatch(r"[0-9a-f]{64}", desired["server_sha256"]) is not None,
            "MOJANG_263_POLICY_DRIFT")
    return pins, desired["server_sha256"]


def execute(discovery: dict) -> dict:
    pins, minecraft_sha = validate_discovery(discovery)
    with tempfile.TemporaryDirectory(prefix="supracraft-s2b-vanillacord-") as td:
        root = pathlib.Path(td)
        server = root / "vanilla"
        proxy = root / "velocity"
        server.mkdir()
        proxy.mkdir()
        vcjar = root / "supracraft-vanillacord-2.9.0.jar"
        vc_digest = download_vanillacord(vcjar)
        vjar = proxy / "velocity.jar"
        velocity_digest = pinned_artifact(discovery["stable"]["velocity"],
                                           pins["velocity"], vjar)
        with zipfile.ZipFile(vjar) as archive:
            template = archive.read("default-velocity.toml").decode("utf-8")
        vconfig = velocity_config(template)
        # Patch exact original Mojang 26.3, then independently hash the retained
        # original input JAR. No patched Mojang JAR is published or uploaded.
        completed = subprocess.run(
            ["java", "-jar", str(vcjar), "26.3"],
            cwd=root, capture_output=True, text=True, timeout=240,
        )
        require(completed.returncode == 0, "VANILLACORD_PATCH_FAILED")
        original = root / "in/26.3.jar"
        patched = root / "out/26.3.jar"
        require(original.is_file() and patched.is_file(),
                "VANILLA_PATCH_INPUT_OR_OUTPUT_MISSING")
        require(hashlib.sha256(original.read_bytes()).hexdigest() == minecraft_sha,
                "MOJANG_SERVER_SHA256_MISMATCH")
        require(zipfile.is_zipfile(patched), "PATCHED_SERVER_NOT_JAR")
        patched_digest = hashlib.sha256(patched.read_bytes()).hexdigest()
        server_jar = server / "server.jar"
        shutil.copyfile(patched, server_jar)
        (server / "eula.txt").write_text("eula=true\n")
        (server / "server.properties").write_text(
            f"server-ip=127.0.0.1\nserver-port={BACKEND_PORT}\n"
            "online-mode=false\nenforce-secure-profile=false\n"
            "network-compression-threshold=-1\n"
            "white-list=false\nenforce-whitelist=false\n"
            "max-players=3\nview-distance=2\nsimulation-distance=2\n"
            "spawn-protection=0\nenable-rcon=false\nenable-query=false\n"
            "motd=SUPRACRAFT_S2B_VANILLA\n"
        )
        actual_secret = os.urandom(32).hex()
        wrong_secret = os.urandom(32).hex()
        vconf = server / "vanillacord.txt"
        vconf.write_text(vanilla_config(actual_secret))
        vconf.chmod(0o600)
        validate_vanilla_config(vconf.read_text(), actual_secret)
        (proxy / "velocity.toml").write_text(vconfig)
        secret_file = proxy / "forwarding.secret"
        secret_file.write_text(wrong_secret + "\n")
        secret_file.chmod(0o600)
        handles = []
        try:
            backend = start_java(server_jar, server, handles)
            wait_status(backend, BACKEND_PORT, "VANILLACORD_263")
            bypass = run_bot(BACKEND_PORT, False, "DIRECT_VANILLA_BACKEND")
            # Wrong credential is an actual running proxy, not a mocked parser.
            bad_proxy = start_java(vjar, proxy, handles)
            wait_status(bad_proxy, PROXY_PORT, "VELOCITY_WRONG_SECRET")
            mismatch = run_bot(PROXY_PORT, False, "WRONG_VANILLACORD_SECRET")
            graceful_stop(bad_proxy, "VELOCITY")
            secret_file.write_text(actual_secret + "\n")
            secret_file.chmod(0o600)
            good_proxy = start_java(vjar, proxy, handles)
            wait_status(good_proxy, PROXY_PORT, "VELOCITY_CORRECT_SECRET")
            good = run_bot(PROXY_PORT, True, "CORRECT_VANILLACORD_SECRET")
            require(good["username"] == BOT_NAME, "PROXY_CLIENT_NAME_DRIFT")
            require((server / "world/level.dat").is_file(), "VANILLA_WORLD_NOT_CREATED")
            graceful_stop(good_proxy, "VELOCITY")
            stop_vanilla(backend)
            expected = expected_offline_uuid(BOT_NAME)
            observed = backend_usercache(server, BOT_NAME)
            require(observed == expected, "VANILLA_FORWARDED_UUID_MISMATCH")
            require(backend_join_log(server, BOT_NAME, expected),
                    "VANILLA_INDEPENDENT_JOIN_NOT_OBSERVED")
            outcome = {
                "schema": SCHEMA,
                "classification": PASS,
                "scope": "OFFLINE_LOOPBACK_PROTOCOL_ONLY",
                "source": {
                    "minecraft_version": "26.3", "minecraft_protocol": 777,
                    "java_major": 25, "mojang_server_sha256": minecraft_sha,
                    "vanillacord_version": "2.9.0", "vanillacord_sha256": vc_digest,
                    "vanillacord_release_id": VC_RELEASE_ID,
                    "vanillacord_asset_id": VC_ASSET_ID,
                    "patched_server_sha256": patched_digest,
                    "velocity_version": "4.2.0", "velocity_build": 30,
                    "velocity_sha256": velocity_digest,
                },
                "backend_log_join_independently_observed": True,
                "backend_usercache_uuid": observed,
                "backend_log_uuid_matches_expected": True,
                "expected_proxy_offline_uuid": expected,
                "forwarded_username_matches_expected": True,
                "forwarded_uuid_matches_expected": True,
                "direct_backend_denied": not bypass["spawned"],
                "wrong_secret_denied": not mismatch["spawned"],
                "proxy_player_spawned": good["spawned"],
                "world_level_dat_observed": True,
                "test_network": "127.0.0.1_only",
                "account_authentication_qualified": False,
                "vip_admission_qualified": False,
                "realm_isolation_qualified": False,
                "operational_selection": False,
                "physical_truenas_apply": "HOLD",
            }
        finally:
            for proc, handle in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=20)
                finally:
                    handle.close()
    require(not root.exists(), "RDTE_TEMPORARY_WORLD_RESIDUE")
    outcome["temporary_runtime_disposed"] = True
    outcome["temporary_secrets_disposed"] = True
    return outcome


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    args = ap.parse_args()
    try:
        result = execute(json.loads(args.discovery.read_text()))
    except Exception as exc:
        # Emit no Java console logs, backend data, secret, world or JAR bytes.
        reason = str(exc)
        code = reason if re.fullmatch(r"[A-Z0-9_]+", reason) else type(exc).__name__
        result = {"schema": SCHEMA, "classification": "FAIL",
                  "failure_type": type(exc).__name__, "failure_code": code[:100],
                  "temporary_runtime_disposed": False,
                  "operational_selection": False, "physical_truenas_apply": "HOLD"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure_code": result.get("failure_code")}, sort_keys=True))
    return 0 if result["classification"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
