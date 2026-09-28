#!/usr/bin/env python3
"""Qualify one Mineflayer 4.39.0 physical placement against official Java 26.3."""

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
PORT = 25567
MARKER = "SUPRACRAFT_MINEFLAYER_PLACE_OK"


def write_server_config(root: Path) -> None:
    (root / "eula.txt").write_text("eula=true\n", "utf-8")
    (root / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
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
                "motd=SupraCraft Mineflayer placement qualification",
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


def wait_server(process: subprocess.Popen[str], protocol: int, timeout: int = 180) -> dict[str, Any]:
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
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()[-4000:]
            raise RuntimeError(
                f"bot exited before {path.name} appeared: "
                f"exit={process.returncode}; stdout={output!r}"
            )
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


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

    with tempfile.TemporaryDirectory(prefix="mineflayer-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
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

                # Build a deterministic, reachable placement fixture and make
                # its chunk a spawn chunk so the independent server oracle can
                # still evaluate it after the bot disconnects.
                send(server, "setworldspawn 0 70 0")
                send(server, "setblock 0 69 0 minecraft:stone")
                send(server, "setblock 0 70 0 minecraft:air")
                send(server, "setblock 1 100 0 minecraft:air")
                time.sleep(1)

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
                    ["node", str(Path(__file__).with_name("probe_mineflayer_place.js"))],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                try:
                    wait_file(ready, bot, 30)
                except RuntimeError as exc:
                    diagnostic = None
                    if bot_result_path.exists():
                        diagnostic = json.loads(
                            bot_result_path.read_text("utf-8")
                        )
                    raise RuntimeError(
                        f"{exc}; bot_result={diagnostic!r}"
                    ) from exc

                send(server, f"gamemode survival {BOT_NAME}")
                send(server, f"give {BOT_NAME} minecraft:stone 1")
                send(server, f"tp {BOT_NAME} 2 70 0 90 0")

                try:
                    bot_stdout, _ = bot.communicate(timeout=60)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    bot_stdout, _ = bot.communicate(timeout=10)
                    raise RuntimeError(
                        "Mineflayer worker timed out: " + bot_stdout[-4000:]
                    )

                if not bot_result_path.exists():
                    raise RuntimeError(
                        "Mineflayer worker produced no result: " + bot_stdout[-4000:]
                    )
                bot_result = json.loads(bot_result_path.read_text("utf-8"))
                if bot.returncode != 0 or not bot_result.get("placed"):
                    raise RuntimeError(
                        "Mineflayer placement failed: "
                        + json.dumps(bot_result, sort_keys=True)
                        + " stdout="
                        + bot_stdout[-4000:]
                    )

                # Independent server-side condition: if the bot really left
                # stone at the target, the server itself emits a marker.
                send(
                    server,
                    "execute if block 0 70 0 minecraft:stone "
                    f"run say {MARKER}",
                )
                time.sleep(2)

                send(server, "stop")
                try:
                    exit_code = server.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    server.kill()
                    exit_code = server.wait(timeout=10)

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

        if exit_code != 0:
            raise RuntimeError(f"server exit code {exit_code}")
        server_verified = MARKER in server_log
        if not server_verified:
            raise RuntimeError(
                "official server did not emit placement verification marker"
            )
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
        "schema": "supracraft.mineflayer-java-placement/v0.1",
        "minecraft": {
            "edition": "java",
            "version": "26.3",
            "protocol": protocol,
            "world_version": int(info["world_version"]),
        },
        "mineflayer": bot_result,
        "fixture": {
            "support": {"at": [0, 69, 0], "block": "minecraft:stone"},
            "target": {"at": [0, 70, 0], "block": "minecraft:stone"},
            "bot_teleport": [2, 70, 0],
        },
        "official_server_verified": server_verified,
        "status_protocol": int(status.get("version", {}).get("protocol", -1)),
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
