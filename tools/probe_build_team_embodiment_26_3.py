#!/usr/bin/env python3
"""Exact Java 26.3 physical build-team embodiment RDTE.

This bounded rep exercises two real exact-version client actors:
- hauler: source container -> grounded walk -> registered hopper depot;
- builder: grounded walk -> explicit start-work control.

After the builder starts work, the already-qualified bounded construction
actuator is reused. This rep does not claim block-by-block NPC placement.
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
    refresh_bom_scores,
    run_builder,
    xyz,
)

PORT = 25577


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


def wait_file(path: Path, process: subprocess.Popen[str], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            out = process.stdout.read()[-6000:] if process.stdout is not None else ""
            raise RuntimeError(f"actor exited before {path.name}: {process.returncode}; {out!r}")
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def run_actor(
    root: Path,
    role: str,
    username: str,
    teleport: str,
    server: subprocess.Popen[str],
) -> dict[str, Any]:
    ready = root / f"{role}.ready"
    go = root / f"{role}.go"
    result_path = root / f"{role}.result.json"

    env = dict(os.environ)
    env.update({
        "MC_HOST": "127.0.0.1",
        "MC_PORT": str(PORT),
        "MC_USER": username,
        "ACTOR_ROLE": role,
        "ACTOR_READY_FILE": str(ready),
        "ACTOR_GO_FILE": str(go),
        "ACTOR_RESULT_FILE": str(result_path),
    })
    actor = subprocess.Popen(
        ["node", str(Path(__file__).with_name("probe_build_team_actor.js"))],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_file(ready, actor)
        send(server, f"tp {username} {teleport}")
        time.sleep(0.5)
        go.write_text("go\n", "utf-8")
        try:
            stdout, _ = actor.communicate(timeout=50)
        except subprocess.TimeoutExpired:
            actor.kill()
            stdout, _ = actor.communicate(timeout=10)
            raise RuntimeError(f"{role} actor timed out: {stdout[-6000:]}")
        if not result_path.exists():
            raise RuntimeError(f"{role} actor produced no result: {stdout[-6000:]}")
        result = json.loads(result_path.read_text("utf-8"))
        if actor.returncode != 0 or result.get("result") in ("error", "incomplete"):
            raise RuntimeError(
                f"{role} actor failed: {json.dumps(result, sort_keys=True)} "
                f"stdout={stdout[-6000:]}"
            )
        return result
    finally:
        if actor.poll() is None:
            actor.kill()
            actor.wait(timeout=10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--work-site", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    projection = json.loads(args.projection.read_text("utf-8"))
    work_site = json.loads(args.work_site.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    if projection.get("world_scan") is not False:
        raise RuntimeError("build-team embodiment forbids world scanning")
    if projection.get("actor_semantics", {}).get("physical_block_placement_by_builder") is not False:
        raise RuntimeError("rep must not overclaim physical block placement")

    with tempfile.TemporaryDirectory(prefix="build-team-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                "white-list=false",
                "enforce-whitelist=false",
                f"server-port={PORT}",
                "view-distance=4",
                "simulation-distance=3",
                "spawn-protection=0",
                "max-players=4",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft build team embodiment RDTE",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add -16 -16 16 16")
                send(server, "scoreboard objectives add supracraft_cap dummy")
                send(server, "scoreboard objectives add supracraft_metric dummy")
                send(server, "scoreboard objectives add supracraft_bom dummy")

                # Bounded, walkable test work site.
                send(server, "fill -12 69 -3 8 69 5 minecraft:stone")
                controller = xyz(work_site["controller"]["at"])
                depot = xyz(work_site["depot"]["at"])
                send(server, f"setblock {controller} {work_site['controller']['block']}")
                send(server, f"setblock {depot} {work_site['depot']['block']}")
                send(server, "setblock 1 70 0 minecraft:lever[face=floor,facing=north,powered=false]")
                for row in work_site["architecture_delta"]:
                    send(server, f"setblock {xyz(row['at'])} minecraft:air")

                # Explicit source stockpile with exactly the qualified BOM.
                send(server, "setblock -8 70 2 minecraft:barrel")
                send(server, "item replace block -8 70 2 container.0 with minecraft:cauldron 2")
                send(server, "item replace block -8 70 2 container.1 with minecraft:water_bucket")
                send(server, "item replace block -8 70 2 container.2 with minecraft:water_bucket")
                time.sleep(0.6)

                hauler = run_actor(
                    root,
                    "hauler",
                    projection["actors"]["hauler"]["username"],
                    "-7.5 70 3.5",
                    server,
                )

                refresh_bom_scores(server, work_site)
                marker(
                    server,
                    f"execute {full_bom_condition(work_site)} "
                    "run say SUPRACRAFT_HAULER_DEPOSITED_BOM",
                )
                if float(hauler.get("walk", {}).get("distance", 0)) < 4:
                    raise RuntimeError(f"hauler did not perform meaningful grounded movement: {hauler}")

                builder = run_actor(
                    root,
                    "builder",
                    projection["actors"]["builder"]["username"],
                    "6.5 70 0.5",
                    server,
                )
                if float(builder.get("walk", {}).get("distance", 0)) < 2:
                    raise RuntimeError(f"builder did not perform meaningful grounded movement: {builder}")

                marker(
                    server,
                    "execute if block 1 70 0 minecraft:lever[powered=true] "
                    "run say SUPRACRAFT_BUILDER_STARTED_WORK",
                )

                # Existing bounded construction engine remains the only actuator.
                run_builder(server, work_site)
                a0, a1 = work_site["architecture_delta"]
                marker(
                    server,
                    f"execute if block {xyz(a0['at'])} {a0['block']} "
                    f"if block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_BUILD_TEAM_ARCHITECTURE_COMPLETED",
                )

                for command in capability_eval_commands(work_site):
                    send(server, command)
                marker(
                    server,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_BUILD_TEAM_CAPABILITY_ACTIVATED",
                )

                refresh_bom_scores(server, work_site)
                marker(
                    server,
                    "execute if score bom_0 supracraft_bom matches 0 "
                    "if score bom_1 supracraft_bom matches 0 "
                    "run say SUPRACRAFT_BUILD_TEAM_MATERIALS_CONSUMED",
                )

                send(server, "save-all flush")
                time.sleep(0.3)
                send(server, "stop")
                exit_code = server.wait(timeout=45)
            finally:
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
            "hauler_deposited_bom": "SUPRACRAFT_HAULER_DEPOSITED_BOM",
            "builder_started_work": "SUPRACRAFT_BUILDER_STARTED_WORK",
            "architecture_completed": "SUPRACRAFT_BUILD_TEAM_ARCHITECTURE_COMPLETED",
            "capability_activated": "SUPRACRAFT_BUILD_TEAM_CAPABILITY_ACTIVATED",
            "materials_consumed": "SUPRACRAFT_BUILD_TEAM_MATERIALS_CONSUMED",
        }
        observed = {key: token in server_log for key, token in markers.items()}
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed = exit_code == 0 and all(observed.values()) and not errors

        result = {
            "schema": "supracraft.build-team-embodiment-runtime-rdte/v0.1",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "official_server_verified": True,
            "world_scan": False,
            "actors": {"hauler": hauler, "builder": builder},
            "physical_block_placement_by_builder": False,
            "reuse_existing_construction_engine": True,
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
                f"build-team embodiment failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-8000:].replace(chr(10), ' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
