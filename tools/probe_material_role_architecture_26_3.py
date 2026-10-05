#!/usr/bin/env python3
"""Exact Java 26.3 runtime oracle for civilization-aware material lowering.

The same reusable architecture blueprint is instantiated twice with different
material-role decisions. This proves material/context variation without adding
named-place identity or gameplay-structure semantics.
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

PORT = 25579


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


def add(anchor: list[int], rel: list[int]) -> list[int]:
    return [int(anchor[i]) + int(rel[i]) for i in range(3)]


def xyz(values: list[int]) -> str:
    return " ".join(str(int(v)) for v in values)


def material_block(variant: dict[str, Any], role: str) -> str:
    decisions = variant.get("material_decisions", {})
    if role not in decisions:
        raise ValueError(f"missing material decision for role {role}")
    block = decisions[role].get("selected_block")
    if not isinstance(block, str) or not block.startswith("minecraft:"):
        raise ValueError(f"invalid selected block for role {role}")
    return block


def build_variant(process: subprocess.Popen[str], projection: dict[str, Any], variant: dict[str, Any]) -> None:
    anchor = variant["anchor"]
    for op in projection["operations"]:
        block = material_block(variant, op["role"])
        if op["kind"] == "fill":
            send(
                process,
                f"fill {xyz(add(anchor, op['from']))} {xyz(add(anchor, op['to']))} {block}",
            )
        elif op["kind"] == "setblock":
            send(process, f"setblock {xyz(add(anchor, op['at']))} {block}")
        else:
            raise ValueError(f"unsupported operation kind: {op['kind']!r}")


def verify_variant_command(projection: dict[str, Any], variant: dict[str, Any], token: str) -> str:
    anchor = variant["anchor"]
    checks = []
    for op in projection["operations"]:
        block = material_block(variant, op["role"])
        if op["kind"] == "fill":
            checks.append(f"if block {xyz(add(anchor, op['from']))} {block}")
            checks.append(f"if block {xyz(add(anchor, op['to']))} {block}")
        elif op["kind"] == "setblock":
            checks.append(f"if block {xyz(add(anchor, op['at']))} {block}")
    return f"execute {' '.join(checks)} run say {token}"


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
        raise RuntimeError("probe requires exact Java 26.3")
    protocol = int(info["protocol_version"])

    if projection.get("named_place_identity") is not False:
        raise RuntimeError("material-variation rep must not carry named-place identity")
    if projection.get("gameplay_structure_semantics") is not False:
        raise RuntimeError("material-variation rep must not carry gameplay structure semantics")
    if projection.get("world_scan") is not False:
        raise RuntimeError("material-variation rep forbids world scanning")
    variants = projection.get("variants", [])
    if len(variants) != 2:
        raise RuntimeError("bounded rep expects exactly two material variants")

    with tempfile.TemporaryDirectory(prefix="material-lowering-26.3-") as td:
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
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft material lowering RDTE",
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
                send(server, "forceload add -16 -16 32 16")

                early, brick = variants
                build_variant(server, projection, early)
                build_variant(server, projection, brick)

                marker(
                    server,
                    verify_variant_command(
                        projection, early, "SUPRACRAFT_EARLY_STONE_VARIANT_PRESENT"
                    ),
                )
                marker(
                    server,
                    verify_variant_command(
                        projection, brick, "SUPRACRAFT_FIRED_BRICK_VARIANT_PRESENT"
                    ),
                )

                early_block = material_block(early, "masonry_primary")
                brick_block = material_block(brick, "masonry_primary")
                if early_block == brick_block:
                    raise RuntimeError("material contexts did not produce distinct lowered blocks")
                marker(server, "say SUPRACRAFT_MATERIAL_CONTEXTS_DISTINCT")

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
            "early_stone_variant_present":"SUPRACRAFT_EARLY_STONE_VARIANT_PRESENT",
            "fired_brick_variant_present":"SUPRACRAFT_FIRED_BRICK_VARIANT_PRESENT",
            "material_contexts_distinct":"SUPRACRAFT_MATERIAL_CONTEXTS_DISTINCT",
        }
        observed={key:token in server_log for key,token in markers.items()}
        errors=[
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed=exit_code == 0 and all(observed.values()) and not errors

        result={
            "schema":"supracraft.material-role-architecture-runtime-rdte/v0.1",
            "minecraft":{"edition":"java","version":"26.3"},
            "status_protocol":int(status.get("version",{}).get("protocol",-1)),
            "official_server_verified":True,
            "blueprint_id":projection["blueprint_id"],
            "named_place_identity":False,
            "gameplay_structure_semantics":False,
            "world_scan":False,
            "variants":[
                {
                    "context_id":row["context_id"],
                    "selected_materials":{
                        role:decision["selected_block"]
                        for role,decision in row["material_decisions"].items()
                    }
                }
                for row in variants
            ],
            "oracles":observed,
            "server_error_count":len(errors),
            "result":"PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n","utf-8")
        print(json.dumps(result,indent=2,sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"material-lowering RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-7000:].replace(chr(10),' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
