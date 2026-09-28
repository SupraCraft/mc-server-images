#!/usr/bin/env python3
"""Derive a public-safe Minecraft Java 26.3 block catalog qualification summary.

Authoritative legality/state IDs come from Mojang's server data generator.
Client blockstate/model JSON is inspected only in-memory to measure visual
coverage. Mojang assets are not retained in the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_verified(meta: dict[str, Any]) -> bytes:
    with urllib.request.urlopen(str(meta["url"]), timeout=300) as response:
        data = response.read()
    if sha1(data) != meta["actual_sha1"]:
        raise RuntimeError("artifact SHA-1 mismatch against qualified evidence")
    if sha256(data) != meta["sha256"]:
        raise RuntimeError("artifact SHA-256 mismatch against qualified evidence")
    if len(data) != int(meta["size"]):
        raise RuntimeError("artifact size mismatch against qualified evidence")
    return data


def find_report(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one generated {name}, found {len(matches)}: {matches}"
        )
    return matches[0]


def model_refs(blockstate: Any) -> set[str]:
    refs: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            model = value.get("model")
            if isinstance(model, str):
                refs.add(model)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(blockstate)
    return refs


def normalized_model_path(model: str) -> str | None:
    if ":" in model:
        namespace, name = model.split(":", 1)
    else:
        namespace, name = "minecraft", model
    if namespace != "minecraft":
        return None
    return f"assets/minecraft/models/{name}.json"



def exact_state_id(
    blocks: dict[str, Any],
    block_id: str,
    properties: dict[str, str],
) -> int:
    record = blocks.get(block_id)
    if not isinstance(record, dict):
        raise RuntimeError(f"missing fixture block {block_id}")
    matches = []
    for state in record.get("states", []):
        if not isinstance(state, dict):
            continue
        state_properties = state.get("properties", {})
        if state_properties is None:
            state_properties = {}
        if state_properties == properties:
            matches.append(int(state["id"]))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected exactly one legal state for {block_id}{properties}, "
            f"found {matches}"
        )
    return matches[0]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info.get("id") != "26.3":
        raise RuntimeError("probe requires qualified Minecraft 26.3 evidence")

    server = fetch_verified(evidence["server_artifact"])
    client = fetch_verified(evidence["client_artifact"])

    with tempfile.TemporaryDirectory(prefix="mc-26.3-catalog-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        server_jar.write_bytes(server)
        generated = root / "generated"

        command = [
            "java",
            "-DbundlerMainClass=net.minecraft.data.Main",
            "-jar",
            str(server_jar),
            "--reports",
            "--output",
            str(generated),
        ]
        run = subprocess.run(
            command,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout_seconds,
            check=False,
        )
        if run.returncode != 0:
            raise RuntimeError(
                "Mojang data generator failed: " + (run.stdout or "")[-6000:]
            )

        blocks_path = find_report(generated, "blocks.json")
        registries_path = find_report(generated, "registries.json")
        blocks_bytes = blocks_path.read_bytes()
        registries_bytes = registries_path.read_bytes()
        blocks = json.loads(blocks_bytes)
        registries = json.loads(registries_bytes)

        if not isinstance(blocks, dict) or not blocks:
            raise RuntimeError("generated blocks.json is not a non-empty object")

        state_count = 0
        state_ids: list[int] = []
        property_names: set[str] = set()
        property_value_counts: Counter[str] = Counter()
        stateful_blocks: list[tuple[str, int]] = []

        for block_id, record in blocks.items():
            if not isinstance(record, dict):
                raise RuntimeError(f"invalid block record for {block_id}")
            states = record.get("states", [])
            if not isinstance(states, list) or not states:
                raise RuntimeError(f"block {block_id} has no generated states")
            state_count += len(states)
            if len(states) > 1:
                stateful_blocks.append((block_id, len(states)))
            for state in states:
                if "id" in state:
                    state_ids.append(int(state["id"]))
            props = record.get("properties", {})
            if isinstance(props, dict):
                for prop, values in props.items():
                    property_names.add(prop)
                    if isinstance(values, list):
                        property_value_counts[prop] = max(
                            property_value_counts[prop], len(values)
                        )

        with zipfile.ZipFile(io.BytesIO(client)) as jar:
            names = set(jar.namelist())
            blockstate_paths = {
                name
                for name in names
                if name.startswith("assets/minecraft/blockstates/")
                and name.endswith(".json")
            }
            block_model_paths = {
                name
                for name in names
                if name.startswith("assets/minecraft/models/block/")
                and name.endswith(".json")
            }
            block_texture_paths = {
                name
                for name in names
                if name.startswith("assets/minecraft/textures/block/")
                and name.endswith(".png")
            }

            missing_blockstates: list[str] = []
            parse_failures: list[str] = []
            all_model_refs: set[str] = set()
            blocks_with_multipart = 0
            blocks_with_variants = 0

            for block_id in sorted(blocks):
                if ":" in block_id:
                    namespace, name = block_id.split(":", 1)
                else:
                    namespace, name = "minecraft", block_id
                if namespace != "minecraft":
                    continue
                path = f"assets/minecraft/blockstates/{name}.json"
                if path not in names:
                    missing_blockstates.append(block_id)
                    continue
                try:
                    data = json.loads(jar.read(path))
                except Exception:
                    parse_failures.append(block_id)
                    continue
                if isinstance(data, dict):
                    if "multipart" in data:
                        blocks_with_multipart += 1
                    if "variants" in data:
                        blocks_with_variants += 1
                all_model_refs.update(model_refs(data))

        missing_referenced_models: list[str] = []
        external_model_refs: list[str] = []
        for model in sorted(all_model_refs):
            path = normalized_model_path(model)
            if path is None:
                external_model_refs.append(model)
            elif path not in block_model_paths:
                missing_referenced_models.append(model)

        block_registry = registries.get("minecraft:block")
        registry_entry_count = None
        if isinstance(block_registry, dict):
            entries = block_registry.get("entries")
            if isinstance(entries, dict):
                registry_entry_count = len(entries)

        top_stateful = [
            {"block": block, "state_count": count}
            for block, count in sorted(
                stateful_blocks, key=lambda item: (-item[1], item[0])
            )[:25]
        ]

        contiguous_state_ids = (
            bool(state_ids)
            and len(state_ids) == len(set(state_ids))
            and min(state_ids) == 0
            and max(state_ids) + 1 == len(state_ids)
        )

        result = {
            "schema": "supracraft.minecraft-block-catalog-summary/v0.1",
            "minecraft": {
                "edition": "java",
                "version": "26.3",
                "protocol": int(info["protocol_version"]),
                "world_version": int(info["world_version"]),
                "data_pack_major": int(info["pack_version"]["data_major"]),
                "resource_pack_major": int(info["pack_version"]["resource_major"]),
            },
            "provenance": {
                "server_sha256": evidence["server_artifact"]["sha256"],
                "client_sha256": evidence["client_artifact"]["sha256"],
                "blocks_report_sha256": sha256(blocks_bytes),
                "registries_report_sha256": sha256(registries_bytes),
                "generator": (
                    "java -DbundlerMainClass=net.minecraft.data.Main "
                    "-jar server.jar --reports"
                ),
            },
            "fixture_state_checks": [
                {
                    "block": "minecraft:chest",
                    "properties": {
                        "facing": "south",
                        "type": "single",
                        "waterlogged": "false",
                    },
                    "state_id": exact_state_id(
                        blocks,
                        "minecraft:chest",
                        {
                            "facing": "south",
                            "type": "single",
                            "waterlogged": "false",
                        },
                    ),
                },
                {
                    "block": "minecraft:redstone_lamp",
                    "properties": {"lit": "false"},
                    "state_id": exact_state_id(
                        blocks,
                        "minecraft:redstone_lamp",
                        {"lit": "false"},
                    ),
                },
                {
                    "block": "minecraft:lantern",
                    "properties": {
                        "hanging": "false",
                        "waterlogged": "false",
                    },
                    "state_id": exact_state_id(
                        blocks,
                        "minecraft:lantern",
                        {
                            "hanging": "false",
                            "waterlogged": "false",
                        },
                    ),
                },
            ],
            "runtime_catalog": {
                "blocks": len(blocks),
                "states": state_count,
                "state_ids_observed": len(state_ids),
                "state_ids_contiguous_from_zero": contiguous_state_ids,
                "blocks_with_multiple_states": len(stateful_blocks),
                "unique_property_names": sorted(property_names),
                "property_max_value_count": dict(
                    sorted(property_value_counts.items())
                ),
                "top_stateful_blocks": top_stateful,
                "block_registry_entries": registry_entry_count,
            },
            "client_visual_coverage": {
                "blockstate_json_files": len(blockstate_paths),
                "block_model_json_files": len(block_model_paths),
                "block_texture_png_files": len(block_texture_paths),
                "runtime_blocks_without_matching_blockstate_json": (
                    missing_blockstates
                ),
                "blockstate_parse_failures": parse_failures,
                "blocks_using_variants": blocks_with_variants,
                "blocks_using_multipart": blocks_with_multipart,
                "unique_referenced_models": len(all_model_refs),
                "referenced_models_missing_from_client_jar": (
                    missing_referenced_models
                ),
                "non_minecraft_namespace_model_refs": external_model_refs,
            },
            "retention_policy": {
                "mojang_asset_payloads_retained": False,
                "derived_summary_only": True,
            },
            "result": "qualified",
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
