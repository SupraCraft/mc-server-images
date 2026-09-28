#!/usr/bin/env python3
"""Public-safe Amulet-Core 1.9.x qualification against official Minecraft Java 26.3.

The probe:
1. downloads the already-qualified official server artifact;
2. generates a disposable vanilla world;
3. opens it with Amulet-Core;
4. asserts Java (26, 3) translation support;
5. writes one gold block using version-aware APIs;
6. reopens with Amulet and checks the exact block;
7. boots the official server again and has the server independently verify it.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import amulet
from amulet.api.block import Block

from smoke_vanilla_runtime import (
    download_verified_server,
    status_query,
)


DIMENSION = "minecraft:overworld"
PROBE_AT = (0, 70, 0)
MARKER_AT = (1, 100, 0)
GAME_VERSION = ("java", (26, 3, 0))
PROBE_BLOCK = Block("minecraft", "gold_block")


def write_server_config(root: Path, port: int) -> None:
    (root / "eula.txt").write_text("eula=true\n", "utf-8")
    (root / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
                f"server-port={port}",
                "view-distance=3",
                "simulation-distance=2",
                "spawn-protection=0",
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft Amulet 26.3 qualification",
                "",
            ]
        ),
        "utf-8",
    )


def boot_until_ready(
    root: Path,
    server_jar: Path,
    protocol: int,
    port: int,
    *,
    command_after_ready: str | None = None,
    timeout_seconds: int = 180,
) -> tuple[dict[str, Any], str]:
    log_path = root / "server.log"
    with log_path.open("w+", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                "java",
                "-Xms512M",
                "-Xmx1536M",
                "-jar",
                str(server_jar),
                "nogui",
            ],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        status: dict[str, Any] | None = None
        last_error = ""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                status = status_query("127.0.0.1", port, protocol)
                if int(status.get("version", {}).get("protocol", -1)) == protocol:
                    break
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)

        if status is None or int(status.get("version", {}).get("protocol", -1)) != protocol:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write("stop\n")
                process.stdin.flush()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            log.flush()
            log.seek(0)
            tail = log.read()[-6000:]
            raise RuntimeError(
                "server failed readiness; "
                f"last_error={last_error!r}; exit={process.returncode}; "
                f"log_tail={tail!r}"
            )

        if process.stdin is None:
            raise RuntimeError("server stdin unavailable")

        if command_after_ready:
            process.stdin.write(command_after_ready + "\n")
            process.stdin.flush()
            # Give the command queue a bounded opportunity to execute.
            time.sleep(2)

        process.stdin.write("stop\n")
        process.stdin.flush()
        try:
            exit_code = process.wait(timeout=40)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=10)

        log.flush()
        log.seek(0)
        server_log = log.read()

    if exit_code != 0:
        raise RuntimeError(f"server exited {exit_code}")
    error_lines = [
        line
        for line in server_log.splitlines()
        if "/ERROR]:" in line or "/ERROR] " in line
    ]
    if error_lines:
        raise RuntimeError(
            "server emitted ERROR lines: " + " | ".join(error_lines[-20:])
        )
    return status, server_log


def block_name(block: Any) -> str:
    for attr in ("namespaced_name",):
        value = getattr(block, attr, None)
        if isinstance(value, str):
            return value
    namespace = getattr(block, "namespace", None)
    base_name = getattr(block, "base_name", None)
    if isinstance(namespace, str) and isinstance(base_name, str):
        return f"{namespace}:{base_name}"
    return str(block)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    version_info = evidence["artifact_version_json"]
    if version_info["id"] != "26.3":
        raise RuntimeError("probe requires official Minecraft 26.3 evidence")
    protocol = int(version_info["protocol_version"])

    amulet_version = importlib.metadata.version("amulet-core")

    with tempfile.TemporaryDirectory(prefix="amulet-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root, 25566)

        _, first_log = boot_until_ready(
            root,
            server_jar,
            protocol,
            25566,
            command_after_ready="setworldspawn 0 70 0",
        )
        world_path = root / "world"
        if not (world_path / "level.dat").exists():
            raise RuntimeError("vanilla server did not create world/level.dat")

        level = amulet.load_level(str(world_path))
        try:
            java_versions = [
                tuple(version)
                for version in level.translation_manager.version_numbers("java")
            ]
            if (26, 3, 0) not in java_versions:
                raise RuntimeError(
                    "Amulet translation manager does not advertise Java (26, 3, 0); "
                    f"latest={java_versions[-10:]}"
                )

            before, _ = level.get_version_block(
                *PROBE_AT,
                DIMENSION,
                GAME_VERSION,
            )
            before_name = block_name(before)

            level.set_version_block(
                *PROBE_AT,
                DIMENSION,
                GAME_VERSION,
                PROBE_BLOCK,
            )
            level.save()
        finally:
            level.close()

        level = amulet.load_level(str(world_path))
        try:
            after, _ = level.get_version_block(
                *PROBE_AT,
                DIMENSION,
                GAME_VERSION,
            )
            after_name = block_name(after)
        finally:
            level.close()

        if after_name != "minecraft:gold_block":
            raise RuntimeError(
                f"Amulet reopen mismatch: expected minecraft:gold_block, got {after_name}"
            )

        x, y, z = PROBE_AT
        marker_x, marker_y, marker_z = MARKER_AT
        command = (
            f"execute if block {x} {y} {z} minecraft:gold_block "
            f"run setblock {marker_x} {marker_y} {marker_z} minecraft:diamond_block"
        )
        status, second_log = boot_until_ready(
            root,
            server_jar,
            protocol,
            25566,
            command_after_ready=command,
        )

        # Cross-direction oracle: the vanilla server places this marker only
        # when it independently observes the Amulet-written gold block.
        level = amulet.load_level(str(world_path))
        try:
            marker_block, _ = level.get_version_block(
                *MARKER_AT,
                DIMENSION,
                GAME_VERSION,
            )
            marker_name = block_name(marker_block)
        finally:
            level.close()

        server_verified = marker_name == "minecraft:diamond_block"
        if not server_verified:
            raise RuntimeError(
                "official Minecraft 26.3 server did not create the conditional "
                f"marker; observed {marker_name} at {MARKER_AT}"
            )

    result = {
        "schema": "supracraft.amulet-java-world-io/v0.1",
        "minecraft": {
            "edition": "java",
            "version": "26.3",
            "protocol": protocol,
            "world_version": version_info["world_version"],
        },
        "amulet_core_version": amulet_version,
        "translation_support": {
            "java_26_3": True,
        },
        "probe": {
            "coordinate": list(PROBE_AT),
            "before": before_name,
            "written": "minecraft:gold_block",
            "amulet_reopen": after_name,
            "official_server_verified": server_verified,
            "server_conditional_marker": {
                "coordinate": list(MARKER_AT),
                "block": marker_name,
            },
        },
        "vanilla": {
            "first_boot_done": "Done (" in first_log,
            "second_boot_done": "Done (" in second_log,
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
        },
        "result": "qualified",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
