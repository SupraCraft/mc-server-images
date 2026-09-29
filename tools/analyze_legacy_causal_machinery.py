#!/usr/bin/env python3
"""Extract a coarse causal/semantic machinery graph from legacy Anvil worlds.

This intentionally separates:
- observed physical machinery,
- command semantics,
- inferred candidate connectivity,
- unresolved causal direction.

It is a structural oracle, not a player-experience score.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import struct
import tempfile
import zipfile
import zlib
from collections import Counter, defaultdict, deque
from pathlib import Path

import nbtlib


# Legacy numeric block IDs relevant to authored interaction machinery.
BLOCKS = {
    23: ("dispenser", ["actuator"]),
    25: ("note_block", ["presentation_feedback"]),
    29: ("sticky_piston", ["actuator"]),
    33: ("piston", ["actuator"]),
    54: ("chest", ["state_memory"]),
    55: ("redstone_wire", ["signal_transport"]),
    61: ("furnace", ["state_memory"]),
    62: ("lit_furnace", ["state_memory"]),
    63: ("standing_sign", ["presentation_feedback"]),
    64: ("wooden_door", ["actuator"]),
    68: ("wall_sign", ["presentation_feedback"]),
    69: ("lever", ["sensor_input", "state_memory"]),
    70: ("stone_pressure_plate", ["sensor_input"]),
    71: ("iron_door", ["actuator"]),
    72: ("wooden_pressure_plate", ["sensor_input"]),
    75: ("redstone_torch_off", ["logic_gate", "signal_transport"]),
    76: ("redstone_torch_on", ["logic_gate", "signal_transport"]),
    77: ("stone_button", ["sensor_input"]),
    93: ("repeater_off", ["timer_clock", "signal_transport"]),
    94: ("repeater_on", ["timer_clock", "signal_transport"]),
    96: ("trapdoor", ["actuator"]),
    107: ("fence_gate", ["actuator"]),
    123: ("redstone_lamp_off", ["presentation_feedback"]),
    124: ("redstone_lamp_on", ["presentation_feedback"]),
    131: ("tripwire_hook", ["sensor_input"]),
    132: ("tripwire", ["sensor_input", "signal_transport"]),
    137: ("command_block", ["condition_query", "actuator", "orchestrator"]),
    143: ("wooden_button", ["sensor_input"]),
    146: ("trapped_chest", ["sensor_input", "state_memory"]),
    147: ("light_weighted_pressure_plate", ["sensor_input"]),
    148: ("heavy_weighted_pressure_plate", ["sensor_input"]),
    149: ("comparator_off", ["condition_query", "signal_transport"]),
    150: ("comparator_on", ["condition_query", "signal_transport"]),
    151: ("daylight_detector", ["sensor_input"]),
    154: ("hopper", ["state_memory", "actuator"]),
    158: ("dropper", ["actuator"]),
    167: ("iron_trapdoor", ["actuator"]),
    178: ("inverted_daylight_detector", ["sensor_input"]),
    210: ("repeating_command_block", ["condition_query", "actuator", "orchestrator", "timer_clock"]),
    211: ("chain_command_block", ["condition_query", "actuator", "orchestrator"]),
}

COMMAND_ROLE = {
    "testfor": ["condition_query"],
    "testforblock": ["condition_query"],
    "testforblocks": ["condition_query"],
    "execute": ["condition_query", "orchestrator"],
    "scoreboard": ["semantic_state"],
    "setblock": ["actuator"],
    "fill": ["actuator"],
    "clone": ["actuator"],
    "summon": ["actuator"],
    "tp": ["actuator"],
    "teleport": ["actuator"],
    "give": ["actuator"],
    "clear": ["actuator"],
    "replaceitem": ["actuator"],
    "effect": ["actuator", "presentation_feedback"],
    "particle": ["presentation_feedback"],
    "playsound": ["presentation_feedback"],
    "title": ["presentation_feedback"],
    "tellraw": ["presentation_feedback"],
    "say": ["presentation_feedback"],
    "kill": ["actuator"],
    "gamemode": ["actuator"],
    "time": ["actuator"],
    "weather": ["actuator"],
    "spreadplayers": ["actuator"],
    "function": ["orchestrator"],
}

COORD_COMMANDS = {"setblock": 3, "testforblock": 3, "summon": 3, "tp": 3, "teleport": 3}
ABS_INT = re.compile(r"^-?\d+$")


def plain(v):
    if hasattr(v, "unpack"):
        try:
            return v.unpack()
        except Exception:
            pass
    return v


def decompress(payload: bytes, kind: int) -> bytes:
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported compression {kind}")


def iter_chunks(region: Path):
    blob = region.read_bytes()
    if len(blob) < 8192:
        return
    for slot in range(1024):
        off = slot * 4
        sector = int.from_bytes(blob[off:off+3], "big")
        count = blob[off+3]
        if not sector or not count:
            continue
        p = sector * 4096
        if p + 5 > len(blob):
            continue
        length = struct.unpack(">I", blob[p:p+4])[0]
        kind = blob[p+4]
        end = p + 4 + length
        if length < 1 or end > len(blob):
            continue
        yield nbtlib.File.parse(io.BytesIO(decompress(blob[p+5:end], kind)))


def byte_values(tag):
    return [(int(x) & 0xFF) for x in tag]


def nibble_at(arr, index: int) -> int:
    b = int(arr[index // 2]) & 0xFF
    return (b >> (4 if index & 1 else 0)) & 0x0F


def chunk_level(root):
    if hasattr(root, "get") and root.get("Level") is not None:
        return root["Level"]
    return root


def find_world_root(root: Path) -> Path:
    levels = sorted(root.rglob("level.dat"))
    if len(levels) != 1:
        raise RuntimeError(f"expected one level.dat, found {len(levels)}")
    return levels[0].parent


def node_id(pos):
    return f"{pos[0]},{pos[1]},{pos[2]}"


def normalize_command(command: str):
    c = command.strip()
    if c.startswith("/"):
        c = c[1:]
    parts = c.split()
    verb = parts[0].lower() if parts else ""
    return verb, parts


def extract_absolute_target(parts):
    if not parts:
        return None
    verb = parts[0].lower().lstrip("/")
    # Old command syntax only; accept coordinates only when all three are literal ints.
    starts = []
    if verb in {"setblock", "testforblock", "summon"}:
        starts = [1]
    elif verb in {"tp", "teleport"}:
        # tp x y z OR tp <target> x y z
        starts = [1, 2]
    for start in starts:
        xyz = parts[start:start+3]
        if len(xyz) == 3 and all(ABS_INT.match(x) for x in xyz):
            return tuple(int(x) for x in xyz)
    return None


def analyze(world: Path):
    machinery = {}
    tile_entities = {}
    command_meta = {}
    regions = sorted((world / "region").glob("r.*.*.mca"))
    if not regions:
        raise RuntimeError("no region files")

    for region in regions:
        for root in iter_chunks(region):
            level = chunk_level(root)
            cx = int(plain(level.get("xPos", 0)))
            cz = int(plain(level.get("zPos", 0)))

            for te in level.get("TileEntities", []):
                try:
                    pos = (int(plain(te["x"])), int(plain(te["y"])), int(plain(te["z"])))
                except Exception:
                    continue
                tile_entities[pos] = te

            for sec in level.get("Sections", []):
                blocks = sec.get("Blocks")
                if blocks is None:
                    continue
                sy = int(plain(sec.get("Y", 0)))
                base = byte_values(blocks)
                add = sec.get("Add")
                data = sec.get("Data")
                for i, low in enumerate(base):
                    bid = low
                    if add is not None:
                        bid |= nibble_at(add, i) << 8
                    if bid not in BLOCKS:
                        continue
                    lx = i & 15
                    lz = (i >> 4) & 15
                    ly = (i >> 8) & 15
                    pos = (cx * 16 + lx, sy * 16 + ly, cz * 16 + lz)
                    name, roles = BLOCKS[bid]
                    meta = nibble_at(data, i) if data is not None else None
                    machinery[pos] = {
                        "node_id": node_id(pos),
                        "position": list(pos),
                        "legacy_block_id": bid,
                        "legacy_metadata": meta,
                        "family": name,
                        "roles": sorted(set(roles)),
                    }

    command_counts = Counter()
    command_role_counts = Counter()
    scoreboard_ops = Counter()
    explicit_target_edges = []

    for pos, node in machinery.items():
        if "command_block" not in node["family"]:
            continue
        te = tile_entities.get(pos)
        if te is None:
            node["command"] = {"present": False}
            continue
        command = str(plain(te.get("Command", "")))
        verb, parts = normalize_command(command)
        command_counts[verb or "<empty>"] += 1
        roles = COMMAND_ROLE.get(verb, [])
        for role in roles:
            command_role_counts[role] += 1
        if roles:
            node["roles"] = sorted(set(node["roles"]) | set(roles))
        digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
        node["command"] = {
            "present": bool(command.strip()),
            "verb": verb or None,
            "sha256": digest,
            "success_count": int(plain(te.get("SuccessCount", 0))) if te.get("SuccessCount") is not None else None,
            "track_output": bool(plain(te.get("TrackOutput", 1))) if te.get("TrackOutput") is not None else None,
            "auto": bool(plain(te.get("auto", 0))) if te.get("auto") is not None else None,
        }
        if verb == "scoreboard" and len(parts) >= 3:
            scoreboard_ops[" ".join(parts[1:3]).lower()] += 1
        target = extract_absolute_target(parts)
        if target is not None:
            explicit_target_edges.append({
                "source": node_id(pos),
                "target_position": list(target),
                "target": node_id(target) if target in machinery else None,
                "edge_type": "command_explicit_target",
                "certainty": "strong" if target in machinery else "adequate",
                "verb": verb,
            })

    # Physical adjacency is a candidate-causality graph. Direction is deliberately
    # not fabricated where legacy metadata/current power state is insufficient.
    dirs = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    adjacency = []
    undirected = defaultdict(set)
    for pos, node in machinery.items():
        for dx,dy,dz in dirs:
            q = (pos[0]+dx, pos[1]+dy, pos[2]+dz)
            if q not in machinery or pos >= q:
                continue
            adjacency.append({
                "a": node_id(pos),
                "b": node_id(q),
                "edge_type": "physical_adjacency_candidate",
                "certainty": "weak",
            })
            undirected[pos].add(q)
            undirected[q].add(pos)

    # Connected components of observed machinery.
    seen = set()
    components = []
    for start in machinery:
        if start in seen:
            continue
        q = deque([start])
        seen.add(start)
        members = []
        roles = Counter()
        families = Counter()
        while q:
            p = q.popleft()
            members.append(p)
            families[machinery[p]["family"]] += 1
            for role in machinery[p]["roles"]:
                roles[role] += 1
            for nxt in undirected.get(p, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        components.append({
            "component_id": len(components),
            "node_count": len(members),
            "bounds": {
                "min": [min(p[i] for p in members) for i in range(3)],
                "max": [max(p[i] for p in members) for i in range(3)],
            },
            "role_counts": dict(sorted(roles.items())),
            "family_counts": dict(families.most_common()),
            "hybrid_sensor_to_command": roles["sensor_input"] > 0 and (
                roles["orchestrator"] > 0 or families["command_block"] > 0
            ),
            "hybrid_state_to_actuator": roles["state_memory"] > 0 and roles["actuator"] > 0,
        })

    trapped = []
    for pos, node in machinery.items():
        if node["family"] != "trapped_chest":
            continue
        neigh = []
        for d in dirs:
            q=(pos[0]+d[0],pos[1]+d[1],pos[2]+d[2])
            if q in machinery:
                neigh.append({"node_id":node_id(q),"family":machinery[q]["family"],"roles":machinery[q]["roles"]})
        trapped.append({"node_id":node_id(pos),"position":list(pos),"adjacent_machinery":neigh})

    role_counts = Counter()
    family_counts = Counter()
    for node in machinery.values():
        family_counts[node["family"]] += 1
        for role in node["roles"]:
            role_counts[role] += 1

    hybrid_components = [c for c in components if c["hybrid_sensor_to_command"] or c["hybrid_state_to_actuator"]]

    return {
        "schema": "supracraft-legacy-causal-machinery/1",
        "world_format": "legacy_anvil_pre_palette",
        "analysis_kind": "static_structural_feedback_blind",
        "node_count": len(machinery),
        "family_counts": dict(family_counts.most_common()),
        "role_counts": dict(sorted(role_counts.items())),
        "command_semantics": {
            "verb_counts": dict(command_counts.most_common()),
            "role_counts": dict(sorted(command_role_counts.items())),
            "scoreboard_operation_counts": dict(scoreboard_ops.most_common()),
            "explicit_target_edge_count": len(explicit_target_edges),
        },
        "component_count": len(components),
        "hybrid_component_count": len(hybrid_components),
        "largest_components": sorted(components, key=lambda c: c["node_count"], reverse=True)[:50],
        "trapped_chests": trapped,
        "edges": {
            "physical_adjacency_candidate_count": len(adjacency),
            "command_explicit_target_count": len(explicit_target_edges),
            "physical_adjacency_candidates": adjacency,
            "command_explicit_targets": explicit_target_edges,
        },
        "nodes": sorted(machinery.values(), key=lambda n: tuple(n["position"])),
        "limitations": [
            "Physical adjacency is not equivalent to powered redstone connectivity or causal direction.",
            "Legacy block metadata is preserved but this version does not infer all orientation semantics from it.",
            "Redstone dust connections beyond direct observed machinery and opaque solid-block conduction are not fully reconstructed.",
            "Commands are classified by top-level verb; nested execute semantics and relative-coordinate targets are not yet fully resolved.",
            "Static structure cannot establish whether a player perceived or understood the mechanism.",
            "No human feedback labels are loaded by this analyzer."
        ]
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world-zip", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="causal-machinery-") as td:
        root=Path(td)
        with zipfile.ZipFile(args.world_zip) as zf:
            if zf.testzip() is not None:
                raise RuntimeError("source zip failed CRC")
            zf.extractall(root)
        result=analyze(find_world_root(root))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "node_count":result["node_count"],
        "family_counts":result["family_counts"],
        "role_counts":result["role_counts"],
        "command_semantics":result["command_semantics"],
        "component_count":result["component_count"],
        "hybrid_component_count":result["hybrid_component_count"],
        "trapped_chest_count":len(result["trapped_chests"]),
        "largest_components":result["largest_components"][:10],
    },indent=2,sort_keys=True))


if __name__=="__main__":
    main()
