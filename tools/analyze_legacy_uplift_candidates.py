#!/usr/bin/env python3
"""Detect and safely materialize bounded Java 26.3+ uplift candidates.

This tool deliberately separates:
- SAFE_SYNTACTIC rules that may be auto-applied when exact preconditions match;
- STRUCTURAL_REIMPLEMENTATION and CANDIDATE_MODERNIZATION rules that are advisory
  until runtime equivalence is established.

It never mutates the source tree. --apply-safe writes a separate output tree.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from uplift_predicate_26_2_to_26_3 import uplift_predicate_document
from uplift_mcfunction_block_state_snbt import rewrite_text as rewrite_block_state_snbt

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = REPO_ROOT / "bench/worldgen/corpora/legacy-uplift-rules-26.3-v1.json"
BLOCK_ID_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


def load_catalog(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "supracraft-legacy-uplift-rule-catalog/1":
        raise ValueError(f"unsupported catalog schema: {data.get('schema')!r}")
    return data


def relstr(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in {".json", ".mcmeta", ".mcfunction", ".txt", ".snbt"}


def json_pointer(parts: list[str | int]) -> str:
    if not parts:
        return ""
    out = []
    for p in parts:
        s = str(p).replace("~", "~0").replace("/", "~1")
        out.append(s)
    return "/" + "/".join(out)


def iter_objects(value: Any, parts: list[str | int] | None = None):
    parts = [] if parts is None else parts
    if isinstance(value, dict):
        yield value, parts
        for k, v in value.items():
            yield from iter_objects(v, parts + [k])
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from iter_objects(v, parts + [i])


def looks_like_block_state(obj: dict[str, Any]) -> bool:
    if "Name" not in obj and "Properties" not in obj:
        return False
    if "id" in obj or "properties" in obj:
        return False
    if "Name" in obj:
        if not isinstance(obj["Name"], str) or not BLOCK_ID_RE.match(obj["Name"]):
            return False
    if "Properties" in obj and not isinstance(obj["Properties"], dict):
        return False
    # Avoid broad rewrites of arbitrary Name-only objects by requiring either
    # Properties or a namespaced block id in Name.
    return "Properties" in obj or ("Name" in obj and BLOCK_ID_RE.match(obj["Name"]) is not None)


def safe_findings_for_json(path: Path, root: Path, data: Any) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel = relstr(path, root)
    parts = path.relative_to(root).parts

    if "predicate" in parts:
        _updated_predicate, predicate_changes = uplift_predicate_document(data)
        for change in predicate_changes:
            findings.append({
                "rule_id": change["rule"],
                "class": "SAFE_SYNTACTIC",
                "automatic": True,
                "path": rel,
                "json_pointer": change.get("pointer", ""),
                "detail": {
                    k: v for k, v in change.items()
                    if k not in {"rule", "pointer"}
                },
            })

    for obj, pointer_parts in iter_objects(data):
        if looks_like_block_state(obj):
            findings.append({
                "rule_id": "block_state_Name_Properties_to_id_properties",
                "class": "SAFE_SYNTACTIC",
                "automatic": True,
                "path": rel,
                "json_pointer": json_pointer(pointer_parts),
                "detail": {
                    "has_Name": "Name" in obj,
                    "has_Properties": "Properties" in obj,
                    "Name": obj.get("Name"),
                },
            })
    return findings


def safe_findings_for_mcfunction(path: Path, root: Path, text: str) -> list[dict[str, Any]]:
    _updated, receipts = rewrite_block_state_snbt(text)
    findings: list[dict[str, Any]] = []
    for receipt in receipts:
        findings.append({
            "rule_id": "mcfunction_block_state_snbt_Name_Properties_to_id_properties",
            "class": "SAFE_SYNTACTIC",
            "automatic": True,
            "path": relstr(path, root),
            "json_pointer": f"@offset:{receipt['offset']}",
            "detail": {
                "field": receipt.get("field"),
                "change_count": receipt["change_count"],
            },
        })
    return findings


def path_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if "configured_carver" in rel_parts:
            findings.append({
                "rule_id": "worldgen_configured_carver_directory_to_carver",
                "class": "SAFE_SYNTACTIC",
                "automatic": True,
                "path": relstr(path, root),
            })
        if "configured_feature" in rel_parts:
            findings.append({
                "rule_id": "worldgen_configured_feature_directory_to_feature",
                "class": "SAFE_SYNTACTIC",
                "automatic": True,
                "path": relstr(path, root),
            })
    return findings


def advisory_findings(path: Path, root: Path, text: str, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel = relstr(path, root)
    for rule in catalog["rules"]:
        if rule["class"] == "SAFE_SYNTACTIC":
            continue
        detect = rule.get("detect", {})
        if detect.get("kind") != "text_regex":
            continue
        pat = detect.get("pattern")
        if not pat:
            continue
        m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            findings.append({
                "rule_id": rule["id"],
                "class": rule["class"],
                "automatic": bool(rule.get("automatic", False)),
                "path": rel,
                "match_excerpt": text[max(0, m.start()-80):min(len(text), m.end()+160)].replace("\n", "\\n"),
            })
    return findings


def scan(root: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    findings = path_findings(root)
    parse_errors: list[dict[str, str]] = []
    file_count = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        file_count += 1
        if not is_text_candidate(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if path.suffix.lower() in {".json", ".mcmeta"}:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                parse_errors.append({
                    "path": relstr(path, root),
                    "error": f"{exc.msg} at line {exc.lineno} column {exc.colno}",
                })
            else:
                findings.extend(safe_findings_for_json(path, root, data))

        if path.suffix.lower() == ".mcfunction":
            findings.extend(safe_findings_for_mcfunction(path, root, text))

        findings.extend(advisory_findings(path, root, text, catalog))

    # Dedupe path-based safe findings so a directory with many files does not
    # accidentally look like many distinct migration primitives.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for f in findings:
        key = (f["rule_id"], f.get("path", ""), f.get("json_pointer", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    by_rule = Counter(f["rule_id"] for f in deduped)
    by_class = Counter(f["class"] for f in deduped)
    return {
        "schema": "supracraft-legacy-uplift-scan/1",
        "root": str(root),
        "file_count": file_count,
        "finding_count": len(deduped),
        "counts_by_class": dict(sorted(by_class.items())),
        "counts_by_rule": dict(sorted(by_rule.items())),
        "parse_errors": parse_errors,
        "findings": deduped,
    }


def transform_json(data: Any, *, predicate_file: bool) -> tuple[Any, int]:
    data = copy.deepcopy(data)
    changes = 0

    if predicate_file:
        data, predicate_changes = uplift_predicate_document(data)
        changes += len(predicate_changes)

    def visit(v: Any):
        nonlocal changes
        if isinstance(v, dict):
            if looks_like_block_state(v):
                if "Name" in v:
                    v["id"] = v.pop("Name")
                    changes += 1
                if "Properties" in v:
                    v["properties"] = v.pop("Properties")
                    changes += 1
            for child in list(v.values()):
                visit(child)
        elif isinstance(v, list):
            for child in v:
                visit(child)

    visit(data)
    return data, changes


def rename_worldgen_dirs(root: Path) -> list[dict[str, str]]:
    moves: list[dict[str, str]] = []
    rename_pairs = [("configured_carver", "carver"), ("configured_feature", "feature")]
    for old, new in rename_pairs:
        candidates = sorted(
            [p for p in root.rglob(old) if p.is_dir()],
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for src in candidates:
            if src.name != old:
                continue
            dst = src.with_name(new)
            if dst.exists():
                raise RuntimeError(f"refusing path collision: {src} -> {dst}")
            before = src.relative_to(root).as_posix()
            src.rename(dst)
            moves.append({"from": before, "to": dst.relative_to(root).as_posix()})
    return moves


def apply_safe(source: Path, output: Path, catalog: dict[str, Any]) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"output already exists: {output}")
    shutil.copytree(source, output)

    path_moves = rename_worldgen_dirs(output)
    json_changes: list[dict[str, Any]] = []
    mcfunction_changes: list[dict[str, Any]] = []

    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue

        if path.suffix.lower() in {".json", ".mcmeta"}:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            predicate_file = "predicate" in path.relative_to(output).parts
            updated, changes = transform_json(data, predicate_file=predicate_file)
            if changes:
                path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                json_changes.append({"path": relstr(path, output), "change_count": changes})

        elif path.suffix.lower() == ".mcfunction":
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            updated_text, receipts = rewrite_block_state_snbt(text)
            if receipts:
                path.write_text(updated_text, encoding="utf-8")
                mcfunction_changes.append({
                    "path": relstr(path, output),
                    "changed_occurrence_count": len(receipts),
                    "changed_key_count": sum(int(x["change_count"]) for x in receipts),
                    "fields": sorted({str(x.get("field")) for x in receipts}),
                })

    post_scan = scan(output, catalog)
    residual_safe = [
        f for f in post_scan["findings"]
        if f["class"] == "SAFE_SYNTACTIC" and f.get("automatic")
    ]
    return {
        "schema": "supracraft-legacy-uplift-apply/1",
        "source": str(source),
        "output": str(output),
        "path_moves": path_moves,
        "json_changes": json_changes,
        "mcfunction_changes": mcfunction_changes,
        "post_scan": post_scan,
        "residual_safe_finding_count": len(residual_safe),
        "residual_safe_findings": residual_safe,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="unpacked datapack/world tree to scan")
    ap.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--apply-safe", type=Path, metavar="OUTPUT_TREE")
    ap.add_argument("--fail-on-safe", action="store_true",
                    help="return nonzero if automatically-applicable safe findings remain")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        ap.error(f"root is not a directory: {root}")
    catalog = load_catalog(args.catalog.resolve())
    result = scan(root, catalog)

    if args.apply_safe is not None:
        result["safe_apply"] = apply_safe(root, args.apply_safe.resolve(), catalog)

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    safe_remaining = [
        f for f in result["findings"]
        if f["class"] == "SAFE_SYNTACTIC" and f.get("automatic")
    ]
    if args.apply_safe is not None:
        safe_remaining = result["safe_apply"]["residual_safe_findings"]
    return 2 if args.fail_on_safe and safe_remaining else 0


if __name__ == "__main__":
    sys.exit(main())
