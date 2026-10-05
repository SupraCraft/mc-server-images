#!/usr/bin/env python3
"""Exact Java 26.3 architect/build-team logistics RDTE.

This rep proves only the orchestration bridge:
architect-selected team + explicit source stockpiles + deterministic haul plan
-> existing qualified blueprint/depot work-site actuator.

It does not claim physical NPC pathfinding/navigation qualification.
"""

from __future__ import annotations

import argparse
import json
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

PORT = 25574


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def marker(process: subprocess.Popen[str], command: str) -> None:
    send(process, command)
    time.sleep(0.12)


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


def find_stockpile(plan: dict[str, Any], source_id: str) -> dict[str, Any]:
    for source in plan.get("source_stockpiles", []):
        if source.get("id") == source_id:
            return source
    raise ValueError(f"unknown source stockpile: {source_id}")


def source_slot_item(source: dict[str, Any], slot: str) -> str:
    for row in source.get("slots", []):
        if row.get("slot") == slot:
            return str(row.get("item"))
    raise ValueError(f"source slot not declared: {source.get('id')} {slot}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--work-site", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    plan = json.loads(args.plan.read_text("utf-8"))
    work_site = json.loads(args.work_site.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    if plan.get("world_scan") is not False:
        raise RuntimeError("architect logistics RDTE forbids world scanning")
    if plan.get("actor_semantics", {}).get("physical_navigation_qualified") is not False:
        raise RuntimeError("this rep must not claim physical navigation qualification")

    team = plan.get("team", {})
    if set(team) != {"architect", "builder", "hauler"}:
        raise RuntimeError("team must contain architect, builder and hauler")
    if len(set(team.values())) != 3:
        raise RuntimeError("bounded RDTE expects three distinct recruited actors")

    with tempfile.TemporaryDirectory(prefix="architect-logistics-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                f"server-port={PORT}",
                "view-distance=2",
                "simulation-distance=2",
                "spawn-protection=0",
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft architect logistics RDTE",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                status = wait_server(process, protocol)
                send(process, "forceload add -16 -16 16 16")
                send(process, "scoreboard objectives add supracraft_cap dummy")
                send(process, "scoreboard objectives add supracraft_metric dummy")
                send(process, "scoreboard objectives add supracraft_bom dummy")

                controller = xyz(work_site["controller"]["at"])
                depot = xyz(work_site["depot"]["at"])
                send(process, f"setblock {controller} {work_site['controller']['block']}")
                send(process, f"setblock {depot} {work_site['depot']['block']}")
                for row in work_site["architecture_delta"]:
                    send(process, f"setblock {xyz(row['at'])} minecraft:air")

                marker(
                    process,
                    "say SUPRACRAFT_TEAM_PLAN_ADMITTED",
                )

                # Materialize the two explicit source stockpiles from the plan.
                for source in plan["source_stockpiles"]:
                    pos = xyz(source["at"])
                    send(process, f"setblock {pos} {source['block']}")
                    for row in source["slots"]:
                        send(
                            process,
                            f"item replace block {pos} {row['slot']} with {row['item']}",
                        )

                # Execute only the declared haul tasks. Copy from the explicit
                # source slot to the explicit depot slot, then clear source
                # inventories after their planned transfers are complete.
                touched_sources: set[str] = set()
                for task in plan["haul_tasks"]:
                    if task.get("actor_id") != team["hauler"]:
                        raise RuntimeError("haul task assigned to non-recruited hauler")
                    source = find_stockpile(plan, task["source_id"])
                    if source_slot_item(source, task["source_slot"]) != task["item"]:
                        raise RuntimeError("haul plan/source inventory mismatch")
                    source_pos = xyz(source["at"])
                    send(
                        process,
                        f"item replace block {depot} {task['depot_slot']} "
                        f"from block {source_pos} {task['source_slot']}",
                    )
                    touched_sources.add(task["source_id"])

                for source_id in sorted(touched_sources):
                    source = find_stockpile(plan, source_id)
                    send(process, f"data remove block {xyz(source['at'])} Items")

                refresh_bom_scores(process, work_site)
                marker(
                    process,
                    f"execute {full_bom_condition(work_site)} "
                    "run say SUPRACRAFT_HAUL_PLAN_DELIVERED",
                )

                # Verify all planned sources are empty after admitted delivery.
                source_absence = []
                for source in plan["source_stockpiles"]:
                    pos = xyz(source["at"])
                    for row in source["slots"]:
                        source_absence.append(
                            f"unless items block {pos} {row['slot']} {row['item']}"
                        )
                marker(
                    process,
                    f"execute {' '.join(source_absence)} "
                    "run say SUPRACRAFT_SOURCE_STOCKPILES_DECREMENTED",
                )

                # Reuse the already-qualified construction engine.
                run_builder(process, work_site)
                a0, a1 = work_site["architecture_delta"]
                marker(
                    process,
                    f"execute if block {xyz(a0['at'])} {a0['block']} "
                    f"if block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_BUILD_TEAM_CONSTRUCTED",
                )

                for command in capability_eval_commands(work_site):
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_CAPABILITY_ACTIVATED",
                )

                send(process, "save-all flush")
                time.sleep(0.3)
                send(process, "stop")
                exit_code = process.wait(timeout=45)
            finally:
                if process.poll() is None:
                    try:
                        send(process, "stop")
                        process.wait(timeout=20)
                    except Exception:
                        process.kill()
                        process.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        markers = {
            "team_plan_admitted":"SUPRACRAFT_TEAM_PLAN_ADMITTED",
            "haul_plan_delivered":"SUPRACRAFT_HAUL_PLAN_DELIVERED",
            "source_stockpiles_decremented":"SUPRACRAFT_SOURCE_STOCKPILES_DECREMENTED",
            "build_team_constructed":"SUPRACRAFT_BUILD_TEAM_CONSTRUCTED",
            "capability_activated":"SUPRACRAFT_CAPABILITY_ACTIVATED",
        }
        observed = {key: token in server_log for key, token in markers.items()}
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed = exit_code == 0 and all(observed.values()) and not errors

        result = {
            "schema":"supracraft.architect-logistics-runtime-rdte/v0.1",
            "minecraft":{"edition":"java","version":"26.3"},
            "status_protocol":int(status.get("version",{}).get("protocol",-1)),
            "official_server_verified":True,
            "order_id":plan["order_id"],
            "team":team,
            "physical_navigation_qualified":False,
            "reuse_existing_construction_engine":True,
            "world_scan":False,
            "oracles":observed,
            "semantic_effect":{
                "metric":"husbandry_capacity",
                "base_value":8,
                "active_value":12,
                "unit":"animals"
            },
            "server_error_count":len(errors),
            "result":"PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n","utf-8")
        print(json.dumps(result,indent=2,sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"architect logistics RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-7000:].replace(chr(10),' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
