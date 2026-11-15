#!/usr/bin/env python3
"""Adversarial, source-neutral admission check for a *reported* core-custody trace.

This checks temporal consistency of observations, not their provenance. Only an
independent official-server observer can establish that the reported state was
real. Does not exercise Minecraft or qualify a player, story, or release.
"""
import argparse
import json
import sys
from pathlib import Path

SCHEMA = "supracraft.core-custody-trace/v0.1"
CARRIERS = (
    "chest", "main_inventory", "hotbar", "offhand", "cursor", "crafting",
    "loaded_item_entities", "installed_socket",
)
EVENTS = frozenset({"baseline", "transfer", "loss", "reissue", "install", "post_restart"})


class TraceError(ValueError):
    """Inconsistent or incomplete observation sequence."""


def _nonnegative_integer(value, where):
    if type(value) is not int or value < 0:
        raise TraceError(f"{where}: expected a nonnegative integer")
    return value


def check_trace(doc):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise TraceError("schema missing or unsupported")
    if not isinstance(doc.get("core_identity"), str) or not doc["core_identity"]:
        raise TraceError("core_identity must be a nonempty string")
    rows = doc.get("observations")
    if not isinstance(rows, list) or not rows:
        raise TraceError("observations must be a nonempty array")

    prev = None
    saw_real_loss = False
    original_identity = doc["core_identity"]
    for i, row in enumerate(rows):
        prefix = f"observations[{i}]"
        if not isinstance(row, dict):
            raise TraceError(f"{prefix}: expected an object")
        if row.get("seq") != i or type(row.get("seq")) is not int:
            raise TraceError(f"{prefix}: seq must equal contiguous array index {i}")
        event = row.get("event")
        if event not in EVENTS:
            raise TraceError(f"{prefix}: unknown event")
        # Explicitly refusing partial observations prevents a false absence when
        # item entities, chest, cursor, or chunks were not inspected.
        if row.get("scope_complete") is not True:
            raise TraceError(f"{prefix}: partial carrier observation is inadmissible")
        if row.get("origin") != "server_reported":
            raise TraceError(f"{prefix}: expected server_reported evidence label")
        if row.get("core_identity") != original_identity:
            raise TraceError(f"{prefix}: objective identity changed")
        carriers = row.get("carriers")
        if not isinstance(carriers, dict) or set(carriers) != set(CARRIERS):
            raise TraceError(f"{prefix}: missing/extra carrier; require {', '.join(CARRIERS)}")
        count = sum(_nonnegative_integer(carriers[k], f"{prefix}.{k}") for k in CARRIERS)
        if count > 1:
            raise TraceError(f"{prefix}: duplicate objective detected across carriers ({count})")
        reissues = _nonnegative_integer(row.get("reissues"), f"{prefix}.reissues")
        restored = row.get("restored")
        if type(restored) is not bool:
            raise TraceError(f"{prefix}: restored must be boolean")
        if restored and carriers["installed_socket"] != 1:
            raise TraceError(f"{prefix}: restored claimed with no installed objective")
        if event == "baseline" and i != 0:
            raise TraceError(f"{prefix}: baseline may occur only at start")
        if event == "post_restart" and prev is None:
            raise TraceError(f"{prefix}: restart cannot be the first observation")
        if prev:
            if reissues < prev["reissues"] or reissues > prev["reissues"] + 1:
                raise TraceError(f"{prefix}: impossible reissue counter transition")
            if prev["restored"] and not restored:
                raise TraceError(f"{prefix}: restored state regressed")
            if not prev["restored"] and restored and event != "install":
                raise TraceError(f"{prefix}: restoration without an installation event")
            if event == "post_restart" and (not prev["restored"] or not restored):
                raise TraceError(f"{prefix}: restart lacks a previously restored state")
            if event == "reissue":
                if prev["count"] != 0 or not saw_real_loss or reissues != prev["reissues"] + 1:
                    raise TraceError(f"{prefix}: reissue without observed zero-custody loss")
                if count != 1 or carriers["chest"] != 1:
                    raise TraceError(f"{prefix}: reissue must create exactly one chest objective")
                saw_real_loss = False
            elif reissues != prev["reissues"]:
                raise TraceError(f"{prefix}: unrecorded reissue increment")
            if prev["count"] == 0 and count == 1 and event != "reissue":
                raise TraceError(f"{prefix}: new objective appeared without reissue event")
            if prev["count"] == 1 and count == 0 and event != "loss":
                raise TraceError(f"{prefix}: objective disappeared without recorded loss")
        if event == "loss":
            if not prev or prev["count"] != 1 or count != 0 or restored:
                raise TraceError(f"{prefix}: loss must transition from one objective to zero")
            saw_real_loss = True
        if event == "install" and (not restored or carriers["installed_socket"] != 1):
            raise TraceError(f"{prefix}: install must prove physical socket and restoration")
        prev = {"count": count, "reissues": reissues, "restored": restored}
    return {"result": "CONSISTENT_REPORTED_TRACE", "observations": len(rows),
            "final_restored": prev["restored"], "final_reissues": prev["reissues"],
            "warning": "Reported trace only; official server provenance and physical gameplay are not verified"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace", type=Path)
    a = p.parse_args(argv)
    try:
        result = check_trace(json.loads(a.trace.read_text(encoding="utf-8")))
    except (TraceError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"result": "REJECTED", "reason": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
