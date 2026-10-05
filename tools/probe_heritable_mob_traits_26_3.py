#!/usr/bin/env python3
"""Qualify exact Java 26.3 vanilla mob traits and bounded Growth outcomes."""

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
ROLL_OBJECTIVE = "supracraft_roll"
PROBE_OBJECTIVE = "supracraft_probe"

TRAITS = {
    "large": {
        "tag": "supracraft.large",
        "modifiers": [
            ("minecraft:scale", "supracraft:large_scale", 350),
            ("minecraft:max_health", "supracraft:large_health", 250),
        ],
    },
    "swift": {
        "tag": "supracraft.swift",
        "modifiers": [
            ("minecraft:movement_speed", "supracraft:swift_speed", 200),
        ],
    },
    "fierce": {
        "tag": "supracraft.fierce",
        "modifiers": [
            ("minecraft:attack_damage", "supracraft:fierce_damage", 250),
        ],
    },
}

ROLL_CASES = {
    1: {"large"},
    80: {"large"},
    81: {"large", "fierce"},
    95: {"large", "fierce"},
    96: {"large", "swift"},
    100: {"large", "swift"},
}


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
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft vanilla heritable mob trait qualification",
                "",
            ]
        ),
        "utf-8",
    )


def write_datapack(root: Path) -> dict[str, Any]:
    pack = root / "world" / "datapacks" / "supracraft_traits"
    fn = pack / "data" / "supracraft_traits" / "function"
    fn.mkdir(parents=True, exist_ok=True)

    metadata = {
        "pack": {
            "description": "SupraCraft exact 26.3 bounded mob-trait RDTE",
            "min_format": [121, 0],
            "max_format": [121, 0],
        }
    }
    (pack / "pack.mcmeta").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        "utf-8",
    )

    functions: dict[str, list[str]] = {
        "setup": [
            f"scoreboard objectives add {ROLL_OBJECTIVE} dummy",
            f"scoreboard objectives add {PROBE_OBJECTIVE} dummy",
        ],
        "apply/large": [
            "execute unless entity @s[tag=supracraft.large] run attribute @s minecraft:scale modifier add supracraft:large_scale 0.35 add_multiplied_base",
            "execute unless entity @s[tag=supracraft.large] run attribute @s minecraft:max_health modifier add supracraft:large_health 0.25 add_multiplied_base",
            "tag @s add supracraft.large",
        ],
        "apply/swift": [
            "execute unless entity @s[tag=supracraft.swift] run attribute @s minecraft:movement_speed modifier add supracraft:swift_speed 0.20 add_multiplied_base",
            "tag @s add supracraft.swift",
        ],
        "apply/fierce": [
            "execute unless entity @s[tag=supracraft.fierce] run attribute @s minecraft:attack_damage modifier add supracraft:fierce_damage 0.25 add_multiplied_base",
            "tag @s add supracraft.fierce",
        ],
        "growth/resolve": [
            f"execute if score @s {ROLL_OBJECTIVE} matches 1..80 run function supracraft_traits:apply/large",
            f"execute if score @s {ROLL_OBJECTIVE} matches 81..95 run function supracraft_traits:apply/large",
            f"execute if score @s {ROLL_OBJECTIVE} matches 81..95 run function supracraft_traits:apply/fierce",
            f"execute if score @s {ROLL_OBJECTIVE} matches 96..100 run function supracraft_traits:apply/large",
            f"execute if score @s {ROLL_OBJECTIVE} matches 96..100 run function supracraft_traits:apply/swift",
        ],
        "growth/cast": [
            f"execute store result score @s {ROLL_OBJECTIVE} run random value 1..100",
            "function supracraft_traits:growth/resolve",
        ],
        "inherit/from_marked_source": [
            "execute if entity @e[tag=supracraft.inherit_source,tag=supracraft.large,limit=1] run function supracraft_traits:apply/large",
            "execute if entity @e[tag=supracraft.inherit_source,tag=supracraft.swift,limit=1] run function supracraft_traits:apply/swift",
            "execute if entity @e[tag=supracraft.inherit_source,tag=supracraft.fierce,limit=1] run function supracraft_traits:apply/fierce",
        ],
    }

    for name, commands in functions.items():
        path = fn / f"{name}.mcfunction"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(commands) + "\n", "utf-8")

    return {
        "metadata": metadata,
        "namespace": "supracraft_traits",
        "functions": functions,
        "traits": TRAITS,
        "growth_rolls": {
            "1..80": ["large"],
            "81..95": ["large", "fierce"],
            "96..100": ["large", "swift"],
        },
        "inheritance": {
            "mode": "explicit_marked_source_child_side_resolver",
            "source_tag": "supracraft.inherit_source",
            "natural_breeding_binding": "not_claimed_v0",
        },
    }


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


