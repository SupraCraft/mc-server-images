#!/usr/bin/env python3
"""Resolve metric-family applicability for a declared reference-world profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_profiles(path: Path):
    data=json.loads(path.read_text(encoding="utf-8"))
    profiles={p["profile_id"]:p for p in data["profiles"]}
    assignments={a["world_ref"]:a for a in data.get("profile_assignments",[])}
    return data, profiles, assignments


def resolve(profile, metric_family):
    required=set(profile.get("required_metric_families",[]))
    optional=set(profile.get("optional_metric_families",[]))
    na=set(profile.get("not_applicable_by_default",[]))
    if metric_family in required:
        return "applicable_required"
    if metric_family in optional:
        return "applicable_optional"
    if metric_family in na:
        return "not_applicable"
    return "unknown"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--profiles", type=Path, required=True)
    ap.add_argument("--world-ref", required=True)
    ap.add_argument("--metric-family", action="append", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args=ap.parse_args()

    source, profiles, assignments=load_profiles(args.profiles)
    assignment=assignments.get(args.world_ref)
    if assignment is None:
        raise SystemExit(f"no evaluation profile assignment for {args.world_ref}")
    pid=assignment["primary_profile"]
    profile=profiles[pid]

    observations=[]
    for family in args.metric_family:
        observations.append({
            "metric_family":family,
            "applicability":resolve(profile,family)
        })

    result={
        "schema":"supracraft-worldgen-metric-applicability/1",
        "world_ref":args.world_ref,
        "primary_profile":pid,
        "secondary_profiles":assignment.get("secondary_profiles",[]),
        "evidence_ref":assignment.get("evidence_ref"),
        "observations":observations,
        "rule":source["reporting_rule"]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
