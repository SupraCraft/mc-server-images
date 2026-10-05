#!/usr/bin/env python3
"""Exact Java 26.3 runtime oracle for reusable architecture-only blueprints."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25575


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


def add(anchor: list[int], rel: list[int]) -> list[int]:
    return [int(anchor[i]) + int(rel[i]) for i in range(3)]


def xyz(values: list[int]) -> str:
    return " ".join(str(int(v)) for v in values)


def build_instance(process: subprocess.Popen[str], projection: dict[str, Any], anchor: list[int]) -> None:
    for op in projection["operations"]:
        if op["kind"] == "fill":
            send(
                process,
                f"fill {xyz(add(anchor, op['from']))} {xyz(add(anchor, op['to']))} {op['block']}",
            )
        elif op["kind"] == "setblock":
            send(process, f"setblock {xyz(add(anchor, op['at']))} {op['block']}")
        else:
            raise ValueError(f"unsupported architecture operation: {op['kind']!r}")


def verify_instance_command(projection: dict[str, Any], anchor: list[int], token: str) -> str:
    checks = []
    for op in projection["operations"]:
        if op["kind"] == "fill":
            checks.append(f"if block {xyz(add(anchor, op['from']))} {op['block']}")
            checks.append(f"if block {xyz(add(anchor, op['to']))} {op['block']}")
        elif op["kind"] == "setblock":
            checks.append(f"if block {xyz(add(anchor, op['at']))} {op['block']}")
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
        raise RuntimeError("architecture-only rep must not carry place identity")
    if projection.get("gameplay_structure_semantics") is not False:
        raise RuntimeError("architecture-only rep must not carry gameplay structure semantics")
    if projection.get("capabilities") != []:
        raise RuntimeError("architecture-only rep must not carry capabilities")
    if len(projection.get("instances", [])) != 2:
        raise RuntimeError("bounded rep expects exactly two instances")

    with tempfile.TemporaryDirectory(prefix="architecture-only-26.3-") as td:
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
                "motd=SupraCraft architecture-only RDTE",
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
                send(process, "forceload add -16 -16 32 16")

                first, second = projection["instances"]
                build_instance(process, projection, first["anchor"])
                build_instance(process, projection, second["anchor"])

                marker(
                    process,
                    verify_instance_command(
                        projection, first["anchor"], "SUPRACRAFT_ARCH_INSTANCE_ONE_PRESENT"
                    ),
                )
                marker(
                    process,
                    verify_instance_command(
                        projection, second["anchor"], "SUPRACRAFT_ARCH_INSTANCE_TWO_PRESENT"
                    ),
                )

                # Damage only the first instance; the second must remain intact.
                cap_at = add(first["anchor"], [0, 5, 0])
                send(process, f"setblock {xyz(cap_at)} minecraft:air")
                marker(
                    process,
                    f"execute unless block {xyz(cap_at)} minecraft:chiseled_stone_bricks "
                    "run say SUPRACRAFT_FIRST_INSTANCE_DAMAGED",
                )
                marker(
                    process,
                    verify_instance_command(
                        projection, second["anchor"], "SUPRACRAFT_SECOND_INSTANCE_INDEPENDENT"
                    ),
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
            "instance_one_present":"SUPRACRAFT_ARCH_INSTANCE_ONE_PRESENT",
            "instance_two_present":"SUPRACRAFT_ARCH_INSTANCE_TWO_PRESENT",
            "first_instance_damaged":"SUPRACRAFT_FIRST_INSTANCE_DAMAGED",
            "second_instance_independent":"SUPRACRAFT_SECOND_INSTANCE_INDEPENDENT",
        }
        observed={key:token in server_log for key,token in markers.items()}
        errors=[
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed=exit_code == 0 and all(observed.values()) and not errors

        result={
            "schema":"supracraft.architecture-only-runtime-rdte/v0.1",
            "minecraft":{"edition":"java","version":"26.3"},
            "status_protocol":int(status.get("version",{}).get("protocol",-1)),
            "official_server_verified":True,
            "blueprint_id":projection["blueprint_id"],
            "instance_count":2,
            "named_place_identity":False,
            "gameplay_structure_semantics":False,
            "capabilities":[],
            "oracles":observed,
            "server_error_count":len(errors),
            "result":"PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n","utf-8")
        print(json.dumps(result,indent=2,sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"architecture-only RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-7000:].replace(chr(10),' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