def marker_count(path: Path, marker: str) -> int:
    if not path.exists():
        return 0
    text = path.read_text("utf-8", errors="replace")
    return sum(marker in line for line in text.splitlines())


def wait_for_marker(
    path: Path, marker: str, baseline: int, timeout: float = 8.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker_count(path, marker) > baseline:
            return
        time.sleep(0.1)
    tail = path.read_text("utf-8", errors="replace")[-5000:]
    raise RuntimeError(f"marker timeout: {marker}; server_tail={tail!r}")


def say_if(
    process: subprocess.Popen[str],
    log_path: Path,
    marker: str,
    predicate: str,
) -> None:
    baseline = marker_count(log_path, marker)
    send(process, f"{predicate} run say {marker}")
    wait_for_marker(log_path, marker, baseline)


def summon_fixture(
    process: subprocess.Popen[str],
    entity_type: str,
    fixture_tag: str,
    x: float,
) -> None:
    """Summon one bounded fixture, then assign its test identity explicitly."""
    extra = ",IsImmuneToZombification:1b" if entity_type == "hoglin" else ""
    nbt = (
        "{NoAI:1b,NoGravity:1b,Invulnerable:1b,PersistenceRequired:1b"
        f"{extra}}}"
    )
    send(process, f"summon minecraft:{entity_type} {x} 100 0 {nbt}")
    # Do not depend on summon-NBT custom tag ingestion for harness identity.
    # The exact coordinate has just received one entity of the requested type.
    send(
        process,
        (
            f"tag @e[type=minecraft:{entity_type},x={x},y=100,z=0,"
            f"distance=..0.75,limit=1] add {fixture_tag}"
        ),
    )


def reset_probe_scores(process: subprocess.Popen[str]) -> None:
    for holder in ("#a", "#b", "#c", "#d"):
        send(process, f"scoreboard players set {holder} {PROBE_OBJECTIVE} -999")


def verify_entity(
    process: subprocess.Popen[str],
    log_path: Path,
    fixture_tag: str,
    expected_traits: set[str],
    marker: str,
) -> None:
    """Verify semantic tags and modifier amounts with separable diagnostics."""
    reset_probe_scores(process)
    holders = iter(("#a", "#b", "#c", "#d"))
    modifier_checks: list[tuple[str, int, str, str]] = []

    # First collect every expected modifier value.  Keep the score even when the
    # query fails so the following scoreboard get leaves a useful first-failure
    # diagnostic in the official server log.
    for trait in ("large", "swift", "fierce"):
        if trait not in expected_traits:
            continue
        for attribute_id, modifier_id, expected_scaled_value in TRAITS[trait][
            "modifiers"
        ]:
            holder = next(holders)
            send(
                process,
                (
                    f"execute as @e[tag={fixture_tag},limit=1] "
                    f"store result score {holder} {PROBE_OBJECTIVE} "
                    f"run attribute @s {attribute_id} modifier value get "
                    f"{modifier_id} 1000"
                ),
            )
            send(process, f"scoreboard players get {holder} {PROBE_OBJECTIVE}")
            modifier_checks.append(
                (holder, expected_scaled_value, attribute_id, modifier_id)
            )

    tag_checks: list[str] = []
    for trait in ("large", "swift", "fierce"):
        tag = TRAITS[trait]["tag"]
        if trait in expected_traits:
            tag_checks.append(f"if entity @s[tag={tag}]")
        else:
            tag_checks.append(f"unless entity @s[tag={tag}]")

    # Split tag and modifier assertions so a failed composite predicate does not
    # hide whether the datapack function ran or only an attribute oracle differs.
    say_if(
        process,
        log_path,
        marker + "_TAGS",
        " ".join(
            [
                f"execute as @e[tag={fixture_tag},limit=1]",
                *tag_checks,
            ]
        ),
    )

    for index, (holder, expected, attribute_id, modifier_id) in enumerate(
        modifier_checks
    ):
        say_if(
            process,
            log_path,
            f"{marker}_MOD_{index}",
            (
                f"execute if score {holder} {PROBE_OBJECTIVE} "
                f"matches {expected}"
            ),
        )

    # Emit the original aggregate marker only after all split assertions pass.
    baseline = marker_count(log_path, marker)
    send(process, f"say {marker}")
    wait_for_marker(log_path, marker, baseline)


def stop_server(process: subprocess.Popen[str]) -> int:
    send(process, "save-all flush")
    time.sleep(1)
    send(process, "stop")
    try:
        return process.wait(timeout=40)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=10)


