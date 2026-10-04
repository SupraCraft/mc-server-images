#!/usr/bin/env python3
"""Wave-2 static analyzers for legacy uplift residuals.

No semantic promotion occurs here. These tools derive repeatable residual
signatures and classify exact-version deltas after already-qualified
normalizations have been applied.
"""

from __future__ import annotations

import argparse
import collections
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from uplift_mcfunction_block_state_snbt import rewrite_text
from analyze_legacy_uplift_static_wave import canonicalize_selector_order


VERSION_TOKEN = re.compile(r"(?<![A-Za-z0-9_])26\.(?:2|3)(?![A-Za-z0-9_])")
PID_TOKEN = re.compile(r"\b((?:SUB)?PID_[0-9]+_mc)26(?:2|3)\b")
URL_RELEASE_TOKEN = re.compile(r"/26\.(?:2|3)(?:_JE-[^/\s\"]*)?/")
HEX_OR_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def git_exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        capture_output=True,
    ).returncode == 0


def normalize_known_mcfunction(text: str) -> str:
    text, _ = rewrite_text(text)
    return canonicalize_selector_order(text)


def normalize_release_metadata(text: str) -> str:
    text = PID_TOKEN.sub(r"\1<VERSION>", text)
    text = VERSION_TOKEN.sub("<VERSION>", text)
    text = URL_RELEASE_TOKEN.sub("/<VERSION_RELEASE>/", text)
    return text


def token_signature(old_line: str, new_line: str) -> tuple[str, str]:
    """Create bounded lexical signatures instead of preserving third-party source."""
    def scrub(line: str) -> str:
        line = normalize_release_metadata(line.strip())
        line = re.sub(r'"[^"]{32,}"', '"<LONG_STRING>"', line)
        line = HEX_OR_NUM.sub("<N>", line)
        return line[:240]
    return scrub(old_line), scrub(new_line)


def command_head(line: str) -> str:
    s = line.strip()
    if not s or s.startswith("#"):
        return "<comment_or_blank>"
    return s.split(None, 1)[0]


