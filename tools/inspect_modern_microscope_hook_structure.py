#!/usr/bin/env python3
"""Exact method-structure evidence for modern causal-microscope hook candidates.

This emits normalized method-body fingerprints and bounded symbolic references
from the exact official Minecraft runtime. It does not emit Mojang class bytes,
full disassembly, or qualify a hook merely because a method name matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import discover_minecraft_observability as discovery
import inventory_modern_microscope_symbols as inventory

SCHEMA = "supracraft-causal-hook-structure/1"

TARGETS = (
    {
        "id": "server_tick",
        "event_family": "tick_boundary",
        "role": "server_tick_host",
        "name": "tickServer",
        "descriptor": "(Ljava/util/function/BooleanSupplier;)V",
    },
    {
        "id": "block_state_write",
        "event_family": "block_state_write",
        "role": "world_state_host",
        "name": "setBlock",
        "descriptor": (
            "(Lnet/minecraft/core/BlockPos;"
            "Lnet/minecraft/world/level/block/state/BlockState;II)Z"
        ),
    },
    {
        "id": "command_block_neighbor",
        "event_family": "command_block_neighbor",
        "role": "command_block",
        "name": "neighborChanged",
        "descriptor": (
            "(Lnet/minecraft/world/level/block/state/BlockState;"
            "Lnet/minecraft/world/level/Level;"
            "Lnet/minecraft/core/BlockPos;"
            "Lnet/minecraft/world/level/block/Block;"
            "Lnet/minecraft/world/level/redstone/Orientation;Z)V"
        ),
    },
    {
        "id": "command_block_tick",
        "event_family": "command_block_scheduled_tick",
        "role": "command_block",
        "name": "tick",
        "descriptor": (
            "(Lnet/minecraft/world/level/block/state/BlockState;"
            "Lnet/minecraft/server/level/ServerLevel;"
            "Lnet/minecraft/core/BlockPos;"
            "Lnet/minecraft/util/RandomSource;)V"
        ),
    },
    {
        "id": "command_block_execute",
        "event_family": "command_trigger",
        "role": "command_block",
        "name": "execute",
        "descriptor": (
            "(Lnet/minecraft/world/level/block/state/BlockState;"
            "Lnet/minecraft/server/level/ServerLevel;"
            "Lnet/minecraft/core/BlockPos;"
            "Lnet/minecraft/world/level/BaseCommandBlock;Z)V"
        ),
    },
    {
        "id": "command_dispatch",
        "event_family": "command_execute",
        "role": "command_dispatch",
        "name": "performCommand",
        "descriptor": (
            "(Lcom/mojang/brigadier/ParseResults;Ljava/lang/String;)V"
        ),
    },
    {
        "id": "command_dispatch_prefixed",
        "event_family": "command_execute",
        "role": "command_dispatch",
        "name": "performPrefixedCommand",
        "descriptor": (
            "(Lnet/minecraft/commands/CommandSourceStack;"
            "Ljava/lang/String;)V"
        ),
    },
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def javap_code(runtime_jar: Path, class_name: str) -> str:
    javap = discovery.java_executable("javap")
    return subprocess.run(
        [
            javap,
            "-p",
            "-c",
            "-s",
            "-classpath",
            str(runtime_jar.resolve()),
            class_name,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
        check=True,
    ).stdout


def _method_name(declaration: str, class_name: str) -> str:
    simple = class_name.rsplit(".", 1)[-1]
    before = declaration.split("(", 1)[0].strip()
    token = before.split()[-1]
    if token == simple or token == class_name:
        return "<init>"
    return token


def parse_javap_sections(output: str, class_name: str) -> dict[tuple[str, str], list[str]]:
    lines = output.splitlines()
    descriptor_rows = []
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line.startswith("descriptor:"):
            continue
        declaration = lines[index - 1].strip() if index else ""
        if "(" not in declaration:
            continue
        descriptor = line.split(":", 1)[1].strip()
        descriptor_rows.append(
            (index, _method_name(declaration, class_name), descriptor)
        )

    sections: dict[tuple[str, str], list[str]] = {}
    for offset, (index, name, descriptor) in enumerate(descriptor_rows):
        next_index = (
            descriptor_rows[offset + 1][0] - 1
            if offset + 1 < len(descriptor_rows)
            else len(lines)
        )
        section = lines[index + 1 : next_index]
        key = (name, descriptor)
        if key in sections:
            raise RuntimeError(
                f"{class_name}: duplicate exact method section {name}{descriptor}"
            )
        sections[key] = section
    return sections


def normalize_method_section(lines: list[str]) -> tuple[str, int]:
    normalized = []
    instruction_count = 0
    in_code = False
    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        if text == "Code:":
            in_code = True
            normalized.append("Code:")
            continue
        if in_code and re.match(r"^\d+:", text):
            instruction_count += 1
            text = re.sub(r"^\d+:\s*", "", text)
        text = re.sub(r"#\d+", "#", text)
        text = re.sub(r"\s+", " ", text)
        normalized.append(text)
    return "\n".join(normalized), instruction_count


def symbolic_references(lines: list[str], class_name: str) -> dict[str, list[str]]:
    owner = class_name.replace(".", "/")
    methods = set()
    fields = set()
    classes = set()
    for raw in lines:
        if "//" not in raw:
            continue
        comment = raw.split("//", 1)[1].strip()
        for prefix in ("InterfaceMethod ", "Method "):
            if comment.startswith(prefix):
                ref = comment[len(prefix):].strip()
                if "." not in ref.split(":", 1)[0]:
                    ref = owner + "." + ref
                methods.add(ref)
        if comment.startswith("Field "):
            ref = comment[len("Field "):].strip()
            if "." not in ref.split(":", 1)[0]:
                ref = owner + "." + ref
            fields.add(ref)
        if comment.startswith("class "):
            classes.add(comment[len("class "):].strip())
    return {
        "method_refs": sorted(methods),
        "field_refs": sorted(fields),
        "class_refs": sorted(classes),
    }


def inspect_command(args: argparse.Namespace) -> None:
    manifest = discovery.fetch_json(args.manifest_url)
    rows = discovery.resolve_frontier(manifest)
    row = next(item for item in rows if item["channel"] == args.channel)
    if row["minecraft_version"] != args.expected_version:
        raise RuntimeError(
            f"frontier changed expected={args.expected_version} "
            f"observed={row['minecraft_version']}"
        )
    if row["java_major"] != args.expected_java:
        raise RuntimeError(
            f"Java changed expected={args.expected_java} observed={row['java_major']}"
        )

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    server_jar = work / "server.jar"
    discovery.download_verified(row, server_jar)
    runtime_jar = work / "embedded-runtime.jar"
    inventory.extract_runtime_jar(server_jar, runtime_jar)
    roles = inventory.locate_role_classes(runtime_jar)

    inventory_methods = {}
    class_hashes = {}
    for role, class_name in roles.items():
        inventory_methods[role] = {
            (m["name"], m["descriptor"])
            for m in inventory.javap_methods(runtime_jar, class_name)
        }
        class_hashes[role] = inventory.sha256_bytes(
            inventory.class_bytes(runtime_jar, class_name)
        )

    class_outputs = {}
    for target in TARGETS:
        role = target["role"]
        class_name = roles[role]
        key = (target["name"], target["descriptor"])
        if key not in inventory_methods[role]:
            raise RuntimeError(
                f"{target['id']}: exact target absent in {class_name}: {key}"
            )
        if class_name not in class_outputs:
            class_outputs[class_name] = parse_javap_sections(
                javap_code(runtime_jar, class_name),
                class_name,
            )
        sections = class_outputs[class_name]
        if key not in sections:
            raise RuntimeError(
                f"{target['id']}: javap code section absent in {class_name}: {key}"
            )

    results = []
    for target in TARGETS:
        role = target["role"]
        class_name = roles[role]
        key = (target["name"], target["descriptor"])
        section = class_outputs[class_name][key]
        normalized, instruction_count = normalize_method_section(section)
        refs = symbolic_references(section, class_name)
        if instruction_count < 1:
            raise RuntimeError(f"{target['id']}: method has no bytecode instructions")
        results.append(
            {
                "id": target["id"],
                "event_family": target["event_family"],
                "role": role,
                "runtime_class": class_name,
                "class_sha256": class_hashes[role],
                "method_name": target["name"],
                "method_descriptor": target["descriptor"],
                "normalized_code_sha256": sha256_text(normalized),
                "instruction_count": instruction_count,
                **refs,
            }
        )

    receipt = {
        "schema": SCHEMA,
        "channel": row["channel"],
        "minecraft_version": row["minecraft_version"],
        "java_major": row["java_major"],
        "server_sha1": row["server_sha1"],
        "methods": results,
        "qualification_status": "structure_only_not_hook_qualified",
        "boundaries": [
            "method name and descriptor establish identity, not causal semantics",
            "normalized bytecode fingerprint is structural evidence only",
            "symbolic references support semantic review but do not prove runtime causality",
            "observer-effect A/B is required before a direct hook is qualified",
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
                "channel": row["channel"],
                "minecraft_version": row["minecraft_version"],
                "methods": [
                    {
                        "id": item["id"],
                        "runtime_class": item["runtime_class"],
                        "method_name": item["method_name"],
                        "method_descriptor": item["method_descriptor"],
                        "normalized_code_sha256": item[
                            "normalized_code_sha256"
                        ],
                        "instruction_count": item["instruction_count"],
                        "method_ref_count": len(item["method_refs"]),
                        "field_ref_count": len(item["field_refs"]),
                    }
                    for item in results
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def compare_command(args: argparse.Namespace) -> None:
    docs = []
    for path in Path(args.root).rglob("hook-structure.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema") == SCHEMA:
            docs.append(doc)
    by_channel = {doc["channel"]: doc for doc in docs}
    if set(by_channel) != {"release", "snapshot"}:
        raise RuntimeError(
            f"expected release+snapshot structures, got {sorted(by_channel)}"
        )
    release = {row["id"]: row for row in by_channel["release"]["methods"]}
    snapshot = {row["id"]: row for row in by_channel["snapshot"]["methods"]}
    if set(release) != set(snapshot):
        raise RuntimeError("hook candidate set changed across frontier")

    methods = {}
    for method_id in sorted(release):
        r = release[method_id]
        s = snapshot[method_id]
        same_identity = (
            r["runtime_class"],
            r["method_name"],
            r["method_descriptor"],
        ) == (
            s["runtime_class"],
            s["method_name"],
            s["method_descriptor"],
        )
        if not same_identity:
            raise RuntimeError(f"{method_id}: exact method identity changed")
        methods[method_id] = {
            "runtime_class": r["runtime_class"],
            "method_name": r["method_name"],
            "method_descriptor": r["method_descriptor"],
            "same_class_bytes": r["class_sha256"] == s["class_sha256"],
            "same_normalized_code": (
                r["normalized_code_sha256"] == s["normalized_code_sha256"]
            ),
            "release_instruction_count": r["instruction_count"],
            "snapshot_instruction_count": s["instruction_count"],
            "common_method_refs": sorted(
                set(r["method_refs"]) & set(s["method_refs"])
            ),
            "release_only_method_refs": sorted(
                set(r["method_refs"]) - set(s["method_refs"])
            ),
            "snapshot_only_method_refs": sorted(
                set(s["method_refs"]) - set(r["method_refs"])
            ),
            "common_field_refs": sorted(
                set(r["field_refs"]) & set(s["field_refs"])
            ),
            "release_only_field_refs": sorted(
                set(r["field_refs"]) - set(s["field_refs"])
            ),
            "snapshot_only_field_refs": sorted(
                set(s["field_refs"]) - set(r["field_refs"])
            ),
        }

    summary = {
        "schema": "supracraft-causal-hook-frontier-comparison/1",
        "release": by_channel["release"]["minecraft_version"],
        "snapshot": by_channel["snapshot"]["minecraft_version"],
        "methods": methods,
        "boundary": (
            "shared method identity/fingerprint/references are structural evidence; "
            "runtime hook qualification still requires observer-effect A/B"
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
                "methods": {
                    key: {
                        "same_class_bytes": value["same_class_bytes"],
                        "same_normalized_code": value["same_normalized_code"],
                        "release_instruction_count": value[
                            "release_instruction_count"
                        ],
                        "snapshot_instruction_count": value[
                            "snapshot_instruction_count"
                        ],
                        "release_only_method_ref_count": len(
                            value["release_only_method_refs"]
                        ),
                        "snapshot_only_method_ref_count": len(
                            value["snapshot_only_method_refs"]
                        ),
                    }
                    for key, value in methods.items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest-url", default=discovery.VERSION_MANIFEST_URL)
    sub = p.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--channel", choices=("release", "snapshot"), required=True)
    inspect.add_argument("--expected-version", required=True)
    inspect.add_argument("--expected-java", type=int, required=True)
    inspect.add_argument("--work-dir", required=True)
    inspect.add_argument("--output", required=True)
    inspect.set_defaults(func=inspect_command)

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
