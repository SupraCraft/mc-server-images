#!/usr/bin/env python3
"""Boot actual Paper Java 26.3 candidate in isolated public CI and observe protocol.

This is not an operational deployment, proxy-forwarding test, or prior pinned
artifact acceptance. The exact JAR SHA256 and upstream build are recorded for
a subsequent immutable approval commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from smoke_vanilla_runtime import status_query
from resolve_operational_runtime_versions import official_url, UA, Refused

EXPECTED_VERSION = "26.3"
PROTOCOL = 777
PORT = 25586
MAX_JAR_BYTES = 130 * 1024 * 1024


def run(candidate: dict, runtime_seconds: int = 180) -> dict:
    if candidate.get("version") != EXPECTED_VERSION or (
        not isinstance(candidate.get("build"), int)
        or candidate["build"] <= 0
    ):
        raise Refused("PAPER_263_CANDIDATE_DRIFT")
    uri = candidate.get("url")
    if not official_url(uri, "papermc.io"):
        raise Refused("PAPER_DOWNLOAD_DOMAIN_DRIFT")

    with tempfile.TemporaryDirectory(prefix="supracraft-paper-263-") as t:
        root = pathlib.Path(t)
        jar = root / "paper.jar"
        req = urllib.request.Request(uri, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as f:
            if not official_url(f.url, "papermc.io"):
                raise Refused("PAPER_DOWNLOAD_REDIRECT_DRIFT")
            with jar.open("wb") as dst:
                size = 0
                h = hashlib.sha256()
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_JAR_BYTES:
                        raise Refused("PAPER_JAR_SIZE_DRIFT")
                    dst.write(chunk)
                    h.update(chunk)
        digest = h.hexdigest()
        claimed = candidate.get("reported_sha256")
        if claimed and claimed != digest:
            raise Refused("PAPER_JAR_SHA256_MISMATCH")
        if size < 1024 * 1024 or not zipfile.is_zipfile(jar):
            raise Refused("PAPER_JAR_INVALID")

        (root / "eula.txt").write_text("eula=true\n")
        (root / "server.properties").write_text(
            f"server-port={PORT}\nserver-ip=127.0.0.1\nonline-mode=false\n"
            "max-players=1\nview-distance=2\nsimulation-distance=2\n"
            "spawn-protection=0\nmotd=SupraCraft Paper 26.3 RDTE\n"
            "enable-rcon=false\nenable-query=false\n"
        )
        log = root / "paper.log"
        with log.open("w+", encoding="utf-8") as output:
            process = subprocess.Popen(["java", "-Xms512M", "-Xmx1536M",
                                        "-jar", str(jar), "nogui"],
                                       stdin=subprocess.PIPE,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       cwd=root, text=True)
            status = None
            started = time.monotonic()
            try:
                while time.monotonic() - started < runtime_seconds:
                    if process.poll() is not None:
                        raise Refused("PAPER_EARLY_EXIT")
                    try:
                        probe = status_query("127.0.0.1", PORT, PROTOCOL)
                        if int(probe.get("version", {}).get("protocol", -1)) == PROTOCOL:
                            status = probe
                            break
                    except (ConnectionError, OSError, ValueError, TimeoutError):
                        pass
                    time.sleep(1)
                if status is None:
                    raise Refused("PAPER_263_STATUS_TIMEOUT")
                if process.stdin is None:
                    raise Refused("PAPER_STDIN_UNAVAILABLE")
                process.stdin.write("save-all flush\nstop\n")
                process.stdin.flush()
                code = process.wait(timeout=50)
                if code != 0:
                    raise Refused("PAPER_GRACEFUL_STOP_FAILED")
                output.flush()
                output.seek(0)
                lines = output.read().splitlines()
                if not (root / "world/level.dat").is_file():
                    raise Refused("PAPER_WORLD_SAVE_MISSING")
                if any("/ERROR]" in line for line in lines):
                    raise Refused("PAPER_SERVER_ERROR_LOG")
                if not any("Done (" in line for line in lines):
                    raise Refused("PAPER_READY_LOG_MISSING")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=20)
        return {
            "schema": "supracraft.paper-263-real-runtime-rdte/1",
            "classification": "REAL_DISPOSABLE_STANDALONE_PAPER_BOOT",
            "minecraft_version": EXPECTED_VERSION,
            "paper_build_id": candidate["build"],
            "observed_protocol": status["version"]["protocol"],
            "observed_version_name": status["version"].get("name"),
            "jar_sha256": digest,
            "upstream_reported_sha256": claimed,
            "jar_bytes": size,
            "level_dat_observed": True,
            "graceful_stop": True,
            "java_required": 25,
            "velocity_forwarding_verified": False,
            "vanillacord_verified": False,
            "truenas_app_materialized": False,
            "two_rivers_gameplay_verified": False,
            "operationally_approved": False,
            "physical_truenas_mutated": False,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", type=pathlib.Path, required=True)
    ap.add_argument("--output", type=pathlib.Path, required=True)
    a = ap.parse_args()
    candidate = json.loads(a.discovery.read_text())
    if candidate.get("classification") != "READ_ONLY_CANDIDATES_DISCOVERED":
        raise SystemExit("refuse unqualified discovery")
    result = run(candidate["stable"]["paper"])
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "paper_build_id": result["paper_build_id"],
                      "sha256": result["jar_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
