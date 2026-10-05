#!/usr/bin/env python3
"""Qualify an exact Java 26.3 pressure-plate -> access/feedback chain."""

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
PORT = 25569

PLATE = [0, 70, 0]
WIRE = [1, 70, 0]
TRAPDOOR = [2, 70, 0]
LAMP = [1, 69, 0]
INSIDE = [0.5, 70.1, 0.5]
OUTSIDE = [10.5, 70.1, 0.5]

RESET_MARKER = "SUPRACRAFT_PHYSICAL_RESET_OK"
ACTIVE_MARKER = "SUPRACRAFT_PHYSICAL_ACTIVE_OK"


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
                "motd=SupraCraft physical presence-chain qualification",
                "",
            ]
        ),
        "utf-8",
    )


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


def wait_file(
    path: Path,
    process: subprocess.Popen[str],
    timeout: int,
) -> None:
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


def collect_state_diagnostics(
    process: subprocess.Popen[str],
    log_path: Path,
    checks: dict[str, str],
) -> dict[str, Any]:
    """Collect component-level evidence without changing fixture state."""
    token = f"SUPRACRAFT_PHYSICAL_DIAG_{time.monotonic_ns()}"
    before = {
        name: marker_count(log_path, f"{token}_{name}")
        for name in checks
    }
    for name, condition in checks.items():
        send(process, f"execute {condition} run say {token}_{name}")
    send(process, f"data get entity {BOT_NAME} Pos")
    time.sleep(0.35)
    matched = {
        name: marker_count(log_path, f"{token}_{name}") > before[name]
        for name in checks
    }
    tail = log_path.read_text("utf-8", errors="replace")[-3000:]
    return {"matched": matched, "server_tail": tail}


def wait_for_state(
    process: subprocess.Popen[str],
    log_path: Path,
    *,
    marker: str,
    predicate_prefix: str,
    diagnostics: dict[str, str] | None = None,
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
    detail = (
        collect_state_diagnostics(process, log_path, diagnostics)
        if diagnostics
        else {}
    )
    raise RuntimeError(
        f"physical mechanism state timed out for {marker}; "
        f"attempts={attempts}; diagnostics={detail!r}"
    )


def reset_diagnostics() -> dict[str, str]:
    return {
        "plate_unpowered": (
            "if block 0 70 0 minecraft:stone_pressure_plate[powered=false]"
        ),
        "wire_zero": (
            "if block 1 70 0 minecraft:redstone_wire[power=0]"
        ),
        "trapdoor_closed": (
            "if block 2 70 0 minecraft:iron_trapdoor[open=false,powered=false]"
        ),
        "lamp_unlit": (
            "if block 1 69 0 minecraft:redstone_lamp[lit=false]"
        ),
    }


def active_diagnostics() -> dict[str, str]:
    return {
        "plate_powered": (
            "if block 0 70 0 minecraft:stone_pressure_plate[powered=true]"
        ),
        "wire_15": (
            "if block 1 70 0 minecraft:redstone_wire[power=15]"
        ),
        "trapdoor_open": (
            "if block 2 70 0 minecraft:iron_trapdoor[open=true,powered=true]"
        ),
        "lamp_lit": (
            "if block 1 69 0 minecraft:redstone_lamp[lit=true]"
        ),
    }


def reset_predicate() -> str:
    return (
        "execute "
        "if block 0 70 0 minecraft:stone_pressure_plate[powered=false] "
        "if block 1 70 0 minecraft:redstone_wire[power=0] "
        "if block 2 70 0 minecraft:iron_trapdoor[open=false,powered=false] "
        "if block 1 69 0 minecraft:redstone_lamp[lit=false]"
    )


def active_predicate() -> str:
    return (
        "execute "
        "if block 0 70 0 minecraft:stone_pressure_plate[powered=true] "
        "if block 1 70 0 minecraft:redstone_wire[power=15] "
        "if block 2 70 0 minecraft:iron_trapdoor[open=true,powered=true] "
        "if block 1 69 0 minecraft:redstone_lamp[lit=true]"
    )


def expected_server_shutdown_transport_error(
    bot_result: dict[str, Any],
) -> bool:
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
    server_tail = log_path.read_text(
        "utf-8", errors="replace"
    )[-5000:]
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

    with tempfile.TemporaryDirectory(prefix="physical-chain-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

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
                send(server, "fill -2 69 -2 12 69 2 minecraft:stone")
                send(server, "fill -2 70 -2 4 72 2 minecraft:air")
                send(server, "setblock 0 70 0 minecraft:stone_pressure_plate")
                send(server, "setblock 1 70 0 minecraft:redstone_wire")
                send(server, "setblock 2 70 0 minecraft:iron_trapdoor")
                send(server, "setblock 1 69 0 minecraft:redstone_lamp")
                time.sleep(1)

                initial_attempts, initial_wait = wait_for_state(
                    server,
                    log_path,
                    marker=RESET_MARKER,
                    predicate_prefix=reset_predicate(),
                    diagnostics=reset_diagnostics(),
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
                    diagnostics=active_diagnostics(),
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
                    diagnostics=reset_diagnostics(),
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
            "schema": "supracraft.physical-presence-access-feedback/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": protocol,
                "world_version": int(info["world_version"]),
                "server_sha1": evidence["server_artifact"]["actual_sha1"],
                "server_sha256": evidence["server_artifact"]["sha256"],
            },
            "player_treatment": {
                "kind": "real_connected_offline_player",
                "username": BOT_NAME,
                "mineflayer": bot_result,
                "expected_server_shutdown_transport_error": (
                    shutdown_transport_error
                ),
            },
            "fixture": {
                "pressure_plate": PLATE,
                "wire": WIRE,
                "access_actuator": {
                    "block": "minecraft:iron_trapdoor",
                    "position": TRAPDOOR,
                },
                "visible_feedback": {
                    "block": "minecraft:redstone_lamp",
                    "position": LAMP,
                },
                "inside_position": INSIDE,
                "outside_position": OUTSIDE,
            },
            "oracle": {
                "authority": "official_vanilla_server",
                "initial": {
                    "plate_powered": False,
                    "wire_power": 0,
                    "access_open": False,
                    "access_powered": False,
                    "lamp_lit": False,
                    "attempts": initial_attempts,
                    "wait_seconds": round(initial_wait, 6),
                },
                "occupied": {
                    "plate_powered": True,
                    "wire_power": 15,
                    "access_open": True,
                    "access_powered": True,
                    "lamp_lit": True,
                    "attempts": active_attempts,
                    "wait_seconds": round(active_wait, 6),
                },
                "reset": {
                    "plate_powered": False,
                    "wire_power": 0,
                    "access_open": False,
                    "access_powered": False,
                    "lamp_lit": False,
                    "attempts": reset_attempts,
                    "wait_seconds": round(reset_wait, 6),
                },
                "server_error_log_count": len(error_lines),
            },
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "result": "qualified",
            "limitations": [
                "qualifies only this exact Java 26.3 fixture and one occupancy/reset cycle",
                "does not establish all pressure-plate timing or all redstone/access actuators",
                "Mineflayer supplies embodiment but is not the semantic oracle",
                "post-stop ECONNRESET is tolerated only when paired with the explicit server-shutdown kick",
                "does not establish equivalence with any datapack realization",
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
