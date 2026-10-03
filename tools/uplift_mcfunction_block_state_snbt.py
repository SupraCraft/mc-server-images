#!/usr/bin/env python3
"""Safely rewrite legacy Block State SNBT embedded inside .mcfunction text.

Only keys at the top level of a `block_state:{...}` compound are rewritten:
  Name       -> id
  Properties -> properties

This deliberately does not perform global Name/Properties replacement and
therefore leaves fields such as CustomName untouched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PREFIX = "block_state:{"


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    in_string = False
    quote = ""
    escape = False

    for i in range(open_index, len(text)):
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
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

    raise ValueError(f"unterminated SNBT compound starting at {open_index}")


def rewrite_top_level_keys(compound: str) -> tuple[str, int]:
    """Rewrite Name/Properties keys only at depth zero of an SNBT body."""
    out: list[str] = []
    i = 0
    depth = 0
    in_string = False
    quote = ""
    escape = False
    changes = 0

    while i < len(compound):
        ch = compound[i]

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            i += 1
            continue

        if ch in {'"', "'"}:
            in_string = True
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch in "{[":
            depth += 1
            out.append(ch)
            i += 1
            continue
        if ch in "}]":
            depth -= 1
            out.append(ch)
            i += 1
            continue

        if depth == 0:
            replaced = False
            for old, new in (("Properties", "properties"), ("Name", "id")):
                if compound.startswith(old, i):
                    before_ok = i == 0 or not (compound[i - 1].isalnum() or compound[i - 1] == "_")
                    j = i + len(old)
                    while j < len(compound) and compound[j].isspace():
                        j += 1
                    after_ok = j < len(compound) and compound[j] == ":"
                    if before_ok and after_ok:
                        out.append(new)
                        i += len(old)
                        changes += 1
                        replaced = True
                        break
            if replaced:
                continue

        out.append(ch)
        i += 1

    return "".join(out), changes


def rewrite_text(text: str) -> tuple[str, list[dict[str, int]]]:
    out: list[str] = []
    cursor = 0
    receipts: list[dict[str, int]] = []

    while True:
        start = text.find(PREFIX, cursor)
        if start < 0:
            out.append(text[cursor:])
            break

        out.append(text[cursor:start])
        open_brace = start + len(PREFIX) - 1
        close_brace = find_matching_brace(text, open_brace)

        full = text[start:close_brace + 1]
        body = full[len(PREFIX):-1]
        rewritten_body, changes = rewrite_top_level_keys(body)
        rewritten = PREFIX + rewritten_body + "}"

        out.append(rewritten)
        if changes:
            receipts.append({
                "offset": start,
                "change_count": changes,
            })
        cursor = close_brace + 1

    return "".join(out), receipts


def process_file(source: Path, output: Path) -> dict:
    text = source.read_text("utf-8")
    rewritten, occurrences = rewrite_text(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rewritten, "utf-8")
    return {
        "schema": "supracraft-mcfunction-block-state-snbt-uplift/1",
        "source": str(source),
        "output": str(output),
        "changed_occurrence_count": len(occurrences),
        "changed_key_count": sum(x["change_count"] for x in occurrences),
        "occurrences": occurrences,
        "source_unchanged": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--require-change", action="store_true")
    args = ap.parse_args()

    if args.source.resolve() == args.output.resolve():
        ap.error("source and output must differ; uplift never mutates source evidence")

    receipt = process_file(args.source, args.output)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")
    else:
        print(json.dumps(receipt, indent=2, sort_keys=True))

    if args.require_change and receipt["changed_occurrence_count"] == 0:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
