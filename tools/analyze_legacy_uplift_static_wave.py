#!/usr/bin/env python3
"""Cheap static evidence lanes for resource-budgeted legacy uplift waves."""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
from pathlib import Path

from uplift_mcfunction_block_state_snbt import rewrite_text as rewrite_block_state_snbt
from uplift_inline_loot_snbt import rewrite_text as rewrite_inline_loot_snbt
from uplift_sign_allow_op_features import rewrite_text as rewrite_sign_op_features
from uplift_map_color_with_mapping import load_mapping as load_map_color_mapping, rewrite_text as rewrite_map_color


SELECTOR_START = re.compile(r"@[pares]\[")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def git_exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        capture_output=True,
    ).returncode == 0


def split_top_level_csv(body: str) -> list[str]:
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    in_string = False
    quote = ""
    escape = False
    pairs = {"{": "}", "[": "]", "(": ")"}

    for i, ch in enumerate(body):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
        elif ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
        elif ch == "," and not stack:
            parts.append(body[start:i].strip())
            start = i + 1
    parts.append(body[start:].strip())
    return [p for p in parts if p]


def find_selector_close(text: str, open_bracket: int) -> int:
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(open_bracket, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"unterminated selector at offset {open_bracket}")


def canonicalize_selector_order(text: str) -> str:
    """Discovery-only normalization: sort top-level selector options.

    This is deliberately NOT an uplift transformation. It is used only to
    recognize release diffs that differ solely by selector option order.
    """
    out: list[str] = []
    cursor = 0
    while True:
        m = SELECTOR_START.search(text, cursor)
        if not m:
            out.append(text[cursor:])
            break
        out.append(text[cursor:m.start()])
        open_bracket = m.end() - 1
        close = find_selector_close(text, open_bracket)
        prefix = text[m.start():open_bracket + 1]
        body = text[open_bracket + 1:close]
        options = split_top_level_csv(body)
        out.append(prefix + ",".join(sorted(options)) + "]")
        cursor = close + 1
    return "".join(out)


