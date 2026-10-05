#!/usr/bin/env python3
"""Exact Java 26.3 player-facing blueprint/depot interaction RDTE.

A real exact-26.3 protocol client receives materials, opens the registered
hopper, and deposits the bill of materials through normal container operations.
The existing bounded work-site actuator then consumes those materials, builds
the architectural delta, and activates the already-qualified capability.

This proves the player interaction surface without introducing world scanning
or a second construction engine.
"""

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
from probe_blueprint_depot_26_3 import (
    capability_eval_commands,
    full_bom_condition,
    run_builder,
    xyz,
)

PORT = 25576
BOT_NAME = "SupraCraftBuilder"


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def marker(process: subprocess.Popen[str], command: str) -> None:
    send(process, command)
    time.sleep(0.15)


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
            out = process.stdout.read()[-5000:] if process.stdout is not None else ""
            raise RuntimeError(
                f"client exited before {path.name}: {process.returncode}; {out!r}"
            )
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--work-site", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    work_site = json.loads(args.work_site.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    if work_site.get("world_scan") is not False:
        raise RuntimeError("player-depot RDTE forbids world scanning")
    if work_site.get("initiation") != "blueprint_site":
        raise RuntimeError("player-depot RDTE requires blueprint_site")

    with tempfile.TemporaryDirectory(prefix="player-depot-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
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
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft player depot RDTE",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "server.log"
        client_result_path = root / "client-result.json"
        ready = root / "client.ready"
        go = root / "client.go"

        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            bot = None
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add -16 -16 16 16")
                send(server, "scoreboard objectives add supracraft_cap dummy")
                send(server, "scoreboard objectives add supracraft_metric dummy")

                controller = xyz(work_site["controller"]["at"])
                depot = xyz(work_site["depot"]["at"])
                send(server, f"setblock {controller} {work_site['controller']['block']}")
                send(server, f"setblock {depot} {work_site['depot']['block']}")
                for row in work_site["architecture_delta"]:
                    send(server, f"setblock {xyz(row['at'])} minecraft:air")
                send(server, "setworldspawn 0 70 5")
                time.sleep(0.5)

                env = dict(os.environ)
                env.update({
                    "MC_HOST": "127.0.0.1",
                    "MC_PORT": str(PORT),
                    "MC_USER": BOT_NAME,
                    "BOT_READY_FILE": str(ready),
                    "BOT_GO_FILE": str(go),
                    "BOT_RESULT_FILE": str(client_result_path),
                })
                bot = subprocess.Popen(
                    ["node", str(Path(__file__).with_name("probe_player_blueprint_depot.js"))],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_file(ready, bot, 45)

                # Materials are supplied to the player actor; all movement into
                # the work-site depot after this point is a real client
                # inventory/container operation.
                send(server, f"tp {BOT_NAME} 0 70 4")
                send(server, f"give {BOT_NAME} minecraft:cauldron 2")
                send(server, f"give {BOT_NAME} minecraft:water_bucket 2")
                time.sleep(0.75)
                go.write_text("go\n", "utf-8")

                try:
                    client_stdout, _ = bot.communicate(timeout=45)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    client_stdout, _ = bot.communicate(timeout=10)
                    raise RuntimeError("player client timed out: " + client_stdout[-5000:])

                if not client_result_path.exists():
                    raise RuntimeError("player client produced no result: " + client_stdout[-5000:])
                client_result = json.loads(client_result_path.read_text("utf-8"))
                if bot.returncode != 0 or client_result.get("result") != "deposited":
                    raise RuntimeError(
                        "player client failed: "
                        + json.dumps(client_result, sort_keys=True)
                        + " stdout="
                        + client_stdout[-5000:]
                    )

                marker(
                    server,
                    f"execute {full_bom_condition(work_site)} "
                    "run say SUPRACRAFT_PLAYER_BOM_DEPOSITED",
                )

                run_builder(server, work_site)
                a0, a1 = work_site["architecture_delta"]
                marker(
                    server,
                    f"execute if block {xyz(a0['at'])} {a0['block']} "
                    f"if block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_PLAYER_INITIATED_BUILD_COMPLETED",
                )

                for command in capability_eval_commands(work_site):
                    send(server, command)
                marker(
                    server,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_PLAYER_BUILD_CAPABILITY_ACTIVATED",
                )

                # The builder consumes the accepted materials after successful
                # construction; the depot must be empty of the submitted BOM.
                absent_terms = " ".join(
                    f"unless items block {depot} {row['slot']} {row['item']}"
                    for row in work_site["depot"]["bill_of_materials"]
                )
                marker(
                    server,
                    f"execute {absent_terms} run say SUPRACRAFT_PLAYER_MATERIALS_CONSUMED",
                )

                send(server, "save-all flush")
                time.sleep(0.3)
                send(server, "stop")
                exit_code = server.wait(timeout=45)
            finally:
                if bot is not None and bot.poll() is None:
                    bot.kill()
                    bot.wait(timeout=10)
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        markers = {
            "player_bom_deposited": "SUPRACRAFT_PLAYER_BOM_DEPOSITED",
            "player_initiated_build_completed": "SUPRACRAFT_PLAYER_INITIATED_BUILD_COMPLETED",
            "capability_activated": "SUPRACRAFT_PLAYER_BUILD_CAPABILITY_ACTIVATED",
            "materials_consumed": "SUPRACRAFT_PLAYER_MATERIALS_CONSUMED",
        }
        observed = {key: token in server_log for key, token in markers.items()}
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed = exit_code == 0 and all(observed.values()) and not errors

        result = {
            "schema": "supracraft.player-blueprint-depot-runtime-rdte/v0.1",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "official_server_verified": True,
            "client": client_result,
            "work_site_id": work_site["work_site_id"],
            "initiation": "player_material_delivery",
            "client_inventory_interaction": True,
            "reuse_existing_construction_engine": True,
            "world_scan": False,
            "oracles": observed,
            "semantic_effect": {
                "metric": "husbandry_capacity",
                "base_value": 8,
                "active_value": 12,
                "unit": "animals",
            },
            "server_error_count": len(errors),
            "result": "PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"player blueprint/depot RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-7000:].replace(chr(10), ' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
