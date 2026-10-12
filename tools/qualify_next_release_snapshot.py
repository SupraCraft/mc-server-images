#!/usr/bin/env python3
"""Non-promotable Minecraft 26.4 official-snapshot boot canary.

Always uses a NEW temporary world, only official checksum-verified Mojang
artifacts and loopback status. Does not touch persistent worlds, deployment
credentials, VanillaCord, Paper, Velocity or any TrueNAS host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
import time
import urllib.request

from smoke_vanilla_runtime import status_query

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
UA = "SupraCraft-next-release-canary/1.0 (https://github.com/SupraCraft/mc-server-images)"
MAX_JSON = 2 * 1024 * 1024
MAX_JAR = 155 * 1024 * 1024
PORT = 25589


class CanaryRefused(Exception):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CanaryRefused(reason)


def approved_url(url: object) -> bool:
    from urllib.parse import urlparse
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return (p.scheme == "https" and p.hostname is not None and
            (p.hostname == "mojang.com" or p.hostname.endswith(".mojang.com"))
            and not p.username and not p.password)


def get_json(url: str) -> dict:
    require(approved_url(url), "UNTRUSTED_MOJANG_SOURCE")
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
    ) as stream:
        require(approved_url(stream.url), "UNTRUSTED_MOJANG_REDIRECT")
        payload = stream.read(MAX_JSON + 1)
    require(0 < len(payload) <= MAX_JSON, "MOJANG_JSON_SIZE")
    row = json.loads(payload)
    require(type(row) is dict, "MOJANG_RESPONSE_DRIFT")
    return row


def choose_snapshot(manifest: dict) -> dict:
    latest = manifest.get("latest")
    require(type(latest) is dict, "MOJANG_LATEST_MISSING")
    name = latest.get("snapshot")
    require(isinstance(name, str) and
            re.fullmatch(r"26\.4-snapshot-[0-9]+", name),
            "SNAPSHOT_NOT_IN_ADMITTED_26_4_SERIES")
    version = [v for v in manifest.get("versions", []) if
               isinstance(v, dict) and v.get("id") == name and
               v.get("type") == "snapshot"]
    require(len(version) == 1 and approved_url(version[0].get("url")),
            "SNAPSHOT_METADATA_IDENTITY_DRIFT")
    return {"version": name, "metadata": version[0]["url"]}


def choose_server(version: dict, selection: dict) -> dict:
    require(version.get("id") == selection["version"]
            and version.get("type") == "snapshot",
            "SNAPSHOT_METADATA_DRIFT")
    jdk = version.get("javaVersion", {}).get("majorVersion")
    require(type(jdk) is int and jdk == 25, "SNAPSHOT_JAVA_CHANGED")
    jar = version.get("downloads", {}).get("server")
    require(type(jar) is dict and approved_url(jar.get("url")),
            "SNAPSHOT_SERVER_URL_DRIFT")
    require(isinstance(jar.get("sha1"), str)
            and re.fullmatch("[0-9a-f]{40}", jar["sha1"])
            and type(jar.get("size")) is int and 1024 * 1024 < jar["size"] < MAX_JAR,
            "SNAPSHOT_SERVER_INTEGRITY_METADATA_DRIFT")
    return jar


def normalized_snapshot_name(name: str) -> str:
    return "-".join(name.strip().lower().split())


def run_canary(version: str, server: dict, timeout: int = 180) -> dict:
    with tempfile.TemporaryDirectory(prefix="supracraft-next-release-") as td:
        root = pathlib.Path(td)
        jar = root / "server.jar"
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        count = 0
        with urllib.request.urlopen(
            urllib.request.Request(server["url"], headers={"User-Agent": UA}),
            timeout=90
        ) as inp, jar.open("wb") as out:
            require(approved_url(inp.url), "SNAPSHOT_JAR_REDIRECT_DRIFT")
            while True:
                block = inp.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                require(count <= MAX_JAR, "SNAPSHOT_JAR_OVERSIZED")
                out.write(block)
                sha1.update(block)
                sha256.update(block)
        require(count == server["size"] and sha1.hexdigest() == server["sha1"],
                "SNAPSHOT_JAR_SHA1_OR_SIZE_MISMATCH")
        (root / "eula.txt").write_text("eula=true\n")
        (root / "server.properties").write_text(
            f"server-port={PORT}\nserver-ip=127.0.0.1\n"
            "online-mode=false\nmax-players=1\n"
            "view-distance=2\nsimulation-distance=2\n"
            "spawn-protection=0\nmax-world-size=128\n"
            "enable-rcon=false\nenable-query=false\n"
            "motd=SupraCraft NONPROMOTABLE 26.4 canary\n"
        )
        with (root / "server.log").open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(jar), "nogui"],
                cwd=root, stdin=subprocess.PIPE, stdout=log,
                stderr=subprocess.STDOUT, text=True)
            observed = None
            try:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise CanaryRefused("SNAPSHOT_SERVER_EARLY_EXIT")
                    try:
                        # Even when protocol has changed, STATUS can report its
                        # actual version to the bounded inspection client.
                        report = status_query("127.0.0.1", PORT, 777)
                        details = report.get("version", {})
                        if (isinstance(details.get("name"), str) and
                            normalized_snapshot_name(details["name"]) == version and (
                            type(details.get("protocol")) is int)
                        ):
                            observed = details
                            break
                    except (OSError, EOFError, ValueError, TimeoutError):
                        pass
                    time.sleep(1)
                require(observed is not None, "SNAPSHOT_STATUS_NOT_VERIFIED")
                require(process.stdin is not None, "SNAPSHOT_STDIN_UNAVAILABLE")
                process.stdin.write("save-all flush\nstop\n")
                process.stdin.flush()
                require(process.wait(timeout=50) == 0,
                        "SNAPSHOT_GRACEFUL_STOP_FAILED")
                require((root / "world/level.dat").is_file(),
                        "SNAPSHOT_WORLD_NOT_CREATED")
                log.flush()
                log.seek(0)
                content = log.read()
                require("Done (" in content, "SNAPSHOT_READY_MARKER_MISSING")
                require("/ERROR]" not in content,
                        "SNAPSHOT_SERVER_ERROR_LOG")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=15)
    return {
        "schema": "supracraft.next-minecraft-canary/1",
        "classification": "NONPROMOTABLE_REAL_SNAPSHOT_RUNTIME",
        "minecraft_snapshot": version,
        "observed_protocol": observed["protocol"],
        "observed_version": observed["name"],
        "jar_sha1_verified": sha1.hexdigest(),
        "jar_sha256": sha256.hexdigest(),
        "required_java": 25,
        "world": "throwaway_disposable_only",
        "operational_promotion_allowed": False,
        "persistent_world_mutated": False,
        "collage_deployed": False,
        "vanillacord_qualified": False,
        "velocity_forwarding_qualified": False,
        "paper_qualified": False,
        "next_gate": "CANARY_PROTOCOL_DATAPACK_AND_ADAPTER_COMPATIBILITY_DIFF",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=pathlib.Path, required=True)
    args = p.parse_args()
    manifest = get_json(MANIFEST)
    snapshot = choose_snapshot(manifest)
    metadata = get_json(snapshot["metadata"])
    server = choose_server(metadata, snapshot)
    receipt = run_canary(snapshot["version"], server)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": receipt["classification"],
                      "version": receipt["minecraft_snapshot"],
                      "protocol": receipt["observed_protocol"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
