#!/usr/bin/env python3
"""Exact Java 26.3 blueprint/depot work-site RDTE.

Proves an explicit pre-placed blueprint site with a hopper material depot:
- no global scanning;
- empty/partial materials do not build;
- complete bill of materials gates bounded construction;
- admitted materials are consumed;
- completed architecture activates the existing stock_watering capability;
- damaging required architecture revokes the capability.
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

PORT = 25573


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


def xyz(values: list[int]) -> str:
    if len(values) != 3:
        raise ValueError("coordinate must contain three integers")
    return " ".join(str(int(v)) for v in values)


def bom_totals(projection: dict[str, Any]) -> list[tuple[str, int]]:
    totals: dict[str, int] = {}
    for row in projection["depot"]["bill_of_materials"]:
        item = str(row.get("item", ""))
        count = int(row.get("count", 0))
        if not item.startswith("minecraft:") or count <= 0:
            raise ValueError("invalid bill_of_materials row")
        totals[item] = totals.get(item, 0) + count
    return sorted(totals.items())


def refresh_bom_scores(
    process: subprocess.Popen[str],
    projection: dict[str, Any],
) -> None:
    depot = xyz(projection["depot"]["at"])
    for index, (item, _required) in enumerate(bom_totals(projection)):
        holder = f"bom_{index}"
        send(process, f"scoreboard players set {holder} supracraft_bom 0")
        send(
            process,
            f"execute store result score {holder} supracraft_bom "
            f"if items block {depot} container.* {item}",
        )
    time.sleep(0.12)


def full_bom_condition(projection: dict[str, Any]) -> str:
    terms = []
    for index, (_item, required) in enumerate(bom_totals(projection)):
        terms.append(
            f"if score bom_{index} supracraft_bom matches {required}.."
        )
    return " ".join(terms)


def run_builder(process: subprocess.Popen[str], projection: dict[str, Any]) -> None:
    controller = xyz(projection["controller"]["at"])
    controller_block = projection["controller"]["block"]
    depot = xyz(projection["depot"]["at"])
    depot_block = projection["depot"]["block"]
    refresh_bom_scores(process, projection)
    bom = full_bom_condition(projection)

    # All construction commands are gated by controller + complete aggregate bill.
    for row in projection["architecture_delta"]:
        if row.get("kind") != "setblock":
            raise ValueError("bounded RDTE only supports setblock architecture deltas")
        send(
            process,
            f"execute if block {controller} {controller_block} "
            f"if block {depot} {depot_block} {bom} run "
            f"setblock {xyz(row['at'])} {row['block']}",
        )

    # Consume materials only after all required architecture predicates are true.
    arch = " ".join(
        f"if block {xyz(row['at'])} {row['block']}"
        for row in projection["architecture_delta"]
    )
    # Clear the admitted depot inventory after successful construction.
    # Re-setting the same hopper block can preserve its block-entity inventory,
    # so remove the Items list explicitly while leaving the depot in place.
    send(
        process,
        f"execute if block {controller} {controller_block} {arch} {bom} "
        f"run data remove block {depot} Items",
    )
    time.sleep(0.25)


def capability_eval_commands(projection: dict[str, Any]) -> list[str]:
    target_blocks = " ".join(
        f"if block {xyz(row['at'])} {row['block']}"
        for row in projection["architecture_delta"]
    )
    return [
        "scoreboard players set stock_watering supracraft_cap 0",
        "scoreboard players set husbandry_capacity supracraft_metric 8",
        f"execute {target_blocks} run scoreboard players set stock_watering supracraft_cap 1",
        (
            "execute if score stock_watering supracraft_cap matches 1 run "
            "scoreboard players set husbandry_capacity supracraft_metric 12"
        ),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    projection = json.loads(args.projection.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    if projection.get("initiation") != "blueprint_site":
        raise RuntimeError("RDTE requires blueprint_site initiation")
    if projection.get("world_scan") is not False:
        raise RuntimeError("RDTE forbids world scanning")
    if not projection.get("consume_materials_on_success"):
        raise RuntimeError("RDTE requires resource consumption on successful build")

    with tempfile.TemporaryDirectory(prefix="blueprint-depot-26.3-") as td:
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
                "motd=SupraCraft blueprint depot RDTE",
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
                send(process, "gamerule doMobSpawning false")
                send(process, "forceload add -16 -16 16 16")
                send(process, "scoreboard objectives add supracraft_cap dummy")
                send(process, "scoreboard objectives add supracraft_metric dummy")
                send(process, "scoreboard objectives add supracraft_bom dummy")

                controller = xyz(projection["controller"]["at"])
                depot = xyz(projection["depot"]["at"])
                send(process, f"setblock {controller} {projection['controller']['block']}")
                send(process, f"setblock {depot} {projection['depot']['block']}")
                for row in projection["architecture_delta"]:
                    send(process, f"setblock {xyz(row['at'])} minecraft:air")

                marker(
                    process,
                    f"execute if block {controller} {projection['controller']['block']} "
                    f"if block {depot} {projection['depot']['block']} "
                    "run say SUPRACRAFT_SITE_REGISTERED",
                )

                # Empty depot: build actuator must make no architectural change.
                run_builder(process, projection)
                a0, a1 = projection["architecture_delta"]
                marker(
                    process,
                    f"execute unless block {xyz(a0['at'])} {a0['block']} "
                    f"unless block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_EMPTY_DEPOT_NO_BUILD",
                )

                # Partial delivery: one cauldron + one water bucket.
                bill = projection["depot"]["bill_of_materials"]
                for row in (bill[0], bill[2]):
                    send(
                        process,
                        f"item replace block {depot} {row['slot']} with {row['item']}",
                    )
                run_builder(process, projection)
                marker(
                    process,
                    f"execute unless block {xyz(a0['at'])} {a0['block']} "
                    f"unless block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_PARTIAL_MATERIALS_NO_BUILD",
                )

                # Complete delivery and let the same bounded builder actuator run.
                for row in (bill[1], bill[3]):
                    send(
                        process,
                        f"item replace block {depot} {row['slot']} with {row['item']}",
                    )
                refresh_bom_scores(process, projection)
                marker(
                    process,
                    f"execute {full_bom_condition(projection)} "
                    "run say SUPRACRAFT_FULL_BOM_PRESENT",
                )
                run_builder(process, projection)

                marker(
                    process,
                    f"execute if block {xyz(a0['at'])} {a0['block']} "
                    f"if block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_ARCHITECTURE_COMPLETED",
                )

                # Depot reset after the successful build proves resource consumption.
                absent_terms = " ".join(
                    f"unless items block {depot} {row['slot']} {row['item']}"
                    for row in bill
                )
                marker(
                    process,
                    f"execute {absent_terms} run say SUPRACRAFT_MATERIALS_CONSUMED",
                )

                for command in capability_eval_commands(projection):
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_CAPABILITY_ACTIVATED",
                )

                # Damage one required architectural component and boundedly revalidate.
                send(process, f"setblock {xyz(a1['at'])} minecraft:air")
                for command in capability_eval_commands(projection):
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 0 "
                    "if score husbandry_capacity supracraft_metric matches 8 "
                    "run say SUPRACRAFT_DAMAGE_REVOKED",
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
            "site_registered":"SUPRACRAFT_SITE_REGISTERED",
            "empty_depot_no_build":"SUPRACRAFT_EMPTY_DEPOT_NO_BUILD",
            "partial_materials_no_build":"SUPRACRAFT_PARTIAL_MATERIALS_NO_BUILD",
            "full_bom_present":"SUPRACRAFT_FULL_BOM_PRESENT",
            "materials_consumed":"SUPRACRAFT_MATERIALS_CONSUMED",
            "architecture_completed":"SUPRACRAFT_ARCHITECTURE_COMPLETED",
            "capability_activated":"SUPRACRAFT_CAPABILITY_ACTIVATED",
            "damage_revoked":"SUPRACRAFT_DAMAGE_REVOKED",
        }
        observed={key: token in server_log for key,token in markers.items()}
        errors=[
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed=exit_code == 0 and all(observed.values()) and not errors

        result={
            "schema":"supracraft.blueprint-depot-runtime-rdte/v0.2",
            "minecraft":{"edition":"java","version":"26.3"},
            "status_protocol":int(status.get("version",{}).get("protocol",-1)),
            "official_server_verified":True,
            "work_site_id":projection["work_site_id"],
            "initiation":"blueprint_site",
            "world_scan":False,
            "material_depot":"minecraft:hopper",
            "bill_semantics":"aggregate_item_quantity",
            "oracles":observed,
            "semantic_effect":{"metric":"husbandry_capacity","base_value":8,"active_value":12,"unit":"animals"},
            "server_error_count":len(errors),
            "result":"PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n","utf-8")
        print(json.dumps(result,indent=2,sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"blueprint/depot RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-7000:].replace(chr(10),' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