def sprint_residual(repo: Path, old: str, new: str, output: Path, map_color_recipe: Path | None = None) -> None:
    paths = [
        p for p in git(repo, "diff", "--name-only", old, new, "--", "*.mcfunction").splitlines()
        if p
    ]
    both: list[str] = []
    block_candidates: list[str] = []
    loot_candidates: list[str] = []
    sign_candidates: list[str] = []
    safe_exact: list[str] = []
    selector_order_explains: list[str] = []
    residual: list[str] = []
    map_color_candidate_files: list[str] = []
    project_recipe_candidate_files: list[str] = []
    project_recipe_exact_files: list[str] = []
    changed_occurrences = 0
    changed_keys = 0
    loot_occurrences = 0
    sign_occurrences = 0
    map_color_occurrences = 0
    project_recipe_occurrences = 0
    project_recipe_unresolved = 0
    project_mapping = load_map_color_mapping(map_color_recipe) if map_color_recipe else None

    residual_command_heads = collections.Counter()
    map_color_re = re.compile(r"minecraft:filled_map\[[^\n\]]*\bmap_color\s*=")

    for path in paths:
        if not git_exists(repo, f"{old}:{path}") or not git_exists(repo, f"{new}:{path}"):
            continue
        both.append(path)
        old_text = git(repo, "show", f"{old}:{path}")
        new_text = git(repo, "show", f"{new}:{path}")

        block_updated, block_receipts = rewrite_block_state_snbt(old_text)
        loot_updated, loot_receipts = rewrite_inline_loot_snbt(block_updated)
        sign_updated, sign_receipts = rewrite_sign_op_features(loot_updated)

        if project_mapping is not None:
            transformed, map_receipts, map_unresolved = rewrite_map_color(sign_updated, project_mapping)
            if map_receipts:
                project_recipe_candidate_files.append(path)
                project_recipe_occurrences += len(map_receipts)
            project_recipe_unresolved += len(map_unresolved)
        else:
            transformed = sign_updated
            map_receipts = []

        if block_receipts:
            block_candidates.append(path)
            changed_occurrences += len(block_receipts)
            changed_keys += sum(r["change_count"] for r in block_receipts)
        if loot_receipts:
            loot_candidates.append(path)
            loot_occurrences += len(loot_receipts)
        if sign_receipts:
            sign_candidates.append(path)
            sign_occurrences += len(sign_receipts)

        map_hits = map_color_re.findall(old_text)
        if map_hits:
            map_color_candidate_files.append(path)
            map_color_occurrences += len(map_hits)

        if transformed == new_text:
            if block_receipts or loot_receipts or sign_receipts:
                safe_exact.append(path)
            if map_receipts:
                project_recipe_exact_files.append(path)
            continue

        if canonicalize_selector_order(transformed) == canonicalize_selector_order(new_text):
            selector_order_explains.append(path)
            continue

        residual.append(path)
        old_lines = transformed.splitlines()
        new_lines = new_text.splitlines()
        for line in old_lines + new_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            head = stripped.split(None, 1)[0]
            residual_command_heads[head] += 1

    result = {
        "schema": "supracraft-sprint-racer-static-residual/2",
        "source_repository": "jarrodmmoore/Sprint-Racer-Dev",
        "source_license_boundary": "All Rights Reserved; ephemeral checkout, derived receipt only",
        "old": old,
        "new": new,
        "changed_mcfunction_file_count": len(paths),
        "changed_files_present_in_both_releases": len(both),
        "accepted_safe_pipeline": [
            "block_state_snbt_Name_Properties_to_id_properties",
            "inline_loot_functions_to_modifier",
            "inline_loot_function_discriminator_to_type",
            "direct_sign_allow_op_features_true",
        ],
        "block_state_candidate_file_count": len(block_candidates),
        "block_state_occurrence_count": changed_occurrences,
        "block_state_changed_key_count": changed_keys,
        "inline_loot_candidate_file_count": len(loot_candidates),
        "inline_loot_occurrence_count": loot_occurrences,
        "direct_sign_candidate_file_count": len(sign_candidates),
        "direct_sign_occurrence_count": sign_occurrences,
        "accepted_safe_pipeline_exact_file_count": len(safe_exact),
        "project_map_color_recipe": str(map_color_recipe) if map_color_recipe else None,
        "project_map_color_recipe_candidate_file_count": len(project_recipe_candidate_files),
        "project_map_color_recipe_occurrence_count": project_recipe_occurrences,
        "project_map_color_recipe_unresolved_count": project_recipe_unresolved,
        "project_map_color_recipe_exact_file_count": len(project_recipe_exact_files),
        "map_color_structural_candidate_file_count": len(map_color_candidate_files),
        "map_color_structural_occurrence_count": map_color_occurrences,
        "map_color_candidate_sample": map_color_candidate_files[:50],
        "selector_order_additionally_explains_file_count": len(selector_order_explains),
        "selector_order_explained_sample": selector_order_explains[:50],
        "residual_file_count": len(residual),
        "residual_file_sample": residual[:100],
        "residual_command_head_counts": dict(residual_command_heads.most_common(30)),
        "boundary": (
            "selector ordering remains discovery-only; map_color removal is detected "
            "as structural follow-up and is not auto-rewritten"
        ),
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")


def path_family(path: str) -> str:
    parts = path.split("/")
    if "worldgen" in parts:
        i = parts.index("worldgen")
        return "worldgen/" + (parts[i + 1] if i + 1 < len(parts) else "<root>")
    if "data" in parts:
        i = parts.index("data")
        if i + 2 < len(parts):
            return f"data/{parts[i+1]}/{parts[i+2]}"
    suffix = Path(path).suffix.lower() or "<none>"
    return "suffix/" + suffix


def canonical_json_bytes(path: Path) -> bytes | None:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compare_trees(generated: Path, maintained: Path, output: Path) -> None:
    gen = {p.relative_to(generated).as_posix(): p for p in generated.rglob("*") if p.is_file()}
    main = {p.relative_to(maintained).as_posix(): p for p in maintained.rglob("*") if p.is_file()}
    common = sorted(set(gen) & set(main))
    gen_only = sorted(set(gen) - set(main))
    main_only = sorted(set(main) - set(gen))

    exact: list[str] = []
    json_normalized_equal: list[str] = []
    differing: list[str] = []
    families = collections.Counter()

    for rel in common:
        if gen[rel].read_bytes() == main[rel].read_bytes():
            exact.append(rel)
            continue
        gj = canonical_json_bytes(gen[rel])
        mj = canonical_json_bytes(main[rel])
        if gj is not None and mj is not None and gj == mj:
            json_normalized_equal.append(rel)
            continue
        differing.append(rel)
        families[path_family(rel)] += 1

    result = {
        "schema": "supracraft-voidblock-static-residual/1",
        "generated_file_count": len(gen),
        "maintainer_file_count": len(main),
        "common_path_count": len(common),
        "generated_only_count": len(gen_only),
        "maintainer_only_count": len(main_only),
        "exact_byte_equal_common_count": len(exact),
        "json_normalized_equal_common_count": len(json_normalized_equal),
        "differing_common_count": len(differing),
        "differing_common_by_family": dict(families.most_common()),
        "differing_common_sample": differing[:100],
        "generated_only_sample": gen_only[:50],
        "maintainer_only_sample": main_only[:50],
        "boundary": "static structural receipt only; content equality/non-equality is not runtime semantic equivalence",
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sprint-residual")
    s.add_argument("--repo", type=Path, required=True)
    s.add_argument("--old", required=True)
    s.add_argument("--new", required=True)
    s.add_argument("--output", type=Path, required=True)
    s.add_argument("--map-color-recipe", type=Path)

    v = sub.add_parser("compare-trees")
    v.add_argument("--generated", type=Path, required=True)
    v.add_argument("--maintained", type=Path, required=True)
    v.add_argument("--output", type=Path, required=True)

    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.command == "sprint-residual":
        sprint_residual(args.repo, args.old, args.new, args.output, args.map_color_recipe)
    elif args.command == "compare-trees":
        compare_trees(args.generated, args.maintained, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
