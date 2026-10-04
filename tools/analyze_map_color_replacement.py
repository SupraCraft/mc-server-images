#!/usr/bin/env python3
"""Mine exact legacy filled-map map_color replacement evidence between two git refs.

This is an evidence extractor, not a materializer. It aligns legacy lines that
contain minecraft:filled_map[...] map_color=... with maintained target lines and
records any observed item_model replacement. Ambiguous or unaligned cases remain
unresolved rather than being guessed.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
from pathlib import Path


MAP_COLOR_RE = re.compile(r"\bmap_color\s*=\s*([^,\]]+)")
ITEM_MODEL_RE = re.compile(r"\bitem_model\s*=\s*([^,\]]+)")
FILLED_MAP = "minecraft:filled_map["


def git(repo: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        capture_output=True,
    )
    return p.stdout


def exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        text=True,
        capture_output=True,
    ).returncode == 0


def legacy_paths(repo: Path, old: str) -> list[str]:
    out = git(repo, "grep", "-l", "map_color=", old, "--", "*.mcfunction", check=False)
    return sorted(x for x in out.splitlines() if x)


def mine(repo: Path, old: str, new: str) -> dict:
    paths = legacy_paths(repo, old)
    mapping_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    color_totals: collections.Counter[str] = collections.Counter()
    unresolved = []
    aligned = 0
    legacy_occurrences = 0
    files_with_observed_replacement = set()

    for path in paths:
        if not exists(repo, f"{new}:{path}"):
            unresolved.append({"path": path, "reason": "missing_in_target"})
            continue

        old_lines = git(repo, "show", f"{old}:{path}").splitlines()
        new_lines = git(repo, "show", f"{new}:{path}").splitlines()
        old_hits = [
            (i, line, MAP_COLOR_RE.search(line))
            for i, line in enumerate(old_lines)
            if FILLED_MAP in line and MAP_COLOR_RE.search(line)
        ]
        legacy_occurrences += len(old_hits)

        for i, old_line, match in old_hits:
            assert match is not None
            color = match.group(1).strip()
            color_totals[color] += 1

            if i >= len(new_lines):
                unresolved.append({
                    "path": path,
                    "line": i + 1,
                    "color": color,
                    "reason": "target_line_missing",
                })
                continue

            new_line = new_lines[i]
            model_match = ITEM_MODEL_RE.search(new_line) if FILLED_MAP in new_line else None
            if not model_match:
                unresolved.append({
                    "path": path,
                    "line": i + 1,
                    "color": color,
                    "reason": "no_aligned_item_model",
                })
                continue

            model = model_match.group(1).strip().strip('"\'')
            mapping_counts[(color, model)] += 1
            aligned += 1
            files_with_observed_replacement.add(path)

    models_by_color: dict[str, list[dict[str, object]]] = {}
    for color in sorted(color_totals):
        rows = [
            {"item_model": model, "count": count}
            for (c, model), count in mapping_counts.items()
            if c == color
        ]
        rows.sort(key=lambda x: (-int(x["count"]), str(x["item_model"])))
        models_by_color[color] = rows

    deterministic = {
        color: rows[0]["item_model"]
        for color, rows in models_by_color.items()
        if len(rows) == 1
    }
    ambiguous = {
        color: rows
        for color, rows in models_by_color.items()
        if len(rows) > 1
    }

    return {
        "schema": "supracraft-map-color-replacement-evidence/1",
        "old": old,
        "new": new,
        "legacy_candidate_file_count": len(paths),
        "legacy_occurrence_count": legacy_occurrences,
        "aligned_item_model_replacement_count": aligned,
        "unresolved_occurrence_count": len(unresolved),
        "files_with_observed_replacement_count": len(files_with_observed_replacement),
        "color_occurrence_counts": dict(sorted(color_totals.items())),
        "models_by_color": models_by_color,
        "deterministic_color_to_model_observations": deterministic,
        "ambiguous_color_to_model_observations": ambiguous,
        "unresolved_sample": unresolved[:100],
        "boundary": (
            "observed project-local mappings are evidence only; raw map_color "
            "integers do not establish a universal 26.3 replacement"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    result = mine(args.repo, args.old, args.new)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