def sprint_clusters(repo: Path, old: str, new: str, output: Path) -> None:
    paths = [
        p for p in git(repo, "diff", "--name-only", old, new, "--", "*.mcfunction").splitlines()
        if p and git_exists(repo, f"{old}:{p}") and git_exists(repo, f"{new}:{p}")
    ]

    residual_files: list[str] = []
    metadata_only_files: list[str] = []
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    head_pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    opcode_counts: collections.Counter[str] = collections.Counter()
    changed_line_pairs = 0

    for path in paths:
        old_text = normalize_known_mcfunction(git(repo, "show", f"{old}:{path}"))
        new_text = normalize_known_mcfunction(git(repo, "show", f"{new}:{path}"))

        if old_text == new_text:
            continue

        if normalize_release_metadata(old_text) == normalize_release_metadata(new_text):
            metadata_only_files.append(path)
            continue

        residual_files.append(path)
        a = old_text.splitlines()
        b = new_text.splitlines()
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            opcode_counts[tag] += 1
            left = a[i1:i2]
            right = b[j1:j2]
            # Pair aligned replacement lines when possible; unmatched lines are
            # still represented with an empty side.
            n = max(len(left), len(right))
            for k in range(n):
                ol = left[k] if k < len(left) else ""
                nl = right[k] if k < len(right) else ""
                sig = token_signature(ol, nl)
                pair_counts[sig] += 1
                head_pair_counts[(command_head(ol), command_head(nl))] += 1
                changed_line_pairs += 1

    # Repeated signatures are candidate migration families, not accepted rules.
    repeated = [
        {
            "old_signature": old_sig,
            "new_signature": new_sig,
            "count": count,
        }
        for (old_sig, new_sig), count in pair_counts.most_common(100)
        if count >= 3
    ]

    result = {
        "schema": "supracraft-sprint-residual-clusters/2",
        "source_repository": "jarrodmmoore/Sprint-Racer-Dev",
        "source_license_boundary": "All Rights Reserved; source used ephemerally, derived signatures only",
        "old": old,
        "new": new,
        "changed_mcfunction_files_present_both": len(paths),
        "release_metadata_only_file_count": len(metadata_only_files),
        "release_metadata_only_sample": metadata_only_files[:50],
        "semantic_or_syntax_residual_file_count": len(residual_files),
        "semantic_or_syntax_residual_sample": residual_files[:80],
        "changed_line_pair_count": changed_line_pairs,
        "opcode_counts": dict(opcode_counts),
        "command_head_pair_counts": [
            {"old": a, "new": b, "count": c}
            for (a, b), c in head_pair_counts.most_common(40)
        ],
        "repeated_residual_signatures": repeated,
        "boundary": (
            "Accepted Block State uplift and selector-order normalization are removed first. "
            "Version/PID-only changes are separated. Repeated signatures are discovery candidates only."
        ),
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")


def json_diff_pointers(a: Any, b: Any, ptr: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if type(a) is not type(b):
        return [{"pointer": ptr or "/", "kind": "type_change"}]
    if isinstance(a, dict):
        keys = sorted(set(a) | set(b))
        for key in keys:
            p = f"{ptr}/{str(key).replace('~','~0').replace('/','~1')}"
            if key not in a:
                out.append({"pointer": p, "kind": "added"})
            elif key not in b:
                out.append({"pointer": p, "kind": "removed"})
            else:
                out.extend(json_diff_pointers(a[key], b[key], p))
        return out
    if isinstance(a, list):
        if a == b:
            return out
        # Lists often encode tags/pools; record bounded structure, not contents.
        return [{"pointer": ptr or "/", "kind": "list_change", "old_len": len(a), "new_len": len(b)}]
    if a != b:
        return [{"pointer": ptr or "/", "kind": "value_change"}]
    return out


def classify_function(old_text: str, new_text: str) -> dict[str, Any]:
    if normalize_release_metadata(old_text) == normalize_release_metadata(new_text):
        return {"class": "RELEASE_METADATA_ONLY", "runtime_needed": False}

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changed: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        left, right = old_lines[i1:i2], new_lines[j1:j2]
        for k in range(max(len(left), len(right))):
            changed.append((left[k] if k < len(left) else "", right[k] if k < len(right) else ""))

    metadata_pairs = 0
    executable_pairs = 0
    heads = collections.Counter()
    for old_line, new_line in changed:
        if normalize_release_metadata(old_line) == normalize_release_metadata(new_line):
            metadata_pairs += 1
            continue
        if old_line.strip().startswith("#") and new_line.strip().startswith("#"):
            metadata_pairs += 1
            continue
        executable_pairs += 1
        heads[(command_head(old_line), command_head(new_line))] += 1

    if executable_pairs == 0:
        cls = "RELEASE_METADATA_ONLY"
        runtime = False
    else:
        cls = "MAINTAINER_BEHAVIOR_CHANGE"
        runtime = False

    return {
        "class": cls,
        "runtime_needed": runtime,
        "changed_pair_count": len(changed),
        "metadata_or_comment_pair_count": metadata_pairs,
        "executable_change_pair_count": executable_pairs,
        "command_head_pairs": [
            {"old": a, "new": b, "count": c}
            for (a, b), c in heads.most_common(12)
        ],
    }


def voidblock_classify(
    generated: Path,
    maintained: Path,
    source_26_2: Path,
    output: Path,
) -> None:
    gen = {p.relative_to(generated).as_posix(): p for p in generated.rglob("*") if p.is_file()}
    main = {p.relative_to(maintained).as_posix(): p for p in maintained.rglob("*") if p.is_file()}
    common = sorted(set(gen) & set(main))

    residuals: list[dict[str, Any]] = []
    classes = collections.Counter()

    for rel in common:
        gp, mp = gen[rel], main[rel]
        if gp.read_bytes() == mp.read_bytes():
            continue
        try:
            gj = json.loads(gp.read_text("utf-8"))
            mj = json.loads(mp.read_text("utf-8"))
            if json.dumps(gj, sort_keys=True) == json.dumps(mj, sort_keys=True):
                continue
        except (UnicodeDecodeError, json.JSONDecodeError):
            gj = mj = None

        item: dict[str, Any] = {"path": rel}
        if rel.endswith(".mcfunction"):
            oldp = source_26_2 / rel
            old_text = oldp.read_text("utf-8") if oldp.exists() else gp.read_text("utf-8")
            info = classify_function(old_text, mp.read_text("utf-8"))
            item.update(info)
        elif gj is not None and mj is not None:
            pointers = json_diff_pointers(gj, mj)
            item["json_diff_pointers"] = pointers[:80]
            pset = {x["pointer"] for x in pointers}

            if "/values" in pset and "/tags/worldgen/structure/" in f"/{rel}":
                item["class"] = "MAINTAINER_NEW_CONTENT_TAG_MEMBERSHIP"
                item["runtime_needed"] = False
            elif "/spawn_overrides" in " ".join(pset) or any("spawn_overrides" in p for p in pset):
                item["class"] = "MAINTAINER_SPAWN_CONTENT_CHANGE"
                item["runtime_needed"] = False
            elif "/worldgen/noise_settings/" in f"/{rel}":
                item["class"] = "UNRESOLVED_WORLDGEN_SEMANTIC_DELTA"
                item["runtime_needed"] = True
            else:
                item["class"] = "UNRESOLVED_JSON_DELTA"
                item["runtime_needed"] = True
        else:
            item["class"] = "UNRESOLVED_NON_JSON_DELTA"
            item["runtime_needed"] = True

        classes[item["class"]] += 1
        residuals.append(item)

    result = {
        "schema": "supracraft-voidblock-residual-classification/2",
        "residual_count": len(residuals),
        "counts_by_class": dict(classes),
        "runtime_candidate_count": sum(1 for x in residuals if x.get("runtime_needed")),
        "residuals": residuals,
        "selection_rule": (
            "Release metadata/content deltas are not uplift compatibility gaps. "
            "Only unresolved semantic deltas may nominate a runtime question."
        ),
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sprint-clusters")
    s.add_argument("--repo", type=Path, required=True)
    s.add_argument("--old", required=True)
    s.add_argument("--new", required=True)
    s.add_argument("--output", type=Path, required=True)

    v = sub.add_parser("voidblock-classify")
    v.add_argument("--generated", type=Path, required=True)
    v.add_argument("--maintained", type=Path, required=True)
    v.add_argument("--source-26-2", type=Path, required=True)
    v.add_argument("--output", type=Path, required=True)

    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.cmd == "sprint-clusters":
        sprint_clusters(args.repo, args.old, args.new, args.output)
    else:
        voidblock_classify(args.generated, args.maintained, args.source_26_2, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
