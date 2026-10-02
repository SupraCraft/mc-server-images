#!/usr/bin/env python3
"""Qualify exact-26.3 vanilla player-region selector semantics with a real player."""

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


BOT_NAME = "SupraCraftSelectorProbe"
PORT = 25568

AABB_SELECTOR = "@a[x=-1,y=69,z=-1,dx=2,dy=3,dz=2]"
DISTANCE_SELECTOR = "@a[distance=..1.5]"

INSIDE_AABB = "SUPRACRAFT_REGION_AABB_INSIDE_OK"
OUTSIDE_AABB_UNEXPECTED = "SUPRACRAFT_REGION_AABB_OUTSIDE_UNEXPECTED"
INSIDE_DISTANCE = "SUPRACRAFT_REGION_DISTANCE_INSIDE_OK"
OUTSIDE_DISTANCE_UNEXPECTED = "SUPRACRAFT_REGION_DISTANCE_OUTSIDE_UNEXPECTED"


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
                "motd=SupraCraft selector qualification",
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
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()[-4000:]
            raise RuntimeError(
                f"bot exited before {path.name} appeared: "
                f"exit={process.returncode}; stdout={output!r}"
            )
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def count_marker(log: str, marker: str) -> int:
    return sum(marker in line for line in log.splitlines())


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

    with tempfile.TemporaryDirectory(prefix="selector-26.3-") as td:
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

            bot: subprocess.Popen[str] | None = None
            exit_code: int | None = None
            try:
                status = wait_server(server, protocol)

                send(server, "forceload add 0 0")
                send(server, "setworldspawn 0 70 0")
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
                    if bot.poll() is None:
                        bot.terminate()
                        try:
                            bot_stdout, _ = bot.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            bot.kill()
                            bot_stdout, _ = bot.communicate(timeout=5)
                    else:
                        bot_stdout = ""
                        if bot.stdout is not None:
                            bot_stdout = bot.stdout.read()
                    diagnostic = None
                    if bot_result_path.exists():
                        diagnostic = json.loads(
                            bot_result_path.read_text("utf-8")
                        )
                    log.flush()
                    server_tail = log_path.read_text(
                        "utf-8", errors="replace"
                    )[-5000:]
                    raise RuntimeError(
                        f"{exc}; bot_result={diagnostic!r}; "
                        f"bot_stdout={bot_stdout[-4000:]!r}; "
                        f"server_tail={server_tail!r}"
                    ) from exc

                # Positive: same real player, authoritative server teleport,
                # selector evaluation entirely by vanilla server.
                send(server, f"tp {BOT_NAME} 0 70 0 0 0")
                time.sleep(1)
                send(
                    server,
                    f"execute if entity {AABB_SELECTOR} run say {INSIDE_AABB}",
                )
                send(
                    server,
                    "execute positioned 0 70 0 "
                    f"if entity {DISTANCE_SELECTOR} run say {INSIDE_DISTANCE}",
                )
                time.sleep(1)

                # Hard negative: unchanged selector after moving the same
                # connected player well outside the authored region.
                send(server, f"tp {BOT_NAME} 10 70 0 0 0")
                time.sleep(1)
                send(
                    server,
                    "execute if entity "
                    f"{AABB_SELECTOR} run say {OUTSIDE_AABB_UNEXPECTED}",
                )
                send(
                    server,
                    "execute positioned 0 70 0 "
                    f"if entity {DISTANCE_SELECTOR} "
                    f"run say {OUTSIDE_DISTANCE_UNEXPECTED}",
                )
                time.sleep(2)

                send(server, "stop")
                try:
                    exit_code = server.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    server.kill()
                    exit_code = server.wait(timeout=10)

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

        if exit_code != 0:
            raise RuntimeError(f"server exit code {exit_code}")
        if not bot_result_path.exists():
            raise RuntimeError(
                "Mineflayer presence worker produced no result; "
                + bot_stdout[-4000:]
            )
        bot_result = json.loads(bot_result_path.read_text("utf-8"))
        if "spawn" not in bot_result.get("milestones", {}):
            raise RuntimeError(
                "Mineflayer player never reached spawn: "
                + json.dumps(bot_result, sort_keys=True)
            )
        if bot_result.get("error"):
            raise RuntimeError(
                "Mineflayer presence worker error: "
                + json.dumps(bot_result, sort_keys=True)
            )

        marker_counts = {
            "inside_aabb": count_marker(server_log, INSIDE_AABB),
            "outside_aabb_unexpected": count_marker(
                server_log, OUTSIDE_AABB_UNEXPECTED
            ),
            "inside_distance": count_marker(server_log, INSIDE_DISTANCE),
            "outside_distance_unexpected": count_marker(
                server_log, OUTSIDE_DISTANCE_UNEXPECTED
            ),
        }

        if marker_counts["inside_aabb"] != 1:
            raise RuntimeError(
                "AABB selector did not produce exactly one inside marker: "
                + json.dumps(marker_counts, sort_keys=True)
            )
        if marker_counts["outside_aabb_unexpected"] != 0:
            raise RuntimeError(
                "AABB selector matched player outside region: "
                + json.dumps(marker_counts, sort_keys=True)
            )
        if marker_counts["inside_distance"] != 1:
            raise RuntimeError(
                "distance selector did not produce exactly one inside marker: "
                + json.dumps(marker_counts, sort_keys=True)
            )
        if marker_counts["outside_distance_unexpected"] != 0:
            raise RuntimeError(
                "distance selector matched player outside radius: "
                + json.dumps(marker_counts, sort_keys=True)
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
        "schema": "supracraft.vanilla-player-region-selector/v0.1",
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
        },
        "region": {
            "inside_position": [0, 70, 0],
            "outside_position": [10, 70, 0],
            "aabb_selector": AABB_SELECTOR,
            "distance_selector": DISTANCE_SELECTOR,
            "distance_origin": [0, 70, 0],
        },
        "oracle": {
            "authority": "official_vanilla_server",
            "marker_counts": marker_counts,
            "inside_aabb": True,
            "outside_aabb": False,
            "inside_distance": True,
            "outside_distance": False,
            "server_error_log_count": len(error_lines),
        },
        "status_protocol": int(status.get("version", {}).get("protocol", -1)),
        "result": "qualified",
        "limitations": [
            "qualifies only the exact selector shapes and coordinates in this receipt",
            "does not qualify arbitrary selector predicates or client-side perception",
            "Mineflayer supplies a real connected player but is not the selector oracle",
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
