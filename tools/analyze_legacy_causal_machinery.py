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
    "blockdata": ["semantic_state", "actuator"],
    "entitydata": ["semantic_state", "actuator"],
    "gamerule": ["semantic_state"],
    "spawnpoint": ["semantic_state", "actuator"],
    "xp": ["actuator"],
    "difficulty": ["semantic_state", "actuator"],
    "function": ["orchestrator"],
}

KNOWN_LEGACY_VANILLA_VERBS = set(COMMAND_ROLE) | {
    "achievement", "ban", "ban-ip", "banlist", "debug", "defaultgamemode",
    "deop", "enchant", "help", "kick", "list", "me", "op", "pardon",
    "pardon-ip", "publish", "save-all", "save-off", "save-on", "seed",
    "setidletimeout", "stop", "whitelist", "worldborder"
}

ABS_INT = re.compile(r"^-?\d+$")
ABS_NUM = re.compile(r"^-?(?:\d+(?:\.\d*)?|\.\d+)$")
DIR4 = {
    0: ("north", (0, 0, -1)),
    1: ("east", (1, 0, 0)),
    2: ("south", (0, 0, 1)),
    3: ("west", (-1, 0, 0)),
}
DIR6 = {
    0: ("down", (0, -1, 0)),
    1: ("up", (0, 1, 0)),
    2: ("north", (0, 0, -1)),
    3: ("south", (0, 0, 1)),
    4: ("west", (-1, 0, 0)),
    5: ("east", (1, 0, 0)),
}
BUTTON_META_FACING = {
    0: ("down", (0, -1, 0)),
    1: ("east", (1, 0, 0)),
    2: ("west", (-1, 0, 0)),
    3: ("south", (0, 0, 1)),
    4: ("north", (0, 0, -1)),
    5: ("up", (0, 1, 0)),
}
CHEST_FACING = {
    2: "north",
    3: "south",
    4: "west",
    5: "east",
}


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


def presentation_payload_fingerprints(command: str, verb: str):
    """Return text-free hashes for exact authored presentation payloads.

    Minecraft 1.8.8 tellraw syntax is: tellraw <target> <json>. Preserve only
    cryptographic fingerprints and coarse JSON shape so runtime packet hashes
    can be cross-checked without retaining authored message text.
    """
    if verb != "tellraw":
        return None
    text=command.strip()
    if text.startswith("/"):
        text=text[1:]
    fields=text.split(None,2)
    if len(fields) < 3:
        return {
            "kind":"tellraw_json",
            "parse_status":"missing_payload",
        }

    payload=fields[2].strip()
    out={
        "kind":"tellraw_json",
        "parse_status":"unparsed",
        "wire_json_sha256":hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest(),
    }
    try:
        parsed=json.loads(payload)
    except Exception:
        return out

    canonical=json.dumps(
        parsed,ensure_ascii=False,separators=(",",":")
    )
    out.update({
        "parse_status":"parsed",
        "json_kind":(
            "string" if isinstance(parsed,str)
            else "array" if isinstance(parsed,list)
            else "object" if isinstance(parsed,dict)
            else type(parsed).__name__
        ),
        "canonical_json_sha256":hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
    })
    if isinstance(parsed,str):
        out["literal_text_sha256"]=hashlib.sha256(
            parsed.encode("utf-8")
        ).hexdigest()
    return out


def add_pos(a, delta):
    return (a[0] + delta[0], a[1] + delta[1], a[2] + delta[2])


def opposite(delta):
    return (-delta[0], -delta[1], -delta[2])