def server_error_lines(log_path: Path) -> list[str]:
    text = log_path.read_text("utf-8", errors="replace")
    return [
        line
        for line in text.splitlines()
        if "/ERROR]:" in line or "/ERROR] " in line
    ]


def run_deterministic_roll_cases(
    process: subprocess.Popen[str], log_path: Path
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    x = -18.0
    for entity_type in ("wolf", "hoglin"):
        for roll, expected in ROLL_CASES.items():
            fixture_tag = f"sc_{entity_type}_{roll}"
            summon_fixture(process, entity_type, fixture_tag, x)
            send(
                process,
                f"scoreboard players set @e[tag={fixture_tag},limit=1] {ROLL_OBJECTIVE} {roll}",
            )
            send(
                process,
                f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:growth/resolve",
            )
            # Re-run one boundary case to prove idempotence.
            if roll == 1:
                send(
                    process,
                    f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:growth/resolve",
                )
            marker = f"SUPRACRAFT_{entity_type.upper()}_ROLL_{roll}_OK"
            verify_entity(process, log_path, fixture_tag, expected, marker)
            observations.append(
                {
                    "entity_type": entity_type,
                    "roll": roll,
                    "expected_traits": sorted(expected),
                    "result": "qualified",
                }
            )
            x += 2.0
    return observations


def run_direct_trait_cases(
    process: subprocess.Popen[str], log_path: Path
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    x = 10.0
    for entity_type in ("wolf", "hoglin"):
        for trait in ("large", "swift", "fierce"):
            fixture_tag = f"sc_direct_{entity_type}_{trait}"
            summon_fixture(process, entity_type, fixture_tag, x)
            send(
                process,
                f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:apply/{trait}",
            )
            # Explicit second application: same function must remain safe/idempotent.
            send(
                process,
                f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:apply/{trait}",
            )
            marker = f"SUPRACRAFT_DIRECT_{entity_type.upper()}_{trait.upper()}_OK"
            verify_entity(process, log_path, fixture_tag, {trait}, marker)
            observations.append(
                {
                    "entity_type": entity_type,
                    "trait": trait,
                    "result": "qualified",
                }
            )
            x += 2.0
    return observations


def run_random_case(
    process: subprocess.Popen[str], log_path: Path
) -> dict[str, Any]:
    fixture_tag = "sc_random_wolf"
    summon_fixture(process, "wolf", fixture_tag, 30.0)
    send(
        process,
        f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:growth/cast",
    )

    candidates = [
        (
            "large",
            f"execute as @e[tag={fixture_tag},limit=1] "
            f"if score @s {ROLL_OBJECTIVE} matches 1..80 "
            "if entity @s[tag=supracraft.large] "
            "unless entity @s[tag=supracraft.fierce] "
            "unless entity @s[tag=supracraft.swift]",
        ),
        (
            "large+fierce",
            f"execute as @e[tag={fixture_tag},limit=1] "
            f"if score @s {ROLL_OBJECTIVE} matches 81..95 "
            "if entity @s[tag=supracraft.large] "
            "if entity @s[tag=supracraft.fierce] "
            "unless entity @s[tag=supracraft.swift]",
        ),
        (
            "large+swift",
            f"execute as @e[tag={fixture_tag},limit=1] "
            f"if score @s {ROLL_OBJECTIVE} matches 96..100 "
            "if entity @s[tag=supracraft.large] "
            "if entity @s[tag=supracraft.swift] "
            "unless entity @s[tag=supracraft.fierce]",
        ),
    ]

    baseline = marker_count(log_path, "SUPRACRAFT_RANDOM_")
    for phenotype, predicate in candidates:
        send(
            process,
            f"{predicate} run say SUPRACRAFT_RANDOM_{phenotype.upper().replace('+', '_')}_OK",
        )

    deadline = time.monotonic() + 8.0
    phenotype = None
    while time.monotonic() < deadline:
        text = log_path.read_text("utf-8", errors="replace")
        for name, _ in candidates:
            marker = f"SUPRACRAFT_RANDOM_{name.upper().replace('+', '_')}_OK"
            if marker in text:
                phenotype = name
                break
        if phenotype:
            break
        time.sleep(0.1)

    if phenotype is None:
        tail = log_path.read_text("utf-8", errors="replace")[-5000:]
        raise RuntimeError(f"random Growth landed outside admitted set; tail={tail!r}")

    after = marker_count(log_path, "SUPRACRAFT_RANDOM_")
    if after - baseline != 1:
        raise RuntimeError(
            f"random Growth produced ambiguous admitted markers: before={baseline}, after={after}"
        )

    expected = {
        "large": {"large"},
        "large+fierce": {"large", "fierce"},
        "large+swift": {"large", "swift"},
    }[phenotype]
    verify_entity(
        process,
        log_path,
        fixture_tag,
        expected,
        "SUPRACRAFT_RANDOM_ATTRIBUTES_OK",
    )
    return {"entity_type": "wolf", "phenotype": phenotype, "result": "qualified"}


def run_inheritance_cases(
    process: subprocess.Popen[str], log_path: Path
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    cases = [
        ("wolf", {"large", "fierce"}, 36.0),
        ("hoglin", {"large", "swift"}, 42.0),
    ]
    for entity_type, traits, x in cases:
        source_tag = f"sc_source_{entity_type}"
        child_tag = f"sc_child_{entity_type}"
        summon_fixture(process, entity_type, source_tag, x)
        summon_fixture(process, entity_type, child_tag, x + 1.0)
        for trait in sorted(traits):
            send(
                process,
                f"execute as @e[tag={source_tag},limit=1] run function supracraft_traits:apply/{trait}",
            )
        send(
            process,
            f"tag @e[tag={source_tag},limit=1] add supracraft.inherit_source",
        )
        send(
            process,
            f"execute as @e[tag={child_tag},limit=1] run function supracraft_traits:inherit/from_marked_source",
        )
        marker = f"SUPRACRAFT_INHERIT_{entity_type.upper()}_OK"
        verify_entity(process, log_path, child_tag, traits, marker)
        send(
            process,
            f"tag @e[tag={source_tag},limit=1] remove supracraft.inherit_source",
        )
        observations.append(
            {
                "entity_type": entity_type,
                "source_traits": sorted(traits),
                "child_traits": sorted(traits),
                "binding": "explicit_marked_source",
                "result": "qualified",
            }
        )
    return observations


def prepare_persistence_cases(
    process: subprocess.Popen[str], log_path: Path
) -> list[dict[str, Any]]:
    cases = [
        ("wolf", "sc_persist_wolf", {"large", "fierce"}, 50.0),
        ("hoglin", "sc_persist_hoglin", {"large", "swift"}, 54.0),
    ]
    observations: list[dict[str, Any]] = []
    for entity_type, fixture_tag, traits, x in cases:
        summon_fixture(process, entity_type, fixture_tag, x)
        for trait in sorted(traits):
            send(
                process,
                f"execute as @e[tag={fixture_tag},limit=1] run function supracraft_traits:apply/{trait}",
            )
        verify_entity(
            process,
            log_path,
            fixture_tag,
            traits,
            f"SUPRACRAFT_PRE_RESTART_{entity_type.upper()}_OK",
        )
        observations.append(
            {
                "entity_type": entity_type,
                "fixture_tag": fixture_tag,
                "traits": sorted(traits),
            }
        )
    return observations


def verify_persistence_cases(
    process: subprocess.Popen[str],
    log_path: Path,
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    observed: list[dict[str, Any]] = []
    for case in cases:
        traits = set(case["traits"])
        entity_type = str(case["entity_type"])
        verify_entity(
            process,
            log_path,
            str(case["fixture_tag"]),
            traits,
            f"SUPRACRAFT_POST_RESTART_{entity_type.upper()}_OK",
        )
        observed.append(
            {
                "entity_type": entity_type,
                "traits": sorted(traits),
                "result": "qualified",
            }
        )
    return observed


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

    with tempfile.TemporaryDirectory(prefix="mob-traits-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)
        datapack = write_datapack(root)

        first_log = root / "server-first.log"
        with first_log.open("w", encoding="utf-8") as log:
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
                send(server, "forceload add 0 0")
                send(server, "function supracraft_traits:setup")
                time.sleep(0.5)

                direct = run_direct_trait_cases(server, first_log)
                rolls = run_deterministic_roll_cases(server, first_log)
                random_case = run_random_case(server, first_log)
                inheritance = run_inheritance_cases(server, first_log)
                persistence_cases = prepare_persistence_cases(server, first_log)
                first_rc = stop_server(server)
            finally:
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

        if first_rc != 0:
            raise RuntimeError(f"first server exit code {first_rc}")
        first_errors = server_error_lines(first_log)
        if first_errors:
            raise RuntimeError(
                "first server emitted ERROR lines: "
                + " | ".join(first_errors[-20:])
            )

        restart_log = root / "server-restart.log"
        with restart_log.open("w", encoding="utf-8") as log:
            restarted = subprocess.Popen(
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
                restart_status = wait_server(restarted, protocol)
                post_restart = verify_persistence_cases(
                    restarted, restart_log, persistence_cases
                )
                restart_rc = stop_server(restarted)
            finally:
                if restarted.poll() is None:
                    try:
                        send(restarted, "stop")
                        restarted.wait(timeout=20)
                    except Exception:
                        restarted.kill()
                        restarted.wait(timeout=10)

        if restart_rc != 0:
            raise RuntimeError(f"restart server exit code {restart_rc}")
        restart_errors = server_error_lines(restart_log)
        if restart_errors:
            raise RuntimeError(
                "restart server emitted ERROR lines: "
                + " | ".join(restart_errors[-20:])
            )

        result = {
            "schema": "supracraft.vanilla-mob-traits/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": protocol,
                "world_version": int(info["world_version"]),
                "data_pack_version": [121, 0],
                "server_sha1": evidence["server_artifact"]["actual_sha1"],
                "server_sha256": evidence["server_artifact"]["sha256"],
            },
            "datapack": datapack,
            "oracle": "official_vanilla_server_commands_and_log",
            "direct_trait_cases": direct,
            "deterministic_growth_cases": rolls,
            "random_growth_case": random_case,
            "inheritance_resolver_cases": inheritance,
            "restart_cases": post_restart,
            "status_protocols": {
                "first": int(status.get("version", {}).get("protocol", -1)),
                "restart": int(
                    restart_status.get("version", {}).get("protocol", -1)
                ),
            },
            "server_error_log_count": len(first_errors) + len(restart_errors),
            "result": "qualified",
            "limitations": [
                "qualifies only the exact Java 26.3 trait functions and bounded fixtures",
                "does not claim natural parent-child reproduction event binding",
                "does not claim tamed-wolf attribute retention across taming transitions",
                "does not add replacement AI or new entity types",
                "does not qualify passive hostile mobs or heritable crop state",
                "random qualification proves admitted-set membership, not distribution quality",
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
