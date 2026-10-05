#!/usr/bin/env python3
"""Qualify Java 26.3 vanilla-container core acquisition and reacquisition."""

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
PORT = 25573
CHEST = [0, 70, 0]
BOT_POSITION = [0.5, 70.0, 2.5]

SOURCE_READY = "SUPRACRAFT_CORE_SOURCE_READY"
FIRST_ACQUIRED = "SUPRACRAFT_CORE_FIRST_ACQUIRED"
LOSS_OK = "SUPRACRAFT_CORE_LOSS_OK"
REACQUIRED = "SUPRACRAFT_CORE_REACQUIRED"


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
                "motd=SupraCraft core acquisition qualification",
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


def wait_for_predicate(
    process: subprocess.Popen[str],
    log_path: Path,
    *,
    marker: str,
    predicate: str,
    timeout: float = 8.0,
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
        f"state predicate timed out for {marker}; attempts={attempts}; "
        f"server_tail={log_path.read_text('utf-8', errors='replace')[-5000:]!r}"
    )


def inventory_has_core() -> str:
    return (
        f"execute if items entity {BOT_NAME} inventory.* "
        "minecraft:redstone_block"
    )


def inventory_lacks_core() -> str:
    return (
        f"execute unless items entity {BOT_NAME} inventory.* "
        "minecraft:redstone_block"
    )


def source_has_core() -> str:
    return (
        "execute if items block 0 70 0 container.0 "
        "minecraft:redstone_block"
    )


def source_lacks_core() -> str:
    return (
        "execute unless items block 0 70 0 container.0 "
        "minecraft:redstone_block"
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

    with tempfile.TemporaryDirectory(prefix="core-acquisition-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
        bot_result_path = root / "bot-result.json"
        first_file = root / "bot-first.ready"
        second_file = root / "bot-second.ready"
        done_file = root / "bot-done.ready"

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
                send(server, "fill -2 69 -2 3 69 4 minecraft:stone")
                send(server, "fill -2 70 -2 3 72 4 minecraft:air")
                send(server, "setblock 0 70 0 minecraft:chest[facing=south]")
                send(
                    server,
                    "item replace block 0 70 0 container.0 "
                    "with minecraft:redstone_block 1",
                )
                time.sleep(1)

                source_attempts, source_wait = wait_for_predicate(
                    server,
                    log_path,
                    marker=SOURCE_READY,
                    predicate=source_has_core(),
                )

                ready = root / "bot.ready"
                env = dict(os.environ)
                env.update(
                    {
                        "MC_PORT": str(PORT),
                        "BOT_READY_FILE": str(ready),
                        "BOT_FIRST_FILE": str(first_file),
                        "BOT_SECOND_FILE": str(second_file),
                        "BOT_DONE_FILE": str(done_file),
                        "BOT_RESULT_FILE": str(bot_result_path),
                    }
                )
                bot = subprocess.Popen(
                    [
                        "node",
                        str(
                            Path(__file__).with_name(
                                "probe_mineflayer_core_container.js"
                            )
                        ),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_file(ready, bot, 40)
                send(server, f"gamemode survival {BOT_NAME}")
                send(
                    server,
                    f"tp {BOT_NAME} "
                    f"{BOT_POSITION[0]} {BOT_POSITION[1]} {BOT_POSITION[2]} "
                    "180 0",
                )

                wait_file(first_file, bot, 50)
                first_attempts, first_wait = wait_for_predicate(
                    server,
                    log_path,
                    marker=FIRST_ACQUIRED,
                    predicate=(
                        inventory_has_core()
                        + " "
                        + source_lacks_core().removeprefix("execute ")
                    ),
                )

                # Controlled loss is a falsification treatment, not story behavior.
                send(server, f"clear {BOT_NAME} minecraft:redstone_block")
                loss_attempts, loss_wait = wait_for_predicate(
                    server,
                    log_path,
                    marker=LOSS_OK,
                    predicate=inventory_lacks_core(),
                )

                # Refill the same keeper-side source for the recovery treatment.
                send(
                    server,
                    "item replace block 0 70 0 container.0 "
                    "with minecraft:redstone_block 1",
                )

                wait_file(second_file, bot, 50)
                second_attempts, second_wait = wait_for_predicate(
                    server,
                    log_path,
                    marker=REACQUIRED,
                    predicate=(
                        inventory_has_core()
                        + " "
                        + source_lacks_core().removeprefix("execute ")
                    ),
                )
                done_file.write_text("verified\n", "utf-8")

                try:
                    bot_stdout, _ = bot.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    bot_stdout, _ = bot.communicate(timeout=10)
                    raise RuntimeError(
                        "Mineflayer container worker did not exit after verification: "
                        + bot_stdout[-4000:]
                    )

                if not bot_result_path.exists():
                    raise RuntimeError(
                        "Mineflayer container worker produced no result: "
                        + bot_stdout[-4000:]
                    )
                bot_result = json.loads(bot_result_path.read_text("utf-8"))
                if (
                    bot.returncode != 0
                    or bot_result.get("error")
                    or len(bot_result.get("acquisitions", [])) != 2
                ):
                    raise RuntimeError(
                        "Mineflayer container acquisition failed: "
                        + json.dumps(bot_result, sort_keys=True)
                        + " stdout="
                        + bot_stdout[-4000:]
                    )

                send(server, "stop")
                server_rc = server.wait(timeout=40)
            finally:
                if bot is not None and bot.poll() is None:
                    bot.terminate()
                    try:
                        bot.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        bot.kill()
                        bot.wait(timeout=5)
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

        if server_rc != 0:
            raise RuntimeError(f"server exit code {server_rc}")
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
            "schema": "supracraft.core-container-acquisition/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": protocol,
                "world_version": int(info["world_version"]),
                "server_sha1": evidence["server_artifact"]["actual_sha1"],
                "server_sha256": evidence["server_artifact"]["sha256"],
            },
            "source": {
                "block": "minecraft:chest",
                "position": CHEST,
                "slot": "container.0",
                "core": "minecraft:redstone_block",
                "controller_replenished_for_recovery_treatment": True,
            },
            "player_treatment": {
                "kind": "real_connected_offline_player",
                "username": BOT_NAME,
                "controller_positioned": True,
                "mineflayer": bot_result,
            },
            "oracle": {
                "authority": "official_vanilla_server",
                "source_initially_contains_core": {
                    "attempts": source_attempts,
                    "wait_seconds": round(source_wait, 6),
                },
                "first_acquisition": {
                    "player_has_core": True,
                    "source_slot_empty": True,
                    "attempts": first_attempts,
                    "wait_seconds": round(first_wait, 6),
                },
                "controlled_loss": {
                    "player_has_core": False,
                    "attempts": loss_attempts,
                    "wait_seconds": round(loss_wait, 6),
                },
                "reacquisition": {
                    "player_has_core": True,
                    "source_slot_empty": True,
                    "attempts": second_attempts,
                    "wait_seconds": round(second_wait, 6),
                },
                "server_error_log_count": len(error_lines),
            },
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "result": "qualified",
            "limitations": [
                "qualifies only this exact Java 26.3 chest interaction and two acquisitions",
                "controller positions the player",
                "controller replenishes the source for the recovery treatment",
                "does not establish autonomous navigation or final diegetic replenishment",
                "Mineflayer performs container interaction but is not the possession oracle",
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
