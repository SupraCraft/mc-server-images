#!/usr/bin/env python3
"""Exact modern Minecraft microscope symbol inventory.

This consumes the same official frontier metadata as discovery, verifies the
exact dedicated-server artifact, extracts only the embedded runtime in the
ephemeral work directory, and emits factual class hashes plus method
names/descriptors. It does not redistribute the server or qualify any hook.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

import discover_minecraft_observability as discovery

SCHEMA = "supracraft-causal-symbol-inventory/1"

ROLE_SUFFIXES = {
    "server_tick_host": "net/minecraft/server/MinecraftServer.class",
    "world_state_host": "net/minecraft/world/level/Level.class",
    "server_world_host": "net/minecraft/server/level/ServerLevel.class",
    "command_block": "net/minecraft/world/level/block/CommandBlock.class",
    "command_block_entity": (
        "net/minecraft/world/level/block/entity/CommandBlockEntity.class"
    ),
    "command_dispatch": "net/minecraft/commands/Commands.class",
    "packet_listener": (
        "net/minecraft/server/network/ServerGamePacketListenerImpl.class"
    ),
    "redstone_wire": "net/minecraft/world/level/block/RedstoneWireBlock.class",
}

TOKEN_HINTS = {
    "server_tick_host": ("tick",),
    "world_state_host": (
        "block", "neighbor", "signal", "power", "update", "schedule", "set"
    ),
    "server_world_host": (
        "tick", "block", "neighbor", "signal", "update", "schedule"
    ),
    "command_block": ("neighbor", "tick", "command", "execute"),
    "command_block_entity": ("command", "execute", "perform"),
    "command_dispatch": ("command", "execute", "perform"),
    "packet_listener": ("send", "packet"),
    "redstone_wire": ("neighbor", "power", "signal", "update", "strength"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_runtime_jar(server_jar: Path, target: Path) -> None:
    candidates = []
    with zipfile.ZipFile(server_jar) as outer:
        for name in outer.namelist():
            if not name.endswith(".jar"):
                continue
            try:
                data = outer.read(name)
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    names = set(nested.namelist())
                if "net/minecraft/server/MinecraftServer.class" in names:
                    candidates.append((name, data))
            except zipfile.BadZipFile:
                continue
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one embedded Minecraft runtime jar, got "
            f"{[name for name,_ in candidates]}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(candidates[0][1])


def locate_role_classes(runtime_jar: Path) -> dict[str, str]:
    with zipfile.ZipFile(runtime_jar) as zf:
        names = set(zf.namelist())
    located = {}
    for role, expected in ROLE_SUFFIXES.items():
        matches = sorted(name for name in names if name.endswith(expected))
        if len(matches) != 1:
            raise RuntimeError(
                f"{role}: expected one exact class {expected}, got {matches}"
            )
        located[role] = matches[0][:-6].replace("/", ".")
    return located


def class_bytes(runtime_jar: Path, class_name: str) -> bytes:
    path = class_name.replace(".", "/") + ".class"
    with zipfile.ZipFile(runtime_jar) as zf:
        return zf.read(path)


def javap_methods(runtime_jar: Path, class_name: str) -> list[dict]:
    javap = discovery.java_executable("javap")
    proc = subprocess.run(
        [
            javap,
            "-p",
            "-s",
            "-classpath",
            str(runtime_jar.resolve()),
            class_name,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=90,
        check=True,
    )
    methods = []
    pending = None
    simple = class_name.rsplit(".", 1)[-1]
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if line.startswith("descriptor:"):
            if not pending:
                raise RuntimeError(
                    f"{class_name}: descriptor without declaration: {line}"
                )
            descriptor = line.split(":", 1)[1].strip()
            before = pending.split("(", 1)[0].strip()
            token = before.split()[-1]
            if token == simple:
                name = "<init>"
            elif token.endswith(simple):
                name = "<init>"
            else:
                name = token
            methods.append(
                {
                    "name": name,
                    "descriptor": descriptor,
                    "declaration_sha256": sha256_bytes(
                        pending.encode("utf-8")
                    ),
                }
            )
            pending = None
        elif "(" in line and (
            line.endswith(";")
            or line.endswith(")")
            or line.endswith(" throws")
        ):
            pending = line
        elif line.startswith("static {}"):
            pending = None
    return sorted(methods, key=lambda row: (row["name"], row["descriptor"]))


def candidate_methods(role: str, methods: list[dict]) -> list[dict]:
    tokens = TOKEN_HINTS[role]
    return [
        row
        for row in methods
        if any(token in row["name"].lower() for token in tokens)
    ]


def inventory_command(args: argparse.Namespace) -> None:
    manifest = discovery.fetch_json(args.manifest_url)
    rows = discovery.resolve_frontier(manifest)
    row = next(r for r in rows if r["channel"] == args.channel)
    if row["minecraft_version"] != args.expected_version:
        raise RuntimeError(
            f"frontier changed: expected {args.expected_version}, "
            f"observed {row['minecraft_version']}"
        )
    if row["java_major"] != args.expected_java:
        raise RuntimeError(
            f"Java requirement changed: expected {args.expected_java}, "
            f"observed {row['java_major']}"
        )

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    server_jar = work / "server.jar"
    discovery.download_verified(row, server_jar)
    runtime_jar = work / "embedded-runtime.jar"
    extract_runtime_jar(server_jar, runtime_jar)
    roles = locate_role_classes(runtime_jar)

    entries = []
    for role, class_name in sorted(roles.items()):
        methods = javap_methods(runtime_jar, class_name)
        if not methods:
            raise RuntimeError(f"{role}: no methods discovered for {class_name}")
        entries.append(
            {
                "role": role,
                "runtime_class": class_name,
                "class_sha256": sha256_bytes(
                    class_bytes(runtime_jar, class_name)
                ),
                "method_count": len(methods),
                "methods": methods,
                "name_token_candidates": candidate_methods(role, methods),
            }
        )

    receipt = {
        "schema": SCHEMA,
        "channel": row["channel"],
        "minecraft_version": row["minecraft_version"],
        "java_major": row["java_major"],
        "symbol_mode_required": "unobfuscated",
        "server_sha1": row["server_sha1"],
        "classes": entries,
        "qualification_status": "inventory_only_not_hook_qualified",
        "boundaries": [
            "class and method names are discovery evidence, not hook semantics",
            "name-token candidates are search aids only",
            "hook qualification requires exact behavior review and observer A/B",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "minecraft_version": row["minecraft_version"],
                "channel": row["channel"],
                "classes": [
                    {
                        "role": item["role"],
                        "runtime_class": item["runtime_class"],
                        "method_count": item["method_count"],
                        "name_token_candidate_count": len(
                            item["name_token_candidates"]
                        ),
                    }
                    for item in entries
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def compare_command(args: argparse.Namespace) -> None:
    root = Path(args.root)
    docs = []
    for path in root.rglob("symbol-inventory.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema") == SCHEMA:
            docs.append(doc)
    by_channel = {doc["channel"]: doc for doc in docs}
    if set(by_channel) != {"release", "snapshot"}:
        raise RuntimeError(
            f"expected release+snapshot inventories, got {sorted(by_channel)}"
        )

    def class_map(doc):
        return {row["role"]: row for row in doc["classes"]}

    release = class_map(by_channel["release"])
    snapshot = class_map(by_channel["snapshot"])
    if set(release) != set(snapshot):
        raise RuntimeError("role set differs across frontier")

    roles = {}
    for role in sorted(release):
        r = release[role]
        s = snapshot[role]
        r_methods = {(x["name"], x["descriptor"]) for x in r["methods"]}
        s_methods = {(x["name"], x["descriptor"]) for x in s["methods"]}
        common = sorted(r_methods & s_methods)
        roles[role] = {
            "release_class": r["runtime_class"],
            "snapshot_class": s["runtime_class"],
            "same_runtime_class": r["runtime_class"] == s["runtime_class"],
            "same_class_bytes": r["class_sha256"] == s["class_sha256"],
            "common_method_count": len(common),
            "release_only_method_count": len(r_methods - s_methods),
            "snapshot_only_method_count": len(s_methods - r_methods),
            "common_methods": [
                {"name": name, "descriptor": descriptor}
                for name, descriptor in common
            ],
        }

    summary = {
        "schema": "supracraft-causal-symbol-frontier-comparison/1",
        "release": by_channel["release"]["minecraft_version"],
        "snapshot": by_channel["snapshot"]["minecraft_version"],
        "roles": roles,
        "boundary": (
            "common signatures are compatibility evidence only; "
            "they are not qualified causal hook bindings"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "release": summary["release"],
                "snapshot": summary["snapshot"],
                "roles": {
                    role: {
                        "same_runtime_class": row["same_runtime_class"],
                        "same_class_bytes": row["same_class_bytes"],
                        "common_method_count": row["common_method_count"],
                        "release_only_method_count": row[
                            "release_only_method_count"
                        ],
                        "snapshot_only_method_count": row[
                            "snapshot_only_method_count"
                        ],
                    }
                    for role, row in roles.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--manifest-url",
        default=discovery.VERSION_MANIFEST_URL,
    )
    sub = p.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory")
    inv.add_argument("--channel", choices=("release", "snapshot"), required=True)
    inv.add_argument("--expected-version", required=True)
    inv.add_argument("--expected-java", type=int, required=True)
    inv.add_argument("--work-dir", required=True)
    inv.add_argument("--output", required=True)
    inv.set_defaults(func=inventory_command)

    compare = sub.add_parser("compare")
    compare.add_argument("--root", required=True)
    compare.add_argument("--output", required=True)
    compare.set_defaults(func=compare_command)
    return p


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
