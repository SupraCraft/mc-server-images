#!/usr/bin/env python3
"""Uplift selected inline loot SNBT syntax from Java 26.2 to 26.3.

Implemented safe schema changes:
- loot-entry top-level functions:[...] -> modifier:[...]
- top-level loot-function object discriminator function: -> type:

Scope is restricted to mcfunction commands whose command line is loot ... or
contains run loot .... Arbitrary fields named function/functions are never
globally rewritten.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


LOOT_LINE = re.compile(r"(^|\\srun\\s)loot\\s")


def find_matching(text: str, open_index: int, open_char: str, close_char: str) -> int:
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
        elif ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return i

    raise ValueError(f"unterminated {open_char}{close_char} at offset {open_index}")


def rewrite_loot_function_discriminators(body: str) -> tuple[str, int]:
    out: list[str] = []
    i = 0
    curly = 0
    square = 0
    in_string = False
    quote = ""
    escape = False
    changes = 0

    while i < len(body):
        ch = body[i]
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

        if ch == "{":
            curly += 1
            out.append(ch)
            i += 1
            continue
        if ch == "}":
            curly -= 1
            out.append(ch)
            i += 1
            continue
        if ch == "[":
            square += 1
            out.append(ch)
            i += 1
            continue
        if ch == "]":
            square -= 1
            out.append(ch)
            i += 1
            continue

        if curly == 1 and square == 0 and body.startswith("function", i):
            before_ok = i == 0 or not (body[i - 1].isalnum() or body[i - 1] == "_")
            j = i + len("function")
            while j < len(body) and body[j].isspace():
                j += 1
            if before_ok and j < len(body) and body[j] == ":":
                out.append("type")
                i += len("function")
                changes += 1
                continue

        out.append(ch)
        i += 1

    return "".join(out), changes


def line_is_loot_command(text: str, pos: int) -> bool:
    line_start = text.rfind("\n", 0, pos) + 1
    line = text[line_start:pos]
    while line_start > 0:
        prev_end = line_start - 1
        prev_start = text.rfind("\n", 0, prev_end) + 1
        prev_line = text[prev_start:prev_end]
        if not prev_line.rstrip().endswith("\\"):
            break
        line_start = prev_start
        line = text[line_start:pos]
    normalized = line.replace("\\\n", " ")
    return bool(LOOT_LINE.search(normalized.lstrip()))


def rewrite_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    needle = "functions:["
    out: list[str] = []
    cursor = 0
    receipts: list[dict[str, Any]] = []

    while True:
        start = text.find(needle, cursor)
        if start < 0:
            out.append(text[cursor:])
            break

        if not line_is_loot_command(text, start):
            out.append(text[cursor:start + len(needle)])
            cursor = start + len(needle)
            continue

        open_bracket = start + len(needle) - 1
        close_bracket = find_matching(text, open_bracket, "[", "]")
        body = text[open_bracket + 1:close_bracket]
        rewritten_body, discriminator_changes = rewrite_loot_function_discriminators(body)

        out.append(text[cursor:start])
        out.append("modifier:[" + rewritten_body + "]")
        receipts.append({
            "offset": start,
            "field_change": "functions_to_modifier",
            "loot_function_discriminator_changes": discriminator_changes,
        })
        cursor = close_bracket + 1

    return "".join(out), receipts


def process_file(source: Path, output: Path) -> dict[str, Any]:
    text = source.read_text("utf-8")
    updated, receipts = rewrite_text(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(updated, "utf-8")
    return {
        "schema": "supracraft-inline-loot-26.2-to-26.3-uplift/1",
        "source": str(source),
        "output": str(output),
        "changed_loot_entry_count": len(receipts),
        "loot_function_discriminator_change_count": sum(
            int(r["loot_function_discriminator_changes"]) for r in receipts
        ),
        "receipts": receipts,
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
        ap.error("source and output must differ")

    receipt = process_file(args.source, args.output)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(payload + "\n", "utf-8")
    else:
        print(payload)

    if args.require_change and receipt["changed_loot_entry_count"] == 0:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
