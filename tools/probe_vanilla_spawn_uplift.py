#!/usr/bin/env python3
"""Probe exact vanilla 26.2 -> 26.3 mob-spawn data migration.

Downloads official Mojang version metadata and server jars, verifies SHA-1,
extracts selected vanilla structure definitions from the nested server jar,
and emits a derived migration receipt only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

DEFAULT_STRUCTURES = [
    "minecraft:fortress",
    "minecraft:pillager_outpost",
    "minecraft:swamp_hut",
]


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as response:
        return response.read()


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def version_metadata(version: str) -> dict[str, Any]:
    manifest = fetch_json(MANIFEST)
    entry = next((x for x in manifest["versions"] if x["id"] == version), None)
    if entry is None:
        raise RuntimeError(f"version {version!r} not present in Mojang manifest")
    return fetch_json(entry["url"])


def extract_nested_server_file(server_bytes: bytes, relative_path: str) -> bytes:
    """Find file either directly or inside the bundler's nested server jar."""
    with zipfile.ZipFile(io.BytesIO(server_bytes)) as outer:
        names = set(outer.namelist())
        if relative_path in names:
            return outer.read(relative_path)

        nested = [
            n for n in outer.namelist()
            if n.startswith("META-INF/versions/") and n.endswith(".jar")
        ]
        if not nested:
            # Fallback for packaging changes: inspect any nested jar.
            nested = [n for n in outer.namelist() if n.endswith(".jar")]

        for nested_name in nested:
            try:
                payload = outer.read(nested_name)
                with zipfile.ZipFile(io.BytesIO(payload)) as inner:
                    if relative_path in inner.namelist():
                        return inner.read(relative_path)
            except zipfile.BadZipFile:
                continue

    raise FileNotFoundError(relative_path)


def structure_path(structure_id: str) -> str:
    namespace, name = structure_id.split(":", 1)
    return f"data/{namespace}/worldgen/structure/{name}.json"


def normalized_count_from_legacy(min_count: int, max_count: int) -> Any:
    if min_count == max_count:
        return min_count
    return {
        "type": "minecraft:uniform",
        "min_inclusive": min_count,
        "max_inclusive": max_count,
    }


def spawn_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    overrides = data.get("spawn_overrides", {})
    if not isinstance(overrides, dict):
        return out
    for category, spec in sorted(overrides.items()):
        if not isinstance(spec, dict):
            continue
        bbox = spec.get("bounding_box")
        for entry in spec.get("spawns", []) or []:
            if not isinstance(entry, dict):
                continue
            row = {
                "category": category,
                "bounding_box": bbox,
                "entity_type": entry.get("type"),
                "weight": entry.get("weight"),
            }
            if "minCount" in entry or "maxCount" in entry:
                row["minCount"] = entry.get("minCount")
                row["maxCount"] = entry.get("maxCount")
            if "count" in entry:
                row["count"] = entry.get("count")
            out.append(row)
    return out


def key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("category")), str(row.get("entity_type")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="26.2")
    ap.add_argument("--new", default="26.3")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--structures", nargs="*", default=DEFAULT_STRUCTURES)
    args = ap.parse_args()

    versions: dict[str, dict[str, Any]] = {}
    server_payloads: dict[str, bytes] = {}

    for version in (args.old, args.new):
        meta = version_metadata(version)
        server = meta["downloads"]["server"]
        payload = fetch_bytes(server["url"])
        actual_sha1 = sha1(payload)
        if actual_sha1 != server["sha1"]:
            raise RuntimeError(
                f"{version} server SHA-1 mismatch: {actual_sha1} != {server['sha1']}"
            )
        versions[version] = {
            "id": meta["id"],
            "data_version": meta.get("world_version"),
            "protocol_version": meta.get("protocol_version"),
            "server_sha1": server["sha1"],
            "server_size": server["size"],
            "server_url_host": urllib.request.urlparse(server["url"]).hostname
            if hasattr(urllib.request, "urlparse") else "piston-data.mojang.com",
        }
        server_payloads[version] = payload

    comparisons: list[dict[str, Any]] = []
    exact_mapping_matches = 0
    mapping_mismatches = 0
    ranged_examples = 0

    for structure_id in args.structures:
        path = structure_path(structure_id)
        old_data = json.loads(
            extract_nested_server_file(server_payloads[args.old], path).decode("utf-8")
        )
        new_data = json.loads(
            extract_nested_server_file(server_payloads[args.new], path).decode("utf-8")
        )
        old_rows = {key(r): r for r in spawn_rows(old_data)}
        new_rows = {key(r): r for r in spawn_rows(new_data)}
        common = sorted(set(old_rows) & set(new_rows))

        rows = []
        for k in common:
            old_row = old_rows[k]
            new_row = new_rows[k]
            if "minCount" not in old_row or "maxCount" not in old_row or "count" not in new_row:
                continue
            expected = normalized_count_from_legacy(
                int(old_row["minCount"]), int(old_row["maxCount"])
            )
            actual = new_row["count"]
            match = expected == actual
            if old_row["minCount"] != old_row["maxCount"]:
                ranged_examples += 1
            exact_mapping_matches += int(match)
            mapping_mismatches += int(not match)
            rows.append({
                "category": k[0],
                "entity_type": k[1],
                "old_min": old_row["minCount"],
                "old_max": old_row["maxCount"],
                "expected_26_3_count": expected,
                "actual_26_3_count": actual,
                "count_mapping_matches": match,
                "old_bounding_box": old_row.get("bounding_box"),
                "new_bounding_box": new_row.get("bounding_box"),
                "bounding_box_unchanged": (
                    old_row.get("bounding_box") == new_row.get("bounding_box")
                ),
                "old_weight": old_row.get("weight"),
                "new_weight": new_row.get("weight"),
            })

        comparisons.append({
            "structure": structure_id,
            "path": path,
            "rows": rows,
        })

    result = {
        "schema": "supracraft-vanilla-spawn-uplift-oracle/1",
        "source": "official Mojang version manifest + official server artifacts",
        "old_version": versions[args.old],
        "new_version": versions[args.new],
        "structures": comparisons,
        "summary": {
            "mapping_rows": exact_mapping_matches + mapping_mismatches,
            "exact_count_mapping_matches": exact_mapping_matches,
            "count_mapping_mismatches": mapping_mismatches,
            "ranged_legacy_examples": ranged_examples,
            "expected_mapping": "min==max -> constant; min!=max -> minecraft:uniform int provider",
        },
        "classification": (
            "VANILLA_COUNT_MAPPING_CONFIRMED"
            if exact_mapping_matches > 0 and mapping_mismatches == 0 and ranged_examples > 0
            else "MAPPING_REQUIRES_REVIEW"
        ),
        "boundary": (
            "This validates the serialized count migration on selected vanilla structure "
            "spawn rows; it does not prove third-party intentional content changes are mistakes."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(result["classification"])

    if result["classification"] != "VANILLA_COUNT_MAPPING_CONFIRMED":
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
