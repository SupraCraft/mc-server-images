#!/usr/bin/env python3
"""Qualify exact Velocity 4.2.0 standalone proxy process on an isolated runner.

This is a proxy boot/socket check, NOT a live forwarded Minecraft connection,
identity proof, or operational authorization. Digest is captured for pinning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from resolve_operational_runtime_versions import Refused, UA, official_url

PORT = 25577
MAX_JAR = 80 * 1024 * 1024


def run(candidate: dict) -> dict:
    if candidate.get("version") != "4.2.0" or candidate.get("build") != 30:
        raise Refused("VELOCITY_RELEASE_BUILD_DRIFT")
    url = candidate.get("url")
    if not official_url(url, "papermc.io"):
        raise Refused("VELOCITY_DOWNLOAD_DOMAIN_DRIFT")
    with tempfile.TemporaryDirectory(prefix="supracraft-velocity-420-") as tmp:
        root = pathlib.Path(tmp)
        jar = root / "velocity.jar"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        sha = hashlib.sha256()
        total = 0
        with urllib.request.urlopen(req, timeout=90) as stream, jar.open("wb") as out:
            if not official_url(stream.url, "papermc.io"):
                raise Refused("VELOCITY_DOWNLOAD_REDIRECT_DRIFT")
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_JAR:
                    raise Refused("VELOCITY_JAR_SIZE_DRIFT")
                out.write(chunk)
                sha.update(chunk)
        actual = sha.hexdigest()
        expected = candidate.get("reported_sha256")
        if expected and expected != actual:
            raise Refused("VELOCITY_JAR_SHA256_MISMATCH")
        if total < 1024 * 1024 or not zipfile.is_zipfile(jar):
            raise Refused("VELOCITY_JAR_INVALID")
        log_path = root / "velocity.log"
        with log_path.open("w+", encoding="utf-8") as log:
            proc = subprocess.Popen(["java", "-Xms256M", "-Xmx768M",
                                     "-jar", str(jar)],
                                    cwd=root, stdin=subprocess.PIPE,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    text=True)
            listening = False
            try:
                deadline = time.monotonic() + 100
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise Refused("VELOCITY_EARLY_EXIT")
                    try:
                        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                            listening = True
                            break
                    except OSError:
                        time.sleep(1)
                if not listening:
                    raise Refused("VELOCITY_PROXY_LISTENER_TIMEOUT")
                log.flush()
                log.seek(0)
                data = log.read()
                if "Velocity" not in data or "4.2.0" not in data:
                    raise Refused("VELOCITY_VERSION_LOG_MISSING")
            finally:
                if proc.poll() is None:
                    if proc.stdin:
                        try:
                            proc.stdin.write("shutdown\n")
                            proc.stdin.flush()
                            proc.wait(timeout=20)
                        except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                            proc.kill()
                            proc.wait(timeout=10)
    return {
        "schema": "supracraft.velocity-420-real-proxy-rdte/1",
        "classification": "REAL_DISPOSABLE_STANDALONE_VELOCITY_BOOT",
        "velocity_version": "4.2.0", "build": 30,
        "sha256": actual, "bytes": total,
        "listener_25577_observed": listening,
        "minecraft_26_3_forwarding_verified": False,
        "vanillacord_verified": False,
        "auth_and_vip_verified": False,
        "operationally_approved": False,
        "physical_truenas_mutated": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--discovery", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    args = p.parse_args()
    evidence = json.loads(args.discovery.read_text())
    if evidence.get("classification") != "READ_ONLY_CANDIDATES_DISCOVERED":
        raise SystemExit("refuse unqualified upstream discovery")
    receipt = run(evidence["stable"]["velocity"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"result": receipt["classification"],
                      "sha256": receipt["sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
