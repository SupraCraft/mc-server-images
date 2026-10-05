#!/usr/bin/env python3
"""Create a small versioned SupraCraft tour datapack in a Minecraft world."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PACK_NAME = "supracraft_benchmark"


def _safe_id(value: str) -> str:
    if not value or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in value):
        raise ValueError(f"unsafe tour site id: {value!r}")
    return value


def write_tour_pack(world: Path, data_pack_major: int, run_id: str, sites: list[dict[str, Any]]) -> dict[str, Any]:
    if not sites:
        raise ValueError("at least one tour site is required")

    pack = world / "datapacks" / PACK_NAME
    functions = pack / "data" / "supracraft" / "function" / "tour"
    functions.mkdir(parents=True, exist_ok=True)

    pack_meta = {
        "pack": {
            "min_format": [int(data_pack_major), 0],
            "max_format": [int(data_pack_major), 0],
            "description": f"SupraCraft worldgen benchmark tour: {run_id}",
        }
    }
    (pack / "pack.mcmeta").write_text(json.dumps(pack_meta, indent=2) + "\n", "utf-8")

    normalized = []
    for raw in sites:
        site_id = _safe_id(str(raw["site_id"]))
        category = str(raw["category"])
        position = [float(v) for v in raw["position"]]
        if len(position) != 3:
            raise ValueError(f"{site_id}: position must have 3 values")
        look_at = raw.get("look_at")
        if look_at is not None:
            look_at = [float(v) for v in look_at]
            if len(look_at) != 3:
                raise ValueError(f"{site_id}: look_at must have 3 values")

        x, y, z = position
        tp = f"tp @s {x:g} {y:g} {z:g}"
        if look_at is not None:
            tx, ty, tz = look_at
            tp += f" facing {tx:g} {ty:g} {tz:g}"

        lines = [
            "gamemode spectator @s",
            "effect give @s minecraft:night_vision infinite 0 true",
            tp,
            "tellraw @s " + json.dumps({"text": f"[{category}] {raw['reason']}", "color": "gold"}, separators=(",", ":")),
        ]
        (functions / f"{site_id}.mcfunction").write_text("\n".join(lines) + "\n", "utf-8")
        normalized.append({
            "site_id": site_id,
            "category": category,
            "position": position,
            "look_at": look_at,
            "reason": str(raw["reason"]),
            "teleport": f"/function supracraft:tour/{site_id}",
        })

    first = normalized[0]["site_id"]
    (functions / "start.mcfunction").write_text(
        "\n".join([
            "say SUPRACRAFT_TOUR_PACK_OK",
            "gamemode spectator @s",
            "effect give @s minecraft:night_vision infinite 0 true",
            f"function supracraft:tour/{first}",
        ]) + "\n",
        "utf-8",
    )

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "sites": normalized,
        "tour_start_command": "/function supracraft:tour/start",
        "pack_id": f"file/{PACK_NAME}",
        "data_pack_major": int(data_pack_major),
    }
    (world / "SUPRACRAFT-TOUR.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
    (world / "SUPRACRAFT-TOUR.txt").write_text(
        "SupraCraft world-generator benchmark tour\n\n"
        "Open the world in Minecraft Java 26.3.\n"
        "Use /gamemode spectator or /gamemode creative freely.\n"
        "Start the tour with:\n"
        "  /function supracraft:tour/start\n\n"
        + "\n".join(f"  {s['teleport']} - [{s['category']}] {s['reason']}" for s in normalized)
        + "\n",
        "utf-8",
    )
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--data-pack-major", type=int, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sites", type=Path, required=True, help="JSON array of site objects")
    args = ap.parse_args()
    sites = json.loads(args.sites.read_text("utf-8"))
    manifest = write_tour_pack(args.world, args.data_pack_major, args.run_id, sites)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
