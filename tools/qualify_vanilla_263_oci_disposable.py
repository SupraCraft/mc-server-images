#!/usr/bin/env python3
"""OP-4A: a *new* Java 25 vanilla-26.3 OCI candidate on one disposable runner.

Discover a fixed upstream *versioned tag* to learn its manifest digest, lock
every actual pull and run to that SHA-256 (never execute a floating tag),
then start, stop, delete and reinstall with an independent world host path.
This does not qualify a native TrueNAS App, Foundry materialization, online
authentication or physical TrueNAS, and the candidate digest is NOT selected
for operations without later freezing/independent approval.
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
import time

from minecraft_world_agent import tree_hash
from smoke_vanilla_runtime import status_query

CANDIDATE_TAG = "docker.io/itzg/minecraft-server:2026.9.1-java25"
BASE = "docker.io/itzg/minecraft-server"
PORT = 25594
VERSION = "26.3"
PROTOCOL = 777
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class Refused(RuntimeError):
    pass


def require(ok: bool, name: str) -> None:
    if not ok:
        raise Refused(name)


def run(args: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    ret = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and ret.returncode != 0:
        raise Refused("COMMAND_FAILED:" + args[0] + ":" + args[1] +
                      ":" + str(ret.returncode))
    return ret


def observed_immutable_image() -> tuple[str, str]:
    """The only mutable lookup; persist its resolved digest and use it by SHA."""
    # No arbitrary CLI string interpolation or untrusted GitHub refs.
    result = run(["docker", "buildx", "imagetools", "inspect", CANDIDATE_TAG], 110)
    lines = result.stdout.splitlines()
    found = [m.group(1) for line in lines
             if (m := re.fullmatch(r"Digest:\s+(sha256:[0-9a-f]{64})", line.strip()))]
    require(len(found) == 1, "OCI_DISCOVERY_DIGEST_UNAVAILABLE")
    digest = found[0]
    immutable = BASE + "@" + digest
    # Independently resolve manifest via immutable address. It must still
    # match the resolved index digest before invoking any container.
    repeated = run(["docker", "buildx", "imagetools", "inspect", immutable], 110)
    require(any(line.strip() == "Digest:    " + digest or
                re.fullmatch(r"Digest:\s+" + re.escape(digest), line.strip())
                for line in repeated.stdout.splitlines()),
            "IMMUTABLE_DIGEST_READBACK_DRIFT")
    require("linux/amd64" in result.stdout, "AMD64_IMAGE_UNAVAILABLE")
    return digest, immutable


def verify_java25(image: str) -> str:
    result = run(["docker", "run", "--rm", "--pull=never",
                  "--entrypoint", "java", image, "-version"], 90)
    output = result.stderr + result.stdout
    require(bool(re.search(r'(?m)^(?:openjdk|java) version "25(?:[.]|")', output)) or
            bool(re.search(r'(?m)^openjdk 25(?:[.]|\s)', output)),
            "CONTAINER_JAVA_25_UNVERIFIED")
    return "25"


def docker_running(name: str) -> bool:
    r = run(["docker", "inspect", "--format", "{{.State.Running}}", name],
            timeout=10, check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def await_vanilla(name: str, timeout: int = 180) -> dict:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        require(docker_running(name), "CONTAINER_EARLY_EXIT")
        try:
            report = status_query("127.0.0.1", PORT, PROTOCOL)
            if (report.get("version", {}).get("protocol") == PROTOCOL and
                    str(report.get("version", {}).get("name", "")).startswith(VERSION)):
                return {"protocol": PROTOCOL, "reported_name":
                        report["version"]["name"]}
        except (OSError, ValueError, TimeoutError, EOFError):
            pass
        time.sleep(2)
    raise Refused("EXACT_VANILLA_PROTOCOL_READINESS_TIMEOUT")


def launch(image: str, world: Path, name: str) -> None:
    args = [
        "docker", "run", "-d", "--pull=never",
        "--name", name, "--stop-timeout", "45",
        "--label", "supracraft.rdte=ephemeral-vanilla-263-qualification",
        "--publish", f"127.0.0.1:{PORT}:25565",
        "--mount", f"type=bind,source={world},target=/data/world",
        "--memory", "3g", "--cpus", "2",
        "-e", "EULA=TRUE",
        "-e", "TYPE=VANILLA", "-e", "VERSION=26.3",
        "-e", "ONLINE_MODE=FALSE",
        "-e", "ENABLE_RCON=FALSE", "-e", "ENABLE_QUERY=FALSE",
        "-e", "SERVER_PORT=25565",
        "-e", "LEVEL=world", "-e", "SEED=4242424242",
        "-e", "VIEW_DISTANCE=3", "-e", "SIMULATION_DISTANCE=2",
        "-e", "MAX_PLAYERS=2", "-e", "MAX_MEMORY=1536M",
        "-e", "UID=1000", "-e", "GID=1000",
        image,
    ]
    run(args, timeout=55)
    require(docker_running(name), "CONTAINER_START_FAILED")


def stop_remove(name: str) -> None:
    r = run(["docker", "inspect", name], 10, check=False)
    if r.returncode:
        return
    if docker_running(name):
        run(["docker", "stop", "-t", "50", name], 90)
    run(["docker", "rm", name], 30)


def execute() -> dict:
    digest, immutable = observed_immutable_image()
    with tempfile.TemporaryDirectory(prefix="supracraft-oci263-") as tmp:
        root = Path(tmp)
        world = root / "external-world"
        world.mkdir()
        name = "supracraft-op4a-" + str(os.getpid())
        try:
            run(["docker", "pull", "--platform", "linux/amd64", immutable],
                timeout=310)
            require(verify_java25(immutable) == "25", "JAVA_VERSION_WRONG")
            first = None
            after_restart = None
            launch(immutable, world, name)
            first = await_vanilla(name)
            require((world / "level.dat").is_file(),
                    "HOST_OWNED_WORLD_LEVEL_DAT_ABSENT")
            stop_remove(name)
            require((world / "level.dat").is_file(),
                    "WORLD_DELETED_WITH_APP")
            first_world_sha = tree_hash(world)
            require(len(first_world_sha) == 64,
                    "WORLD_TREE_HASH_MISSING")
            sentinel = world / ".supracraft-rdte-world-independent"
            sentinel.write_text("independent world ownership sentinel\n")
            sentinel_sha = hashlib.sha256(sentinel.read_bytes()).hexdigest()
            launch(immutable, world, name)
            after_restart = await_vanilla(name)
            require(sentinel.is_file() and
                    hashlib.sha256(sentinel.read_bytes()).hexdigest() == sentinel_sha,
                    "WORLD_SENTINEL_NOT_RETAINED_ON_REINSTALL")
            require((world / "level.dat").is_file(), "WORLD_NOT_REMOUNTED")
            stop_remove(name)
            require(not docker_running(name) and
                    (world / "level.dat").is_file() and
                    sentinel.is_file(),
                    "CONTAINER_DELETE_DID_NOT_PRESERVE_WORLD")
            return {
                "schema": "supracraft.op4a-vanilla263-oci-candidate/1",
                "classification": "REAL_DISPOSABLE_VANILLA_263_JAVA25_OCI_WORLD_RETENTION",
                "image_candidate_tag_observed": CANDIDATE_TAG,
                "image_manifest_sha256": digest,
                "executed_immutable_image_ref": immutable,
                "java_version_in_container": 25,
                "minecraft_version": VERSION,
                "minecraft_protocol": PROTOCOL,
                "first_status": first,
                "after_reinstall_status": after_restart,
                "first_world_tree_sha256": first_world_sha,
                "external_world_sentinel_sha256": sentinel_sha,
                "world_retained_after_container_delete_and_reinstall": True,
                "container_removed_at_end": True,
                "public_ports": ["127.0.0.1:25594"],
                "runtime_tag_frozen_for_operations": False,
                "native_truenas_app_qualified": False,
                "truenas_target_version_qualified": False,
                "collage_deployed": False,
                "world_contents_published": False,
                "online_account_authentication_qualified": False,
                "full_two_rivers_world_qualified": False,
                "physical_truenas_apply": "HOLD",
                "operational_selection": False,
            }
        finally:
            stop_remove(name)
            run(["docker", "image", "rm", immutable], 40, check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    try:
        result = execute()
        code = 0
    except Exception as exc:
        result = {
            "schema": "supracraft.op4a-vanilla263-oci-candidate/1",
            "classification": "FAIL",
            "failure_type": type(exc).__name__,
            "failure": str(exc)[:180],
            "native_truenas_app_qualified": False,
            "operational_selection": False,
            "physical_truenas_apply": "HOLD",
        }
        code = 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "failure": result.get("failure")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
