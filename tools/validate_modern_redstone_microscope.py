#!/usr/bin/env python3
"""Validate modern redstone microscope stock/instrumented A/B evidence."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def pos(row: dict) -> list:
    data=row.get("data") or {}
    return [data.get("x"),data.get("y"),data.get("z")]


def load_result(root: Path, fixture: str, arm: str) -> dict:
    return json.loads((root/f"redstone-{fixture}-{arm}"/"result.json").read_text())


def load_trace(root: Path, fixture: str) -> list[dict]:
    path=root/f"redstone-{fixture}-instrumented"/"trace.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def validate_fixture(root: Path, fixture: str) -> dict:
    stock=load_result(root,fixture,"stock")
    inst=load_result(root,fixture,"instrumented")
    for key in (
        "minecraft_version","java_major","fixture","expected_actuation",
        "actual_actuation","source_position","wire_positions","gap_position",
        "command_block_position","target_position","command_sha256",
    ):
        assert stock[key]==inst[key],(fixture,key,stock[key],inst[key])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True
    assert stock["world_present"] is True
    assert inst["world_present"] is True
    assert stock["actual_actuation"] is stock["expected_actuation"]
    assert inst["actual_actuation"] is inst["expected_actuation"]

    rows=load_trace(root,fixture)
    assert rows
    assert [r["seq"] for r in rows]==list(range(1,len(rows)+1))
    assert rows[0]["event_type"]=="trace_start"
    assert rows[-1]["event_type"]=="trace_end"
    assert rows[-1]["data"]["dropped_events"]==0

    counts=collections.Counter(r["event_type"] for r in rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","block_state_write",
    ):
        assert counts[required]>0,(fixture,required,counts)

    source=[
        r for r in rows
        if r["event_type"]=="block_state_write"
        and pos(r)==inst["source_position"]
    ]
    assert source,(fixture,"source write")
    source=source[0]

    downstream=[
        r for r in rows
        if r["seq"]>source["seq"]
        and r["event_type"] in {
            "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
            "redstone_power_query","redstone_power_result",
        }
        and pos(r) in inst["wire_positions"]
    ]
    assert downstream,(fixture,"wire downstream evidence")

    starts=[r for r in downstream if r["event_type"]=="wire_recompute_start"]
    ends=[r for r in downstream if r["event_type"]=="wire_recompute_end"]
    assert starts and ends
    assert any(
        s["seq"]<e["seq"] and pos(s)==pos(e)
        for s in starts for e in ends
    )

    command_starts=[
        r for r in rows
        if r["event_type"]=="command_trigger_start"
        and r["data"].get("command_sha256")==inst["command_sha256"]
        and pos(r)==inst["command_block_position"]
    ]
    targets=[
        r for r in rows
        if r["event_type"]=="block_state_write"
        and r["seq"]>source["seq"]
        and pos(r)==inst["target_position"]
    ]

    if fixture=="positive":
        assert command_starts
        start=command_starts[0]
        command_ends=[
            r for r in rows
            if r["event_type"]=="command_trigger_end"
            and r["seq"]>start["seq"]
            and pos(r)==inst["command_block_position"]
        ]
        assert command_ends
        end=command_ends[0]
        target=next(r for r in targets if start["seq"]<r["seq"]<end["seq"])
        assert any(source["seq"]<r["seq"]<start["seq"] for r in downstream)
        assert start["tick"]==target["tick"]==end["tick"]
        positive_values=[
            r["data"]["value"]
            for r in downstream
            if r["event_type"]=="redstone_power_result"
            and isinstance(r["data"].get("value"),int)
            and r["data"]["value"]>0
        ]
        assert positive_values,("positive power result",counts)
        causal={
            "source_write":source["seq"],
            "first_wire_event":min(r["seq"] for r in downstream),
            "command_trigger_start":start["seq"],
            "target_write":target["seq"],
            "command_trigger_end":end["seq"],
        }
    else:
        assert not command_starts
        assert not targets
        causal={
            "source_write":source["seq"],
            "first_wire_event":min(r["seq"] for r in downstream),
            "command_trigger_count":0,
            "target_write_count":0,
        }

    return {
        "semantic_divergence":False,
        "expected_actuation":inst["expected_actuation"],
        "actual_actuation":inst["actual_actuation"],
        "event_counts":dict(sorted(counts.items())),
        "causal_seq":causal,
        "dropped_events":0,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
        "stock_world_sha256":stock["world_sha256"],
        "instrumented_world_sha256":inst["world_sha256"],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    fixtures={
        fixture:validate_fixture(args.root,fixture)
        for fixture in ("positive","gap")
    }
    report={
        "schema":"supracraft-modern-redstone-observer-ab/1",
        "minecraft_version":args.version,
        "sensor_pack":"core+redstone",
        "semantic_divergence":False,
        "fixtures":fixtures,
        "boundary":"connected positive plus one-block-gap hard negative qualify only the observed exact wire-to-command shape; no generic redstone topology or alternate evaluator semantics are promoted",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