def metadata_semantics(family: str, meta: int | None):
    if meta is None:
        return {}

    out = {"raw": meta}
    if family in {"repeater_off", "repeater_on"}:
        name, delta = DIR4[meta & 0x3]
        out.update({
            "facing": name,
            "facing_vector": list(delta),
            "delay_redstone_ticks": ((meta >> 2) & 0x3) + 1,
            "powered": family.endswith("_on"),
            "port_semantics": "legacy facing points from output side toward input side; input is +facing, output is -facing",
        })
    elif family in {"comparator_off", "comparator_on"}:
        name, delta = DIR4[meta & 0x3]
        out.update({
            "facing": name,
            "facing_vector": list(delta),
            "mode": "subtract" if (meta & 0x4) else "compare",
            "powered": family.endswith("_on"),
            "port_semantics": "legacy facing points from output side toward rear input; rear input is +facing, output is -facing",
        })
    elif family in {"command_block", "repeating_command_block", "chain_command_block"}:
        code = meta & 0x7
        if code in DIR6:
            name, delta = DIR6[code]
            out.update({"facing": name, "facing_vector": list(delta)})
        else:
            out.update({"facing": "invalid_or_legacy_unused", "facing_code": code})
        out["conditional"] = bool(meta & 0x8)
    elif family in {"dispenser", "dropper", "hopper", "piston", "sticky_piston"}:
        code = meta & 0x7
        if code in DIR6:
            name, delta = DIR6[code]
            out.update({"facing": name, "facing_vector": list(delta)})
        out["active_or_extended_bit"] = bool(meta & 0x8)
    elif family in {"trapped_chest", "chest"}:
        if meta in CHEST_FACING:
            out["facing"] = CHEST_FACING[meta]
        if family == "trapped_chest":
            out["open_sensor_state"] = "dynamic_not_stored_in_block_metadata"
            out["inventory_signal_state"] = "readable_by_comparator"
    elif family == "redstone_wire":
        out["power_level"] = meta & 0xF
        out["connection_shape"] = "runtime_derived_not_stored"
    elif family in {"redstone_lamp_off", "redstone_lamp_on"}:
        out["lit"] = family.endswith("_on")
    elif family in {"redstone_torch_off", "redstone_torch_on"}:
        out["lit"] = family.endswith("_on")
        out["attachment_code"] = meta & 0x7
    elif family in {"stone_button", "wooden_button"}:
        code = meta & 0x7
        name, facing = BUTTON_META_FACING.get(code, BUTTON_META_FACING[5])
        support = opposite(facing)
        out.update({
            "powered": bool(meta & 0x8),
            "attachment_code": code,
            "facing": name,
            "facing_vector": list(facing),
            "support_vector": list(support),
            "support_semantics": "Minecraft 1.8.8 BlockButton support is opposite FACING; powered button strongly powers and notifies that attached support block",
        })
    elif family == "lever":
        out["powered"] = bool(meta & 0x8)
        out["attachment_code"] = meta & 0x7
    elif family in {"stone_pressure_plate", "wooden_pressure_plate"}:
        stored_powered = meta == 1
        out.update({
            "powered": stored_powered,
            "stored_state": 1 if stored_powered else 0,
            "power_level": 15 if stored_powered else 0,
            "occupancy_semantics": (
                "living_entities_only"
                if family == "stone_pressure_plate"
                else "all_triggering_entities"
            ),
            "support_vector": [0, -1, 0],
            "support_semantics": (
                "Minecraft 1.8.8 BlockBasePressurePlate strongly powers only the "
                "support side below; ordinary BlockPressurePlate serializes powered "
                "state as metadata 0/1 while emitting strength 0/15"
            ),
        })
    elif family in {"light_weighted_pressure_plate", "heavy_weighted_pressure_plate"}:
        power = meta & 0xF
        out.update({
            "powered": power > 0,
            "stored_state": power,
            "power_level": power,
            "occupancy_semantics": "entity_count_weighted_signal",
            "entity_count_capacity": (
                15 if family == "light_weighted_pressure_plate" else 150
            ),
            "support_vector": [0, -1, 0],
            "support_semantics": (
                "Minecraft 1.8.8 BlockBasePressurePlate strongly powers only the "
                "support side below; BlockPressurePlateWeighted serializes its 0..15 "
                "power level directly"
            ),
        })
    return out


def parse_coord(token: str, origin_value: int):
    if token.startswith("~"):
        suffix = token[1:]
        if suffix == "":
            return float(origin_value)
        if ABS_NUM.match(suffix):
            return float(origin_value) + float(suffix)
        return None
    if ABS_NUM.match(token):
        return float(token)
    return None


def resolve_xyz(tokens, origin):
    if len(tokens) != 3:
        return None
    vals = [parse_coord(tokens[i], origin[i]) for i in range(3)]
    if any(v is None for v in vals):
        return None
    return tuple(int(v) if float(v).is_integer() else float(v) for v in vals)


