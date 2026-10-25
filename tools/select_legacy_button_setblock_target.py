#!/usr/bin/env python3
"""Select one CORE 1.8.8 original button->setblock source-static trial target.

SOURCE REVIEW ONLY: no Minecraft execution, source redistribution, coordinates,
raw commands, original command hashes or reversible witness identities in output.
The private selection is deterministically recomputed only inside original custody.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from tools.rank_legacy_typed_sensor_command_witnesses import _is_typed, rank
from tools.audit_legacy_piston_authored_inputs import _exact_integer_position, spatial_mutator_contacts

SCHEMA = "supracraft-legacy-button-setblock-source-target-selection/1"
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _source_candidates(graph):
    """Ephemeral original identities only; never serialize returned records."""
    ranked = rank(graph)  # fail closed for forged/duplicate graph identities
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    targets = defaultdict(list)
    rows = edges.get("command_world_targets")
    if not isinstance(rows, list):
        raise ValueError("source world target collection missing")
    for e in rows:
        if not isinstance(e, dict):
            raise ValueError("malformed source world target row")
        targets[e.get("source")].append(e)
    found = {}
    for e in edges["direct_redstone_edges"]:
        a, b = nodes.get(e["source"]), nodes.get(e["target"])
        if not a or not b:
            continue
        if (a["family"] != "wooden_button"
                or b["family"] != "command_block"
                or _is_typed(a, b, e) != "button_command_support"):
            continue
        cmd = b.get("command") or {}
        if cmd.get("verb") != "setblock":
            continue
        digest = cmd.get("sha256")
        target_rows = [r for r in targets[b["node_id"]]
                       if r.get("target_kind") == "point"
                       and r.get("edge_type") == "command_world_target"]
        target = (_exact_integer_position(target_rows[0].get("target_position"))
                  if len(target_rows) == 1 else None)
        key = (a["node_id"], b["node_id"])
        found[key] = {
            "sensor": tuple(a["position"]),
            "command_pos": tuple(b["position"]),
            "command_id": b["node_id"],
            "sha": digest if isinstance(digest, str) and DIGEST.fullmatch(digest) else None,
            "target": target,
            "target_edges": len(target_rows),
        }
    # Source route count is an independent equality check, not an assertion
    # about runtime power, command invocation, or gameplay semantics.
    expected = ranked["original_mutation_verb_path_counts"].get(
        "direct_support_wooden_button__setblock", 0)
    if len(found) != expected:
        raise ValueError("original button/setblock ranker parity mismatch")
    return sorted(found.values(), key=lambda v: (v["sensor"], v["command_pos"]))


def _other_writer_class(graph, candidate):
    """Conservative bounded writers; unknown dynamic contexts stay UNKNOWN."""
    at = candidate["target"]
    if at is None:
        return "UNRESOLVED_TARGET"
    if candidate["target_edges"] != 1:
        return "AMBIGUOUS_SOURCE_TARGET"
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    point_writers = set()
    for e in graph["edges"]["command_world_targets"]:
        if e.get("edge_type") != "command_world_target" or e.get("target_kind") != "point":
            continue
        if _exact_integer_position(e.get("target_position")) != at:
            continue
        writer = nodes.get(e.get("source"))
        if writer and (writer.get("command") or {}).get("verb") in {"setblock", "fill", "clone", "execute"}:
            point_writers.add(writer["node_id"])
    if point_writers - {candidate["command_id"]}:
        return "OTHER_POINT_WRITER"
    bounds = spatial_mutator_contacts(graph, {at})
    if sum(bounds["spatial_write_footprint_candidate_overlaps"].values()):
        return "OTHER_BOUNDED_SPATIAL_WRITER"
    # This does not exclude nested execute, indirect target, scheduler, block
    # update or external modification. Those are disclosed globally as unknown.
    return "NO_IDENTIFIED_COMPETING_STATIC_WRITER"


def _source_observations(source_zip: Path, candidates):
    """Ephemeral command tile entity + saved ID/metadata, in pinned source custody."""
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks, chunk_level, find_world_root, byte_values, nibble_at,
        plain, normalize_command, resolve_xyz,
    )
    positions = {c["command_pos"] for c in candidates}
    positions |= {c["target"] for c in candidates if c["target"] is not None}
    chunks = defaultdict(set)
    for pos in positions:
        x, y, z = pos
        if 0 <= y < 256:
            chunks[(x // 16, z // 16)].add(pos)
    result = {}
    commands = {}
    with tempfile.TemporaryDirectory(prefix="core-button-target-custody-") as td:
        base = Path(td)
        with zipfile.ZipFile(source_zip) as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(i.file_size for i in infos) > 250 * 1024 * 1024:
                raise ValueError("source archive exceeds bounded custody")
            if archive.testzip() is not None:
                raise ValueError("original ZIP CRC mismatch")
            for item in infos:
                p = PurePosixPath(item.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe source archive")
            archive.extractall(base)
        world = find_world_root(base)
        for region in sorted((world / "region").glob("r.*.*.mca")):
            for root in iter_chunks(region):
                level = chunk_level(root)
                key = (int(plain(level.get("xPos", 0))), int(plain(level.get("zPos", 0))))
                if key not in chunks:
                    continue
                sections = {int(plain(s.get("Y", 0))): s
                            for s in level.get("Sections", []) if s.get("Blocks") is not None}
                for pos in chunks[key]:
                    x, y, z = pos
                    section = sections.get(y // 16)
                    if section is None:
                        result[pos] = (0, 0)  # missing section is saved air
                        continue
                    index = (x % 16) + ((z % 16) << 4) + ((y % 16) << 8)
                    block = byte_values(section["Blocks"])[index]
                    if section.get("Add") is not None:
                        block |= nibble_at(section["Add"], index) << 8
                    data = nibble_at(section["Data"], index) if section.get("Data") is not None else None
                    result[pos] = (block, data)
                for te in level.get("TileEntities", []):
                    try:
                        pos = (int(plain(te["x"])), int(plain(te["y"])), int(plain(te["z"])))
                    except (KeyError, TypeError, ValueError):
                        continue
                    if pos in positions:
                        commands[pos] = str(plain(te.get("Command", "")))
    verified = {}
    for c in candidates:
        raw = commands.get(c["command_pos"])
        matched = isinstance(raw, str) and bool(raw) and c["sha"] is not None and (
            hashlib.sha256(raw.encode("utf-8")).hexdigest() == c["sha"])
        syntax_valid = False
        if matched:
            verb, parts = normalize_command(raw)
            # Only standalone 1.8.8 setblock with explicit material and exact
            # absolute/tilde target; never interpret nested execute strings.
            resolved = resolve_xyz(parts[1:4], c["command_pos"]) if len(parts) >= 5 else None
            computed = _exact_integer_position(list(resolved)) if resolved is not None else None
            syntax_valid = (verb == "setblock" and bool(parts[4].strip()) and
                            computed is not None and computed == c["target"])
        verified[c["command_id"]] = {
            "sha_matches": bool(matched),
            "syntax_target_matches": bool(syntax_valid),
            "saved": result.get(c["target"]),
        }
    return verified


def qualify(graph, candidates, observations):
    failures = Counter()
    eligible = []
    for c in candidates:
        why = None
        target = c["target"]
        if c["sha"] is None:
            why = "MISSING_COMMAND_FINGERPRINT"
        elif c["target_edges"] != 1 or target is None or not 0 <= target[1] < 256:
            why = "UNRESOLVED_SINGLE_BLOCK_TARGET"
        elif target == c["sensor"] or target == c["command_pos"]:
            why = "SOURCE_SENSOR_OR_COMMAND_AS_TARGET"
        elif not observations.get(c["command_id"], {}).get("sha_matches"):
            why = "ORIGINAL_TILE_ENTITY_COMMAND_SHA_MISMATCH"
        elif not observations[c["command_id"]].get("syntax_target_matches"):
            why = "ORIGINAL_SETBLOCK_TARGET_MISMATCH"
        elif observations[c["command_id"]].get("saved") is None:
            why = "SAVED_TARGET_NOT_RESOLVED"
        elif (not isinstance(observations[c["command_id"]]["saved"], tuple)
              or len(observations[c["command_id"]]["saved"]) != 2
              or not isinstance(observations[c["command_id"]]["saved"][0], int)
              or observations[c["command_id"]]["saved"][1] is None):
            why = "SAVED_TARGET_STATE_INCOMPLETE"
        else:
            writer = _other_writer_class(graph, c)
            if writer != "NO_IDENTIFIED_COMPETING_STATIC_WRITER":
                why = writer
        if why:
            failures[why] += 1
        else:
            eligible.append(c)
    return {
        "schema": SCHEMA,
        "analysis": "original_1_8_8_source_static_button_setblock_trial_target_only",
        "source_button_setblock_candidate_count": len(candidates),
        "qualified_source_target_candidate_count": len(eligible),
        "source_selection_disposition": (
            "ONE_RECOMPUTABLE_STATIC_TRIAL_TARGET_SELECTED"
            if eligible else "BUTTON_TARGET_UNRESOLVED"),
        "selection_rejection_reason_counts": dict(sorted(failures.items())),
        "selected_trial_target_count": 1 if eligible else 0,
        "selection_rule": "deterministic_original_source_order_ephemeral_only",
        "alternative_writer_boundary": "NO_IDENTIFIED_STATIC_COMPETITOR_ONLY__INDIRECT_AND_RUNTIME_WRITERS_UNKNOWN",
        "original_native_activation": "NOT_RUN",
        "runtime_command_execution": "NOT_OBSERVED",
        "runtime_target_mutation": "NOT_OBSERVED",
        "exclusive_causality": "NOT_PROVEN",
        "minecraft_26_3_parity": "NOT_RUN",
        "gameplay_promoted": False,
        "limitations": [
            "The selected original coordinate and command SHA remain ephemeral; this aggregate cannot reconstruct a trial.",
            "Saved state and authored setblock syntax do not establish a difference after actuation.",
            "Other indirect or dynamic writers, scheduled updates and nested execute remain UNKNOWN.",
            "Source-only trial target does not authorize original native Minecraft, merge or deployment.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--source-zip", type=Path, required=True)
    p.add_argument("--expected-graph-sha256", required=True)
    p.add_argument("--expected-source-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit("refuse overwrite")
    source_sha = hashlib.sha256(args.source_zip.read_bytes()).hexdigest()
    graph_raw = args.graph.read_bytes()
    graph_sha = hashlib.sha256(graph_raw).hexdigest()
    if source_sha != args.expected_source_sha256 or graph_sha != args.expected_graph_sha256:
        raise SystemExit("original source or frozen graph SHA mismatch")
    graph = json.loads(graph_raw)
    candidates = _source_candidates(graph)
    if len(candidates) != 25:
        raise SystemExit("original candidate census drift")
    observations = _source_observations(args.source_zip, candidates)
    out = qualify(graph, candidates, observations)
    out["source_world_sha256"] = source_sha
    out["source_graph_sha256"] = graph_sha
    text = json.dumps(out, sort_keys=True, indent=2) + "\n"
    if any(s in text for s in ('"position"', '"node_id"', '"command"', '"target_position"', '"sha"', "original-world.zip")):
        raise SystemExit("source custody/privacy guard failure")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(json.dumps({"disposition": out["source_selection_disposition"],
                      "candidates": len(candidates),
                      "eligible": out["qualified_source_target_candidate_count"],
                      "native": "NOT_RUN"}, sort_keys=True))


if __name__ == "__main__":
    main()
