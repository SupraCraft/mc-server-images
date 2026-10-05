#!/usr/bin/env python3
"""Analyze resource and biome availability directly from Minecraft Anvil region files."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import struct
import tempfile
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import nbtlib


RESOURCE_RULES = {
    "wood": lambda n: n.endswith(("_log", "_wood", "_stem", "_hyphae")),
    "water": lambda n: n == "minecraft:water",
    "lava": lambda n: n == "minecraft:lava",
    "coal": lambda n: n in {"minecraft:coal_ore", "minecraft:deepslate_coal_ore"},
    "copper": lambda n: n in {"minecraft:copper_ore", "minecraft:deepslate_copper_ore"},
    "iron": lambda n: n in {"minecraft:iron_ore", "minecraft:deepslate_iron_ore"},
    "gold": lambda n: n in {"minecraft:gold_ore", "minecraft:deepslate_gold_ore"},
    "redstone": lambda n: n in {"minecraft:redstone_ore", "minecraft:deepslate_redstone_ore"},
    "lapis": lambda n: n in {"minecraft:lapis_ore", "minecraft:deepslate_lapis_ore"},
    "diamond": lambda n: n in {"minecraft:diamond_ore", "minecraft:deepslate_diamond_ore"},
    "emerald": lambda n: n in {"minecraft:emerald_ore", "minecraft:deepslate_emerald_ore"},
    "food_crops": lambda n: n in {
        "minecraft:wheat", "minecraft:carrots", "minecraft:potatoes",
        "minecraft:beetroots", "minecraft:sweet_berry_bush",
        "minecraft:melon", "minecraft:pumpkin",
    },
    "container_affordance": lambda n: n in {
        "minecraft:chest", "minecraft:trapped_chest", "minecraft:barrel",
    },
}

DEPTH_BANDS = [
    ("below_0", -10_000, -1),
    ("0_31", 0, 31),
    ("32_63", 32, 63),
    ("64_127", 64, 127),
    ("128_plus", 128, 10_000),
]


def plain(value):
    if hasattr(value, "unpack"):
        return value.unpack()
    return value


def spawn_from_level_data(data) -> tuple[tuple[int, int, int], str]:
    modern = data.get("spawn") if hasattr(data, "get") else None
    if modern is not None and hasattr(modern, "get"):
        pos = modern.get("pos")
        if pos is not None and len(pos) >= 3:
            return (int(pos[0]), int(pos[1]), int(pos[2])), "level.dat Data.spawn.pos"

    if all(key in data for key in ("SpawnX", "SpawnY", "SpawnZ")):
        return (
            int(data["SpawnX"]),
            int(data["SpawnY"]),
            int(data["SpawnZ"]),
        ), "level.dat legacy SpawnX/SpawnY/SpawnZ"

    return (0, 64, 0), "fallback origin; no recognized spawn fields"


def read_level_spawn(world: Path) -> tuple[tuple[int, int, int], str]:
    level = nbtlib.load(world / "level.dat")
    data = level.get("Data", level)
    return spawn_from_level_data(data)


def decompress_chunk(payload: bytes, compression: int) -> bytes:
    if compression == 1:
        return gzip.decompress(payload)
    if compression == 2:
        return zlib.decompress(payload)
    if compression == 3:
        return payload
    raise ValueError(f"unsupported Anvil compression type {compression}")


def iter_region_chunks(region_path: Path):
    data = region_path.read_bytes()
    if len(data) < 8192:
        raise ValueError(f"{region_path}: region file shorter than Anvil header")
    for slot in range(1024):
        off = slot * 4
        sector_offset = int.from_bytes(data[off:off+3], "big")
        sector_count = data[off+3]
        if sector_offset == 0 or sector_count == 0:
            continue
        pos = sector_offset * 4096
        if pos + 5 > len(data):
            raise ValueError(f"{region_path}: chunk slot {slot} points outside file")
        length = struct.unpack(">I", data[pos:pos+4])[0]
        compression = data[pos+4]
        end = pos + 4 + length
        if length < 1 or end > len(data):
            raise ValueError(f"{region_path}: invalid chunk length at slot {slot}")
        raw = decompress_chunk(data[pos+5:end], compression)
        yield nbtlib.File.parse(io.BytesIO(raw))


def palette_name(entry) -> str:
    if isinstance(entry, str):
        return str(entry)
    if hasattr(entry, "get"):
        for key in ("Name", "name", "id", ""):
            value = entry.get(key)
            if value is not None:
                return str(value)
    return str(entry)


def decode_palette_indices(container, entry_count: int, min_bits: int) -> list[int]:
    palette = container.get("palette")
    if palette is None:
        palette = container.get("Palette")
    if palette is None:
        return []
    palette_len = len(palette)
    if palette_len <= 1:
        return [0] * entry_count

    data = container.get("data")
    if data is None:
        data = container.get("Data")
    if data is None:
        raise ValueError(f"palette has {palette_len} entries but no packed data")

    bits = max(min_bits, math.ceil(math.log2(palette_len)))
    values_per_long = 64 // bits
    mask = (1 << bits) - 1
    longs = [int(x) & ((1 << 64) - 1) for x in data]
    needed = math.ceil(entry_count / values_per_long)
    if len(longs) < needed:
        raise ValueError(
            f"packed palette too short: palette={palette_len} bits={bits} "
            f"need={needed} longs got={len(longs)}"
        )

    out = []
    for i in range(entry_count):
        word = longs[i // values_per_long]
        shift = (i % values_per_long) * bits
        idx = (word >> shift) & mask
        if idx >= palette_len:
            raise ValueError(f"packed palette index {idx} >= palette size {palette_len}")
        out.append(idx)
    return out


def category_for(block: str) -> list[str]:
    return [name for name, predicate in RESOURCE_RULES.items() if predicate(block)]


def band_for(y: int) -> str:
    for name, lo, hi in DEPTH_BANDS:
        if lo <= y <= hi:
            return name
    return "other"


def section_y(section) -> int:
    return int(section.get("Y", section.get("y", 0)))


def locate_world_root(extract_root: Path) -> Path:
    matches=sorted(extract_root.rglob("level.dat"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one level.dat in archive, found {len(matches)}: {matches[:8]}")
    return matches[0].parent


def analyze_world(world: Path, chunk_radius: int = 4) -> dict:
    (spawn_x, spawn_y, spawn_z), spawn_source = read_level_spawn(world)
    spawn_cx=math.floor(spawn_x/16)
    spawn_cz=math.floor(spawn_z/16)
    block_counts = Counter()
    biome_counts = Counter()
    resource_counts = Counter()
    resource_depth = defaultdict(Counter)
    nearest: dict[str, dict | None] = {key: None for key in RESOURCE_RULES}
    chunks_seen = set()
    sections_seen = 0
    decode_errors = []

    region_candidates = [
        world / "dimensions" / "minecraft" / "overworld" / "region",
        world / "region",
    ]
    region_dir = next((p for p in region_candidates if p.is_dir()), region_candidates[0])
    for region_path in sorted(region_dir.glob("r.*.*.mca")):
        for root in iter_region_chunks(region_path):
            chunk = root
            cx = int(chunk.get("xPos", chunk.get("x_pos", 0)))
            cz = int(chunk.get("zPos", chunk.get("z_pos", 0)))
            if abs(cx-spawn_cx) > chunk_radius or abs(cz-spawn_cz) > chunk_radius:
                continue
            chunks_seen.add((cx, cz))
            sections = chunk.get("sections", chunk.get("Sections", []))
            for section in sections:
                sy = section_y(section)
                block_states = section.get("block_states", section.get("BlockStates"))
                if block_states and block_states.get("palette") is not None:
                    try:
                        palette = [palette_name(x) for x in block_states["palette"]]
                        indices = decode_palette_indices(block_states, 4096, 4)
                        sections_seen += 1
                        for i, idx in enumerate(indices):
                            block = palette[idx]
                            block_counts[block] += 1
                            cats = category_for(block)
                            if not cats:
                                continue
                            lx = i & 15
                            lz = (i >> 4) & 15
                            ly = (i >> 8) & 15
                            wx = cx * 16 + lx
                            wy = sy * 16 + ly
                            wz = cz * 16 + lz
                            horizontal = math.hypot(wx - spawn_x, wz - spawn_z)
                            for cat in cats:
                                resource_counts[cat] += 1
                                resource_depth[cat][band_for(wy)] += 1
                                current = nearest[cat]
                                if current is None or horizontal < current["horizontal_distance"]:
                                    nearest[cat] = {
                                        "block": block,
                                        "position": [wx, wy, wz],
                                        "horizontal_distance": round(horizontal, 3),
                                        "vertical_delta_from_spawn": wy - spawn_y,
                                    }
                    except Exception as exc:
                        decode_errors.append({
                            "region": region_path.name,
                            "chunk": [cx, cz],
                            "section_y": sy,
                            "kind": "block_states",
                            "error": str(exc),
                        })

                biomes = section.get("biomes", section.get("Biomes"))
                if biomes and biomes.get("palette") is not None:
                    try:
                        palette = [str(x) for x in biomes["palette"]]
                        indices = decode_palette_indices(biomes, 64, 1)
                        for idx in indices:
                            biome_counts[palette[idx]] += 1
                    except Exception as exc:
                        decode_errors.append({
                            "region": region_path.name,
                            "chunk": [cx, cz],
                            "section_y": sy,
                            "kind": "biomes",
                            "error": str(exc),
                        })

    early_game = {
        "wood_within_64": nearest["wood"] is not None and nearest["wood"]["horizontal_distance"] <= 64,
        "water_within_64": nearest["water"] is not None and nearest["water"]["horizontal_distance"] <= 64,
        "coal_within_96": nearest["coal"] is not None and nearest["coal"]["horizontal_distance"] <= 96,
        "iron_within_96": nearest["iron"] is not None and nearest["iron"]["horizontal_distance"] <= 96,
    }
    early_game["basic_bundle_observed"] = all(early_game.values())

    return {
        "schema": "supracraft-worldgen-resource-biome-static/1",
        "spawn_reference": {
            "position": [spawn_x, spawn_y, spawn_z],
            "source": spawn_source,
        },
        "spawn_chunk": [spawn_cx, spawn_cz],
        "bounded_chunk_box": [
            spawn_cx-chunk_radius,
            spawn_cz-chunk_radius,
            spawn_cx+chunk_radius,
            spawn_cz+chunk_radius
        ],
        "chunks_seen": len(chunks_seen),
        "sections_seen": sections_seen,
        "resource_counts": dict(sorted(resource_counts.items())),
        "resource_depth_bands": {
            cat: dict(sorted(counter.items())) for cat, counter in sorted(resource_depth.items())
        },
        "nearest_resource_from_spawn": nearest,
        "early_game_static_checks": early_game,
        "biome_cell_counts": dict(biome_counts.most_common()),
        "biome_palette_diversity": len(biome_counts),
        "top_block_counts": [
            {"block": block, "count": count}
            for block, count in block_counts.most_common(40)
        ],
        "decode_errors": decode_errors,
        "limitations": [
            "Biome counts are paletted biome-cell counts across loaded chunk sections, not surface-area percentages.",
            "Static block availability does not prove path accessibility or runtime mob ecology.",
            "Nearest-resource distances are horizontal Euclidean distances, not navigation/path costs.",
            "The early-game bundle is a bootstrap static affordance check and does not imply full survival progression.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world-zip", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--chunk-radius", type=int, default=4)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="worldgen-region-analysis-") as td:
        root = Path(td)
        with zipfile.ZipFile(args.world_zip) as zf:
            zf.extractall(root)
        world = locate_world_root(root)
        result = analyze_world(world, chunk_radius=args.chunk_radius)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["decode_errors"]:
        raise SystemExit(f"region analysis observed {len(result['decode_errors'])} decode errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
