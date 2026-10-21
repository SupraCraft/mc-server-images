#!/usr/bin/env python3
"""Analyze a generic persona trace for navigation/progression proxies.

These outputs are behavioral evidence. They do not directly measure fun,
fairness, frustration, boredom, or immersion.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path


def dist3(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def cell(pos, size=4.0):
    return tuple(math.floor(float(v) / size) for v in (pos[0], pos[2]))


def analyze(doc):
    events = sorted(doc["events"], key=lambda e: float(e["t"]))
    if len(events) < 2:
        raise ValueError("trace must contain at least two events")
    if any(float(events[i]["t"]) > float(events[i+1]["t"]) for i in range(len(events)-1)):
        raise ValueError("event timestamps must be monotonic")

    total_distance = 0.0
    repeat_distance = 0.0
    visited = {cell(events[0]["position"])}
    transitions = Counter()
    prior_cell = cell(events[0]["position"])
    unique_cells = {prior_cell}

    for prev, cur in zip(events, events[1:]):
        step = dist3(prev["position"], cur["position"])
        total_distance += step
        cc = cell(cur["position"])
        transitions[(prior_cell, cc)] += 1
        if cc in visited and cc != prior_cell:
            repeat_distance += step
        visited.add(cc)
        unique_cells.add(cc)
        prior_cell = cc

    start = events[0]["position"]
    end = events[-1]["position"]
    displacement = dist3(start, end)
    directness = displacement / total_distance if total_distance > 0 else 1.0
    detour_ratio = total_distance / displacement if displacement > 0 else None
    backtrack_ratio = repeat_distance / total_distance if total_distance > 0 else 0.0
    repeated_transition_count = sum(v - 1 for v in transitions.values() if v > 1)
    transition_count = max(1, sum(transitions.values()))
    loop_transition_rate = repeated_transition_count / transition_count

    action_events = [
        e for e in events
        if e["kind"] in {"interaction", "move", "retry"}
    ]
    failed_actions = [
        e for e in action_events
        if e.get("success") is False
    ]
    unproductive_action_rate = len(failed_actions) / len(action_events) if action_events else 0.0

    progress_events = [
        e for e in events
        if e["kind"] in {"progress", "objective_complete"} or e.get("progress_id")
    ]
    progress_times = [float(events[0]["t"])] + [float(e["t"]) for e in progress_events]
    if progress_times[-1] != float(events[-1]["t"]):
        progress_times.append(float(events[-1]["t"]))
    progress_gaps = [
        b - a for a, b in zip(progress_times, progress_times[1:])
        if b >= a
    ]
    max_progress_gap = max(progress_gaps) if progress_gaps else 0.0
    mean_progress_gap = sum(progress_gaps) / len(progress_gaps) if progress_gaps else 0.0

    # Behavioral stall: >= 15s between progress events and either repeated failed
    # actions or low net displacement relative to movement inside that interval.
    stall_windows = []
    progress_boundaries = [events[0]] + progress_events
    if progress_boundaries[-1] is not events[-1]:
        progress_boundaries.append(events[-1])
    for a, b in zip(progress_boundaries, progress_boundaries[1:]):
        ta, tb = float(a["t"]), float(b["t"])
        if tb - ta < 15.0:
            continue
        window = [e for e in events if ta <= float(e["t"]) <= tb]
        if len(window) < 2:
            continue
        travelled = sum(dist3(x["position"], y["position"]) for x, y in zip(window, window[1:]))
        net = dist3(window[0]["position"], window[-1]["position"])
        failures = sum(1 for e in window if e.get("success") is False)
        low_net = travelled > 4.0 and net / travelled < 0.25
        if failures >= 2 or low_net:
            stall_windows.append({
                "start_t": ta,
                "end_t": tb,
                "duration": round(tb-ta, 3),
                "travelled": round(travelled, 3),
                "net_displacement": round(net, 3),
                "failed_actions": failures,
                "low_net_displacement": low_net
            })

    failure_events = [e for e in events if e["kind"] == "failure"]
    retry_events = [e for e in events if e["kind"] == "retry"]
    recovery_intervals = []
    for failure in failure_events:
        ft = float(failure["t"])
        next_retry = next((e for e in retry_events if float(e["t"]) >= ft), None)
        next_progress = next((e for e in progress_events if float(e["t"]) >= ft), None)
        if next_retry is not None:
            recovery_intervals.append(float(next_retry["t"]) - ft)
        elif next_progress is not None:
            recovery_intervals.append(float(next_progress["t"]) - ft)

    duration = float(events[-1]["t"]) - float(events[0]["t"])
    completed = any(e["kind"] == "objective_complete" for e in events)

    return {
        "schema": "supracraft-persona-trace-analysis/1",
        "trace_id": doc["trace_id"],
        "world_ref": doc["world_ref"],
        "persona": doc["persona"],
        "objective": doc["objective"],
        "duration_seconds": round(duration, 3),
        "objective_complete": completed,
        "movement": {
            "distance": round(total_distance, 3),
            "displacement": round(displacement, 3),
            "directness": round(directness, 6),
            "detour_ratio": None if detour_ratio is None else round(detour_ratio, 6),
            "backtrack_ratio": round(backtrack_ratio, 6),
            "loop_transition_rate": round(loop_transition_rate, 6),
            "unique_4x4_cells": len(unique_cells)
        },
        "actions": {
            "action_count": len(action_events),
            "failed_action_count": len(failed_actions),
            "unproductive_action_rate": round(unproductive_action_rate, 6)
        },
        "progress": {
            "progress_event_count": len(progress_events),
            "max_progress_gap_seconds": round(max_progress_gap, 3),
            "mean_progress_gap_seconds": round(mean_progress_gap, 3),
            "stall_window_count": len(stall_windows),
            "stall_windows": stall_windows
        },
        "recovery": {
            "failure_count": len(failure_events),
            "retry_count": len(retry_events),
            "mean_failure_to_retry_seconds": (
                None if not recovery_intervals else
                round(sum(recovery_intervals)/len(recovery_intervals), 3)
            ),
            "max_failure_to_retry_seconds": (
                None if not recovery_intervals else round(max(recovery_intervals), 3)
            )
        },
        "interpretation_limits": [
            "High detour/backtracking may be intended in maze, exploration, or search gameplay.",
            "Failure rate does not establish perceived unfairness.",
            "Low event density does not establish boredom.",
            "These metrics require gameplay-profile and persona context before qualitative interpretation."
        ]
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    doc = json.loads(args.trace.read_text(encoding="utf-8"))
    result = analyze(doc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