def command_targets(parts, command_origin):
    if not parts:
        return []
    verb = parts[0].lower().lstrip("/")
    specs = []
    if verb in {"setblock", "testforblock", "summon"}:
        specs = [("point", 1)]
    elif verb in {"tp", "teleport"}:
        # tp x y z OR tp <target> x y z
        for start in (1, 2):
            if len(parts) >= start + 3:
                pos = resolve_xyz(parts[start:start+3], command_origin)
                if pos is not None:
                    return [{"kind": "point", "position": pos, "coordinate_mode": "resolved_absolute_or_relative"}]
        return []
    elif verb == "fill":
        specs = [("region_start", 1), ("region_end", 4)]
    elif verb == "clone":
        specs = [("source_start", 1), ("source_end", 4), ("destination", 7)]
    else:
        return []

    out = []
    for kind, start in specs:
        pos = resolve_xyz(parts[start:start+3], command_origin)
        if pos is not None:
            out.append({"kind": kind, "position": pos, "coordinate_mode": "resolved_absolute_or_relative"})
    return out


def read_scoreboard(world: Path):
    # Since Java 26.1 persistent saved data is namespaced under data/<namespace>/.
    candidates = [
        world / "data" / "minecraft" / "scoreboard.dat",
        world / "data" / "scoreboard.dat",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return {"present": False, "path": None, "objectives": [], "scores": []}
    root = nbtlib.load(path)
    data = root.get("data", root.get("Data", root))
    objectives = []
    for obj in data.get("Objectives", []):
        objectives.append({
            "name": str(plain(obj.get("Name", ""))),
            "criteria": str(plain(obj.get("CriteriaName", ""))),
            "display_name": str(plain(obj.get("DisplayName", ""))) if obj.get("DisplayName") is not None else None,
            "render_type": str(plain(obj.get("RenderType", ""))) if obj.get("RenderType") is not None else None,
        })
    scores = []
    for score in data.get("PlayerScores", []):
        scores.append({
            "name": str(plain(score.get("Name", ""))),
            "objective": str(plain(score.get("Objective", ""))),
            "score": int(plain(score.get("Score", 0))),
            "locked": bool(plain(score.get("Locked", 0))) if score.get("Locked") is not None else None,
        })
    return {"present": True, "path": str(path.relative_to(world)), "objectives": objectives, "scores": scores}


def scoreboard_refs(parts):
    if len(parts) < 3 or parts[0].lower().lstrip("/") != "scoreboard":
        return []
    domain = parts[1].lower()
    op = parts[2].lower()
    refs = []
    if domain == "objectives" and op in {"add", "remove"} and len(parts) >= 4:
        refs.append({"objective": parts[3], "access": "write"})
    elif domain == "objectives" and op == "setdisplay" and len(parts) >= 5:
        refs.append({"objective": parts[4], "access": "read"})
    elif domain == "players":
        if op in {"set", "add", "remove", "test", "enable"} and len(parts) >= 5:
            refs.append({"objective": parts[4], "access": "read" if op == "test" else "write"})
        elif op == "reset" and len(parts) >= 5:
            refs.append({"objective": parts[4], "access": "write"})
        elif op == "operation" and len(parts) >= 8:
            refs.append({"objective": parts[4], "access": "write"})
            refs.append({"objective": parts[7], "access": "read"})
    return refs


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


LEGACY_SENSOR_FAMILIES = {
    "lever", "stone_button", "wooden_button",
    "stone_pressure_plate", "wooden_pressure_plate",
    "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
    "tripwire_hook", "daylight_detector", "inverted_daylight_detector",
    "trapped_chest",
}

LEGACY_DIRECT_WIRE_SINKS = {
    "command_block", "repeating_command_block", "chain_command_block",
    "redstone_lamp_off", "redstone_lamp_on",
    "piston", "sticky_piston",
    "dispenser", "dropper", "hopper",
    "note_block", "iron_door", "wooden_door",
    "trapdoor", "iron_trapdoor", "fence_gate",
}


def legacy_direct_redstone_edges(machinery):
    """Recover only direct redstone relations that do not require hidden solid-block conduction.

    Same-level dust-to-dust adjacency is structurally strong. Sensor-to-dust and
    horizontal dust-to-direct-sink adjacency are adequate potential causal edges
    because attachment/state details may still matter. Exact Minecraft 1.8.8
    source separately grounds powered wire immediately above a legacy command
    block as a directed power relation. Repeater/comparator ports are handled
    separately from their orientation metadata.
    """
    edges=[]
    horizontal=((1,0,0),(-1,0,0),(0,0,1),(0,0,-1))
    all_sides=horizontal+((0,1,0),(0,-1,0))

    for pos,node in machinery.items():
        family=node["family"]
        if family=="redstone_wire":
            for delta in horizontal:
                q=add_pos(pos,delta)
                if q in machinery and machinery[q]["family"]=="redstone_wire":
                    edges.append({
                        "source":node_id(pos),"target":node_id(q),
                        "edge_type":"legacy_dust_horizontal_connection",
                        "certainty":"strong",
                    })
                elif q in machinery and machinery[q]["family"] in LEGACY_DIRECT_WIRE_SINKS:
                    edges.append({
                        "source":node_id(pos),"target":node_id(q),
                        "edge_type":"legacy_dust_direct_component_power",
                        "certainty":"adequate",
                    })
            below=add_pos(pos,(0,-1,0))
            if below in machinery and machinery[below]["family"]=="command_block":
                edges.append({
                    "source":node_id(pos),"target":node_id(below),
                    "edge_type":"legacy_dust_downward_command_power",
                    "certainty":"strong",
                    "basis":(
                        "exact Minecraft 1.8.8 BlockCommandBlock.onNeighborBlockChange "
                        "uses World.isBlockPowered; World.isBlockPowered queries the "
                        "block above with EnumFacing.UP; BlockRedstoneWire.getWeakPower "
                        "returns wire power for side UP"
                    ),
                })
        if family in LEGACY_SENSOR_FAMILIES:
            for delta in all_sides:
                q=add_pos(pos,delta)
                if q in machinery and machinery[q]["family"]=="redstone_wire":
                    edges.append({
                        "source":node_id(pos),"target":node_id(q),
                        "edge_type":"legacy_sensor_direct_dust_power",
                        "certainty":"adequate",
                    })
        if family in {"stone_button", "wooden_button"}:
            support_vector=node.get("metadata_semantics",{}).get("support_vector")
            if support_vector:
                q=add_pos(pos,tuple(support_vector))
                if q in machinery:
                    edges.append({
                        "source":node_id(pos),"target":node_id(q),
                        "edge_type":"legacy_button_attached_support_power",
                        "certainty":"strong",
                        "basis":"exact Minecraft 1.8.8 BlockButton metadata FACING; attached support is opposite FACING",
                    })
        if family in {
            "stone_pressure_plate", "wooden_pressure_plate",
            "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
        }:
            support_vector=node.get("metadata_semantics",{}).get("support_vector")
            if support_vector:
                q=add_pos(pos,tuple(support_vector))
                if q in machinery:
                    edges.append({
                        "source":node_id(pos),"target":node_id(q),
                        "edge_type":"legacy_pressure_plate_support_power",
                        "certainty":"strong",
                        "basis":"exact Minecraft 1.8.8 BlockBasePressurePlate strong power is emitted only toward EnumFacing.UP, i.e. the supporting block below",
                    })
    return edges


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
                        "metadata_semantics": metadata_semantics(name, meta),
                        "family": name,
                        "roles": sorted(set(roles)),
                    }

    scoreboard = read_scoreboard(world)
    scoreboard_objectives = {x["name"]: x for x in scoreboard["objectives"] if x["name"]}
    semantic_state_nodes = {
        name: {
            "node_id": f"scoreboard_objective::{name}",
            "kind": "scoreboard_objective",
            "objective": name,
            "criteria": meta.get("criteria"),
            "display_name": meta.get("display_name"),
            "render_type": meta.get("render_type"),
        }
        for name, meta in scoreboard_objectives.items()
    }

    command_counts = Counter()
    unknown_command_counts = Counter()
    unknown_command_nodes = []
    command_role_counts = Counter()
    scoreboard_ops = Counter()
    explicit_target_edges = []
    scoreboard_edges = []

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
        if not verb:
            unknown_command_counts["<empty>"] += 1
            unknown_command_nodes.append({"node_id":node_id(pos),"verb":None,"sha256":hashlib.sha256(command.encode("utf-8")).hexdigest(),"reason":"empty_command"})
        elif verb not in KNOWN_LEGACY_VANILLA_VERBS:
            unknown_command_counts[verb] += 1
            unknown_command_nodes.append({"node_id":node_id(pos),"verb":verb,"sha256":hashlib.sha256(command.encode("utf-8")).hexdigest(),"reason":"unknown_or_nonvanilla_verb"})
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
            "powered": bool(plain(te.get("powered", 0))) if te.get("powered") is not None else None,
            "condition_met": bool(plain(te.get("conditionMet", 0))) if te.get("conditionMet") is not None else None,
            "last_execution": int(plain(te.get("LastExecution", 0))) if te.get("LastExecution") is not None else None,
            "custom_name": str(plain(te.get("CustomName"))) if te.get("CustomName") is not None else None,
            "last_output_sha256": (
                hashlib.sha256(str(plain(te.get("LastOutput"))).encode("utf-8")).hexdigest()
                if te.get("LastOutput") is not None else None
            ),
            "presentation_payload_fingerprints":presentation_payload_fingerprints(
                command,verb
            ),
        }
        if verb == "scoreboard" and len(parts) >= 3:
            scoreboard_ops[" ".join(parts[1:3]).lower()] += 1
            for ref in scoreboard_refs(parts):
                objective = ref["objective"]
                if objective not in semantic_state_nodes:
                    semantic_state_nodes[objective] = {
                        "node_id": f"scoreboard_objective::{objective}",
                        "kind": "scoreboard_objective_reference_only",
                        "objective": objective,
                        "criteria": None,
                        "display_name": None,
                        "render_type": None,
                    }
                scoreboard_edges.append({
                    "source": node_id(pos),
                    "target": semantic_state_nodes[objective]["node_id"],
                    "edge_type": f"scoreboard_{ref['access']}",
                    "certainty": "strong",
                    "operation": " ".join(parts[1:3]).lower(),
                })
        for target_info in command_targets(parts, pos):
            target = target_info["position"]
            target_block_pos = tuple(int(v) for v in target) if all(float(v).is_integer() for v in target) else None
            explicit_target_edges.append({
                "source": node_id(pos),
                "target_position": list(target),
                "target": node_id(target_block_pos) if target_block_pos in machinery else None,
                "edge_type": "command_world_target",
                "target_kind": target_info["kind"],
                "coordinate_mode": target_info["coordinate_mode"],
                "certainty": "strong" if target_block_pos in machinery else "adequate",
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

    directed_edges = []
    direct_redstone_edges = legacy_direct_redstone_edges(machinery)
    comparator_container_reads = []
    trapped_open_power_edges = []
    command_chain_edges = []

    for pos, node in machinery.items():
        sem = node.get("metadata_semantics", {})
        family = node["family"]

        if family in {"repeater_off", "repeater_on", "comparator_off", "comparator_on"} and sem.get("facing_vector"):
            facing = tuple(sem["facing_vector"])
            input_pos = add_pos(pos, facing)
            output_pos = add_pos(pos, opposite(facing))
            if input_pos in machinery:
                directed_edges.append({
                    "source": node_id(input_pos),
                    "target": node_id(pos),
                    "edge_type": "oriented_rear_input_candidate",
                    "certainty": "adequate",
                    "basis": "legacy metadata facing; facing is output-to-input direction",
                })
            if output_pos in machinery:
                directed_edges.append({
                    "source": node_id(pos),
                    "target": node_id(output_pos),
                    "edge_type": "oriented_front_output_candidate",
                    "certainty": "adequate",
                    "basis": "legacy metadata facing; output is opposite facing",
                })
            if family.startswith("comparator") and input_pos in machinery and machinery[input_pos]["family"] in {"chest", "trapped_chest", "hopper", "furnace", "lit_furnace"}:
                comparator_container_reads.append({
                    "source": node_id(input_pos),
                    "target": node_id(pos),
                    "edge_type": "container_inventory_signal_read",
                    "certainty": "strong",
                })

        if family in {"command_block", "repeating_command_block", "chain_command_block"} and sem.get("facing_vector"):
            facing = tuple(sem["facing_vector"])
            next_pos = add_pos(pos, facing)
            prev_pos = add_pos(pos, opposite(facing))
            if family == "chain_command_block" and next_pos in machinery and "command_block" in machinery[next_pos]["family"]:
                command_chain_edges.append({
                    "source": node_id(pos),
                    "target": node_id(next_pos),
                    "edge_type": "chain_facing_successor_candidate",
                    "certainty": "adequate",
                })
            if sem.get("conditional") and prev_pos in machinery and "command_block" in machinery[prev_pos]["family"]:
                command_chain_edges.append({
                    "source": node_id(prev_pos),
                    "target": node_id(pos),
                    "edge_type": "conditional_predecessor_success_dependency",
                    "certainty": "strong",
                })

        if family == "trapped_chest":
            for dx,dy,dz in dirs:
                q = (pos[0]+dx, pos[1]+dy, pos[2]+dz)
                if q in machinery and machinery[q]["family"] not in {"chest", "trapped_chest"}:
                    trapped_open_power_edges.append({
                        "source": node_id(pos),
                        "target": node_id(q),
                        "edge_type": "open_emits_redstone_power_candidate",
                        "certainty": "adequate",
                        "channel": "player_open_count_signal",
                    })

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
        trapped.append({
            "node_id":node_id(pos),
            "position":list(pos),
            "adjacent_machinery":neigh,
            "semantic_channels": [
                "player_open_count_redstone_output",
                "inventory_fullness_comparator_output"
            ],
            "channel_separation": "opening signal and inventory/fullness signal are distinct causal channels"
        })

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
            "unknown_or_empty_verb_counts": dict(unknown_command_counts.most_common()),
            "unknown_or_empty_nodes": unknown_command_nodes,
            "role_counts": dict(sorted(command_role_counts.items())),
            "scoreboard_operation_counts": dict(scoreboard_ops.most_common()),
            "world_target_edge_count": len(explicit_target_edges),
            "command_chain_edge_count": len(command_chain_edges),
        },
        "semantic_state": {
            "scoreboard_present": scoreboard["present"],
            "objective_count": len(semantic_state_nodes),
            "score_record_count": len(scoreboard["scores"]),
            "objectives": sorted(semantic_state_nodes.values(), key=lambda x: x["objective"]),
            "scoreboard_edges": scoreboard_edges,
        },
        "component_count": len(components),
        "hybrid_component_count": len(hybrid_components),
        "largest_components": sorted(components, key=lambda c: c["node_count"], reverse=True)[:50],
        "trapped_chests": trapped,
        "edges": {
            "physical_adjacency_candidate_count": len(adjacency),
            "oriented_signal_edge_count": len(directed_edges),
            "direct_redstone_edge_count": len(direct_redstone_edges),
            "command_world_target_count": len(explicit_target_edges),
            "command_chain_edge_count": len(command_chain_edges),
            "container_comparator_read_count": len(comparator_container_reads),
            "trapped_chest_open_power_edge_count": len(trapped_open_power_edges),
            "scoreboard_state_edge_count": len(scoreboard_edges),
            "physical_adjacency_candidates": adjacency,
            "oriented_signal_candidates": directed_edges,
            "direct_redstone_edges": direct_redstone_edges,
            "command_world_targets": explicit_target_edges,
            "command_chain_candidates": command_chain_edges,
            "container_comparator_reads": comparator_container_reads,
            "trapped_chest_open_power_candidates": trapped_open_power_edges,
            "scoreboard_state_edges": scoreboard_edges,
        },
        "nodes": sorted(machinery.values(), key=lambda n: tuple(n["position"])),
        "limitations": [
            "Physical adjacency is not equivalent to powered redstone connectivity or causal direction.",
            "Repeater/comparator metadata ports, command-block facing, exact 1.8.8 button attachment direction, exact 1.8.8 pressure-plate stored/output power semantics, and the exact 1.8.8 powered-wire-above to legacy-command-block-below relation are decoded. Same-level dust continuity, direct sensor/dust/component relations, button-to-attached-support power, and pressure-plate-to-support power are recovered separately; other vertical dust steps, opaque solid-block conduction beyond these exact relations, locking/side-input behavior, and quasi-connectivity remain incomplete.",
            "Trapped-chest opening power and comparator inventory/fullness reads are represented as distinct causal channels.",
            "Direct command coordinates including tilde-relative coordinates are resolved where the command-block origin is sufficient; nested execute contexts remain dynamic and unresolved.",
            "Scoreboard objectives/reads/writes are semantic-state graph nodes, but selector expansion and all player/entity instances are not statically resolved.",
            "Static structure cannot establish whether a player perceived or understood the mechanism.",
            "Unknown command verbs may be malformed, map-specific, plugin-provided, or version-specific; they are evidence candidates, not automatically defects.",
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
        "semantic_state": {
            "scoreboard_present": result["semantic_state"]["scoreboard_present"],
            "objective_count": result["semantic_state"]["objective_count"],
            "score_record_count": result["semantic_state"]["score_record_count"],
            "scoreboard_edge_count": len(result["semantic_state"]["scoreboard_edges"]),
        },
        "edge_counts": {
            k:v for k,v in result["edges"].items() if k.endswith("_count")
        },
        "component_count":result["component_count"],
        "hybrid_component_count":result["hybrid_component_count"],
        "trapped_chest_count":len(result["trapped_chests"]),
        "largest_components":result["largest_components"][:10],
    },indent=2,sort_keys=True))


if __name__=="__main__":
    main()
