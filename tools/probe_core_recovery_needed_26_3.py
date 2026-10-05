#!/usr/bin/env python3
"""Qualify Java 26.3 core recovery-needed observation."""

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
PORT = 25574
SOCKET = [0, 70, 0]
CORE = "minecraft:redstone_block"

HAS_CORE = "SUPRACRAFT_RECOVERY_HAS_CORE"
LACKS_CORE = "SUPRACRAFT_RECOVERY_LACKS_CORE"
SOCKET_CORE = "SUPRACRAFT_RECOVERY_SOCKET_CORE"
RECOVERY_NEEDED = "SUPRACRAFT_RECOVERY_NEEDED"
UNEXPECTED = "SUPRACRAFT_RECOVERY_UNEXPECTED"


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
                "motd=SupraCraft recovery-needed qualification",
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


def wait_file(path: Path, process: subprocess.Popen[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            output = process.stdout.read()[-4000:] if process.stdout else ""
            raise RuntimeError(
                f"worker exited before {path.name}: "
                f"exit={process.returncode}; stdout={output!r}"
            )
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def marker_count(path: Path, marker: str) -> int:
    text = path.read_text("utf-8", errors="replace")
    return sum(marker in line for line in text.splitlines())


def require_true(
    process: subprocess.Popen[str],
    log_path: Path,
    *,
    marker: str,
    predicate: str,
    timeout: float = 5.0,
) -> tuple[int, float]:
    baseline = marker_count(log_path, marker)
    started = time.monotonic()
    attempts = 0
    while time.monotonic() - started < timeout:
        attempts += 1
        send(process, f"{predicate} run say {marker}")
        time.sleep(0.2)
        if marker_count(log_path, marker) > baseline:
            return attempts, time.monotonic() - started
    raise RuntimeError(
        f"predicate never became true for {marker}; attempts={attempts}; "
        f"tail={log_path.read_text('utf-8', errors='replace')[-4000:]!r}"
    )


def require_false(
    process: subprocess.Popen[str],
    log_path: Path,
    *,
    marker: str,
    predicate: str,
    settle: float = 0.6,
) -> float:
    baseline = marker_count(log_path, marker)
    started = time.monotonic()
    send(process, f"{predicate} run say {marker}")
    time.sleep(settle)
    if marker_count(log_path, marker) != baseline:
        raise RuntimeError(
            f"predicate unexpectedly true for {marker}; "
            f"tail={log_path.read_text('utf-8', errors='replace')[-4000:]!r}"
        )
    return time.monotonic() - started


def inventory_has_core() -> str:
    return (
        f"execute if items entity {BOT_NAME} inventory.* {CORE}"
    )


def inventory_lacks_core() -> str:
    return (
        f"execute unless items entity {BOT_NAME} inventory.* {CORE}"
    )


def socket_has_core() -> str:
    return (
        f"execute if block {SOCKET[0]} {SOCKET[1]} {SOCKET[2]} {CORE}"
    )


def recovery_needed() -> str:
    return (
        f"execute unless items entity {BOT_NAME} inventory.* {CORE} "
        f"unless block {SOCKET[0]} {SOCKET[1]} {SOCKET[2]} {CORE}"
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

    with tempfile.TemporaryDirectory(prefix="recovery-needed-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
        bot_result_path = root / "bot-result.json"
        with log_path.open("w", encoding="utf-8") as log:
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
            bot: subprocess.Popen[str] | None = None
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add 0 0")
                send(server, "fill -2 69 -2 3 69 3 minecraft:stone")
                send(server, "fill -2 70 -2 3 72 3 minecraft:air")
                send(server, "setblock 0 70 0 minecraft:air")

                ready = root / "bot.ready"
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
                        str(Path(__file__).with_name("probe_mineflayer_presence.js")),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_file(ready, bot, 40)

                # Treatment A: player possesses core; empty socket.
                send(server, f"give {BOT_NAME} {CORE} 1")
                has_attempts, has_wait = require_true(
                    server,
                    log_path,
                    marker=HAS_CORE,
                    predicate=inventory_has_core(),
                )
                negative_possession_wait = require_false(
                    server,
                    log_path,
                    marker=UNEXPECTED + "_POSSESSION",
                    predicate=recovery_needed(),
                )

                # Treatment B: player lacks core; socket empty.
                send(server, f"clear {BOT_NAME} {CORE}")
                lacks_attempts, lacks_wait = require_true(
                    server,
                    log_path,
                    marker=LACKS_CORE,
                    predicate=inventory_lacks_core(),
                )
                need_attempts, need_wait = require_true(
                    server,
                    log_path,
                    marker=RECOVERY_NEEDED,
                    predicate=recovery_needed(),
                )

                # Treatment C: player lacks core; core already installed.
                send(server, f"setblock 0 70 0 {CORE}")
                socket_attempts, socket_wait = require_true(
                    server,
                    log_path,
                    marker=SOCKET_CORE,
                    predicate=socket_has_core(),
                )
                negative_installed_wait = require_false(
                    server,
                    log_path,
                    marker=UNEXPECTED + "_INSTALLED",
                    predicate=recovery_needed(),
                )

                send(server, "stop")
                server_rc = server.wait(timeout=40)

                try:
                    bot_stdout, _ = bot.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    bot_stdout, _ = bot.communicate(timeout=5)
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
        # Normal server shutdown may surface as a disconnect; only pre-shutdown
        # presence is material to this probe.
        server_log = log_path.read_text("utf-8", errors="replace")
        error_lines = [
            line
            for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if error_lines:
            raise RuntimeError(
                "server emitted ERROR lines: " + " | ".join(error_lines[-20:])
            )

        result = {
            "schema": "supracraft.core-recovery-needed/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": protocol,
                "world_version": int(info["world_version"]),
                "server_sha1": evidence["server_artifact"]["actual_sha1"],
                "server_sha256": evidence["server_artifact"]["sha256"],
            },
            "semantic_candidate": {
                "name": "object.recovery_needed",
                "object": "core",
                "target": "beacon",
                "bounded_definition": (
                    "player lacks represented core AND target socket "
                    "does not contain represented core"
                ),
            },
            "representation": {
                "core": CORE,
                "socket": SOCKET,
                "player_inventory_selector": "inventory.*",
            },
            "player_treatment": {
                "kind": "real_connected_offline_player",
                "username": BOT_NAME,
                "mineflayer": bot_result,
            },
            "oracle": {
                "authority": "official_vanilla_server",
                "possessed_empty_socket": {
                    "player_has_core": True,
                    "socket_has_core": False,
                    "recovery_needed": False,
                    "positive_attempts": has_attempts,
                    "positive_wait_seconds": round(has_wait, 6),
                    "negative_wait_seconds": round(
                        negative_possession_wait, 6
                    ),
                },
                "missing_empty_socket": {
                    "player_has_core": False,
                    "socket_has_core": False,
                    "recovery_needed": True,
                    "lacks_attempts": lacks_attempts,
                    "lacks_wait_seconds": round(lacks_wait, 6),
                    "recovery_attempts": need_attempts,
                    "recovery_wait_seconds": round(need_wait, 6),
                },
                "missing_installed_socket": {
                    "player_has_core": False,
                    "socket_has_core": True,
                    "recovery_needed": False,
                    "socket_attempts": socket_attempts,
                    "socket_wait_seconds": round(socket_wait, 6),
                    "negative_wait_seconds": round(
                        negative_installed_wait, 6
                    ),
                },
                "server_error_log_count": len(error_lines),
            },
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "result": "qualified",
            "limitations": [
                "qualifies only this exact Java 26.3 inventory/socket representation",
                "does not search dropped item entities or other storage",
                "does not by itself define final story recovery routing",
                "Mineflayer supplies a real connected player but is not the oracle",
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
