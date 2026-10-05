#!/usr/bin/env python3
"""Qualify exact Java 26.3 datapack presence -> access/feedback -> reset."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query


BOT_NAME = "SupraCraftProbe"
PORT = 25570

ACCESS = [2, 70, 0]
FEEDBACK = [1, 70, 1]
INSIDE = [0.5, 70.1, 0.5]
OUTSIDE = [10.5, 70.1, 0.5]
REGION_SELECTOR = "@a[x=-1,y=69,z=-1,dx=2,dy=3,dz=2]"

RESET_MARKER = "SUPRACRAFT_DATAPACK_RESET_OK"
ACTIVE_MARKER = "SUPRACRAFT_DATAPACK_ACTIVE_OK"


def write_server_config(root: Path) -> None:
    (root / "eula.txt").write_text("eula=true\n", "utf-8")
    (root / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
                "white-list=false",
                "enforce-whitelist=false",
                f"server-port={PORT}",
                "view-distance=3",
                "simulation-distance=2",
                "spawn-protection=0",
                "max-players=2",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft datapack presence-chain qualification",
                "",
            ]
        ),
        "utf-8",
    )


def write_datapack(root: Path) -> dict[str, Any]:
    pack = root / "world" / "datapacks" / "supracraft_presence"
    fn = pack / "data" / "supracraft_presence" / "function"
    tag = pack / "data" / "minecraft" / "tags" / "function"
    fn.mkdir(parents=True, exist_ok=True)
    tag.mkdir(parents=True, exist_ok=True)

    metadata = {
        "pack": {
            "description": "SupraCraft exact 26.3 bounded presence chain",
            "min_format": [121, 0],
            "max_format": [121, 0],
        }
    }
    (pack / "pack.mcmeta").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )
    (tag / "tick.json").write_text(
        json.dumps({"values": ["supracraft_presence:tick"]}, indent=2) + "\n",
        "utf-8",
    )
    commands = [
        f"execute if entity {REGION_SELECTOR} run setblock {ACCESS[0]} {ACCESS[1]} {ACCESS[2]} minecraft:air",
        f"execute if entity {REGION_SELECTOR} run setblock {FEEDBACK[0]} {FEEDBACK[1]} {FEEDBACK[2]} minecraft:sea_lantern",
        f"execute unless entity {REGION_SELECTOR} run setblock {ACCESS[0]} {ACCESS[1]} {ACCESS[2]} minecraft:iron_bars",
        f"execute unless entity {REGION_SELECTOR} run setblock {FEEDBACK[0]} {FEEDBACK[1]} {FEEDBACK[2]} minecraft:black_concrete",
    ]
    (fn / "tick.mcfunction").write_text("\n".join(commands) + "\n", "utf-8")
    return {
        "metadata": metadata,
        "tick_tag": ["supracraft_presence:tick"],
        "commands": commands,
    }


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_server(
    process: subprocess.Popen[str], protocol: int, timeout: int = 180
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early: {process.returncode}")
        try:
            status = status_query("127.0.0.1", PORT, protocol)
            if int(status.get("version", {}).get("protocol", -1)) == protocol:
                return status
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"server readiness timeout: {last_error}")


def wait_file(path: Path, process: subprocess.Popen[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise RuntimeError(
                f"worker exited before {path.name}: exit={process.returncode}"
            )
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def marker_count(path: Path, marker: str) -> int:
    text = path.read_text("utf-8", errors="replace")
    return sum(marker in line for line in text.splitlines())


def wait_for_state(
    process: subprocess.Popen[str],
    log_path: Path,
    *,
    marker: str,
    predicate_prefix: str,
    timeout: float = 8.0,
) -> tuple[int, float]:
    started = time.monotonic()
    attempts = 0
    baseline = marker_count(log_path, marker)
    while time.monotonic() - started < timeout:
        attempts += 1
        send(process, f"{predicate_prefix} run say {marker}")
        time.sleep(0.2)
        if marker_count(log_path, marker) > baseline:
            return attempts, time.monotonic() - started
    raise RuntimeError(
        f"datapack mechanism state timed out for {marker}; attempts={attempts}"
    )


def reset_predicate() -> str:
    return (
        "execute "
        "if block 2 70 0 minecraft:iron_bars "
        "if block 1 70 1 minecraft:black_concrete"
    )


def active_predicate() -> str:
    return (
        "execute "
        "if block 2 70 0 minecraft:air "
        "if block 1 70 1 minecraft:sea_lantern"
    )


def expected_server_shutdown_transport_error(bot_result: dict[str, Any]) -> bool:
    error = str(bot_result.get("error") or "")
    kicked = bot_result.get("kicked") or {}
    translate = (
        kicked.get("value", {})
        .get("translate", {})
        .get("value")
        if isinstance(kicked, dict)
        else None
    )
    return (
        bot_result.get("end_reason") == "socketClosed"
        and translate == "multiplayer.disconnect.server_shutdown"
        and "ECONNRESET" in error
    )


def collect_bot_failure(
    bot: subprocess.Popen[str],
    bot_result_path: Path,
    log_path: Path,
    cause: Exception,
) -> RuntimeError:
    if bot.poll() is None:
        bot.terminate()
        try:
            stdout, _ = bot.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            bot.kill()
            stdout, _ = bot.communicate(timeout=5)
    else:
        stdout = bot.stdout.read() if bot.stdout is not None else ""
    diagnostic = None
    if bot_result_path.exists():
        diagnostic = json.loads(bot_result_path.read_text("utf-8"))
    server_tail = log_path.read_text("utf-8", errors="replace")[-5000:]
    return RuntimeError(
        f"{cause}; bot_result={diagnostic!r}; "
        f"bot_stdout={stdout[-4000:]!r}; server_tail={server_tail!r}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    with tempfile.TemporaryDirectory(prefix="datapack-chain-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)
        datapack = write_datapack(root)

        log_path = root / "server.log"
        bot: subprocess.Popen[str] | None = None
        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
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
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add 0 0")
                time.sleep(1)

                initial_attempts, initial_wait = wait_for_state(
                    server,
                    log_path,
                    marker=RESET_MARKER,
                    predicate_prefix=reset_predicate(),
                )

                ready = root / "bot.ready"
                bot_result_path = root / "bot-result.json"
                env = dict(os.environ)
                env.update(
                    {
                        "MC_PORT": str(PORT),
                        "BOT_READY_FILE": str(ready),
                        "BOT_RESULT_FILE": str(bot_result_path),
                    }
                )
                bot = subprocess.Popen(
                    [
                        "node",
                        str(
                            Path(__file__).with_name(
                                "probe_mineflayer_presence.js"
                            )
                        ),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    wait_file(ready, bot, 40)
                except RuntimeError as exc:
                    raise collect_bot_failure(
                        bot, bot_result_path, log_path, exc
                    ) from exc

                send(
                    server,
                    f"tp {BOT_NAME} {INSIDE[0]} {INSIDE[1]} {INSIDE[2]} 0 0",
                )
                active_attempts, active_wait = wait_for_state(
                    server,
                    log_path,
                    marker=ACTIVE_MARKER,
                    predicate_prefix=active_predicate(),
                )

                send(
                    server,
                    f"tp {BOT_NAME} {OUTSIDE[0]} {OUTSIDE[1]} {OUTSIDE[2]} 0 0",
                )
                reset_marker_2 = RESET_MARKER + "_AFTER"
                reset_attempts, reset_wait = wait_for_state(
                    server,
                    log_path,
                    marker=reset_marker_2,
                    predicate_prefix=reset_predicate(),
                )

                send(server, "save-all flush")
                time.sleep(1)
                send(server, "stop")
                try:
                    server_rc = server.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server_rc = server.wait(timeout=10)

                if bot is not None:
                    try:
                        bot_stdout, _ = bot.communicate(timeout=15)
                    except subprocess.TimeoutExpired:
                        bot.kill()
                        bot_stdout, _ = bot.communicate(timeout=5)
                else:
                    bot_stdout = ""

                log.flush()
                log.seek(0)
                server_log = log.read()
            finally:
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)
                if bot is not None and bot.poll() is None:
                    bot.terminate()
                    try:
                        bot.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        bot.kill()
                        bot.wait(timeout=5)

        if server_rc != 0:
            raise RuntimeError(f"server exit code {server_rc}")
        if not bot_result_path.exists():
            raise RuntimeError(
                "Mineflayer presence worker produced no result: "
                + bot_stdout[-4000:]
            )
        bot_result = json.loads(bot_result_path.read_text("utf-8"))
        if "spawn" not in bot_result.get("milestones", {}):
            raise RuntimeError(
                "Mineflayer player never reached spawn: "
                + json.dumps(bot_result, sort_keys=True)
            )
        shutdown_transport_error = expected_server_shutdown_transport_error(
            bot_result
        )
        if bot_result.get("error") and not shutdown_transport_error:
            raise RuntimeError(
                "Mineflayer presence worker error: "
                + json.dumps(bot_result, sort_keys=True)
            )

        error_lines = [
            line
            for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if error_lines:
            raise RuntimeError(
                "server emitted ERROR lines: "
                + " | ".join(error_lines[-20:])
            )

        result = {
            "schema": "supracraft.datapack-presence-access-feedback/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": protocol,
                "world_version": int(info["world_version"]),
                "data_pack_version": [121, 0],
                "server_sha1": evidence["server_artifact"]["actual_sha1"],
                "server_sha256": evidence["server_artifact"]["sha256"],
            },
            "datapack": datapack,
            "player_treatment": {
                "kind": "real_connected_offline_player",
                "username": BOT_NAME,
                "mineflayer": bot_result,
                "expected_server_shutdown_transport_error": (
                    shutdown_transport_error
                ),
            },
            "fixture": {
                "region_selector": REGION_SELECTOR,
                "access": {
                    "position": ACCESS,
                    "outside": "minecraft:iron_bars",
                    "inside": "minecraft:air",
                },
                "visible_feedback": {
                    "position": FEEDBACK,
                    "outside": "minecraft:black_concrete",
                    "inside": "minecraft:sea_lantern",
                },
                "inside_position": INSIDE,
                "outside_position": OUTSIDE,
            },
            "oracle": {
                "authority": "official_vanilla_server",
                "initial": {
                    "access": "minecraft:iron_bars",
                    "feedback": "minecraft:black_concrete",
                    "attempts": initial_attempts,
                    "wait_seconds": round(initial_wait, 6),
                },
                "occupied": {
                    "access": "minecraft:air",
                    "feedback": "minecraft:sea_lantern",
                    "attempts": active_attempts,
                    "wait_seconds": round(active_wait, 6),
                },
                "reset": {
                    "access": "minecraft:iron_bars",
                    "feedback": "minecraft:black_concrete",
                    "attempts": reset_attempts,
                    "wait_seconds": round(reset_wait, 6),
                },
                "server_error_log_count": len(error_lines),
            },
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "result": "qualified",
            "limitations": [
                "qualifies only this exact Java 26.3 datapack, selector and one occupancy/reset cycle",
                "does not establish persistence across restart or arbitrary datapack logic",
                "Mineflayer supplies embodiment but is not the semantic oracle",
                "does not establish equivalence with the physical/reactive realization",
            ],
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
