#!/usr/bin/env python3
"""Compare exact vanilla Java 26.2 and 26.3 noise-settings migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from probe_vanilla_spawn_uplift import (
    extract_nested_server_file,
    fetch_bytes,
    sha1,
    version_metadata,
)

DEFAULTS = ["overworld", "large_biomes", "nether"]


def contains_type(v: Any, wanted: str) -> bool:
    if isinstance(v, dict):
        if v.get("type") == wanted:
            return True
        return any(contains_type(x, wanted) for x in v.values())
    if isinstance(v, list):
        return any(contains_type(x, wanted) for x in v)
    return False


def block_id(state: Any) -> str | None:
    if isinstance(state, str):
        return state
    if not isinstance(state, dict):
        return None
    return state.get("id") or state.get("Name")


def load_server(version: str) -> tuple[dict[str, Any], bytes]:
    meta = version_metadata(version)
    server = meta["downloads"]["server"]
    payload = fetch_bytes(server["url"])
    actual = sha1(payload)
    if actual != server["sha1"]:
        raise RuntimeError(f"{version} SHA-1 mismatch: {actual} != {server['sha1']}")
    return meta, payload


def load_noise_settings(server: bytes, name: str) -> dict[str, Any]:
    path = f"data/minecraft/worldgen/noise_settings/{name}.json"
    return json.loads(extract_nested_server_file(server, path).decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="26.2")
    ap.add_argument("--new", default="26.3")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--settings", nargs="*", default=DEFAULTS)
    args = ap.parse_args()

    old_meta, old_server = load_server(args.old)
    new_meta, new_server = load_server(args.new)

    rows = []
    for name in args.settings:
        old = load_noise_settings(old_server, name)
        new = load_noise_settings(new_server, name)

        old_final = old.get("noise_router", {}).get("final_density")
        new_final = new.get("noise_router", {}).get("final_density")

        rows.append({
            "name": name,
            "sea_level_old": old.get("sea_level"),
            "sea_level_new": new.get("sea_level"),
            "sea_level_preserved": old.get("sea_level") == new.get("sea_level"),
            "default_block_old": block_id(old.get("default_block")),
            "default_block_new": block_id(new.get("default_block")),
            "default_block_preserved": block_id(old.get("default_block")) == block_id(new.get("default_block")),
            "old_final_density_shape": (
                old_final.get("type") if isinstance(old_final, dict) else type(old_final).__name__
            ),
            "new_final_density_shape": (
                new_final.get("type") if isinstance(new_final, dict) else type(new_final).__name__
            ),
            "new_final_density_contains_beardifier": contains_type(new_final, "minecraft:beardifier"),
            "old_has_aquifers_enabled": "aquifers_enabled" in old,
            "new_has_aquifers_object": "aquifers" in new,
            "old_has_ore_veins_enabled": "ore_veins_enabled" in old,
            "new_has_material_rule": "material_rule" in new,
            "old_noise_size_horizontal": old.get("noise", {}).get("size_horizontal"),
            "old_noise_size_vertical": old.get("noise", {}).get("size_vertical"),
            "new_noise_has_size_fields": (
                "size_horizontal" in new.get("noise", {})
                or "size_vertical" in new.get("noise", {})
            ),
        })

    result = {
        "schema": "supracraft-vanilla-noise-settings-uplift-oracle/1",
        "source": "official Mojang version manifest + official server artifacts",
        "old_version": {
            "id": old_meta["id"],
            "world_version": old_meta.get("world_version"),
            "protocol_version": old_meta.get("protocol_version"),
            "server_sha1": old_meta["downloads"]["server"]["sha1"],
        },
        "new_version": {
            "id": new_meta["id"],
            "world_version": new_meta.get("world_version"),
            "protocol_version": new_meta.get("protocol_version"),
            "server_sha1": new_meta["downloads"]["server"]["sha1"],
        },
        "rows": rows,
        "summary": {
            "setting_count": len(rows),
            "sea_level_preserved_count": sum(r["sea_level_preserved"] for r in rows),
            "default_block_preserved_count": sum(r["default_block_preserved"] for r in rows),
            "new_beardifier_count": sum(r["new_final_density_contains_beardifier"] for r in rows),
            "removed_noise_size_fields_count": sum(not r["new_noise_has_size_fields"] for r in rows),
        },
        "boundary": (
            "This oracle reports exact vanilla migration choices. Official 26.3 technical notes establish "
            "that final_density no longer receives an implicit beardifier; strict third-party behavior "
            "preservation may therefore require an explicit beardifier even where vanilla content chose otherwise."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("SUPRACRAFT_VANILLA_NOISE_SETTINGS_ORACLE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
