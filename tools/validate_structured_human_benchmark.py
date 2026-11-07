#!/usr/bin/env python3
"""Validate an external structured human benchmark calibration corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--benchmark",type=Path,required=True)
    ap.add_argument("--projection",type=Path,required=True)
    args=ap.parse_args()

    doc=json.loads(args.benchmark.read_text(encoding="utf-8"))
    proj=json.loads(args.projection.read_text(encoding="utf-8"))
    concepts=set(proj["candidate_concept_ids"])
    errors=[]

    if doc.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not doc.get("benchmark_id"):
        errors.append("missing benchmark_id")
    dims=doc.get("dimensions",[])
    if len(dims) < 2:
        errors.append("structured benchmark needs >=2 dimensions")
    dim_ids=set()
    for dim in dims:
        did=dim.get("id")
        if not did or did in dim_ids:
            errors.append(f"invalid/duplicate dimension id: {did}")
        dim_ids.add(did)
        cid=dim.get("concept_id")
        if cid not in concepts:
            errors.append(f"dimension concept not in CPE projection: {cid}")

    for cohort in doc.get("cohorts",[]):
        if not cohort.get("source_ref"):
            errors.append("cohort missing source_ref")
        entries=cohort.get("entries",[])
        if not entries:
            errors.append(f"cohort {cohort.get('year')} has no entries")
        for entry in entries:
            scores=entry.get("scores",{})
            missing=dim_ids-set(scores)
            if missing:
                errors.append(f"{entry.get('team')}: missing scores {sorted(missing)}")
            extra=set(scores)-dim_ids
            if extra:
                errors.append(f"{entry.get('team')}: unknown scores {sorted(extra)}")
            for key,val in scores.items():
                if not isinstance(val,(int,float)) or not 0 <= val <= 10:
                    errors.append(f"{entry.get('team')} {key}: score out of [0,10]")
        # Human score diversity is necessary for calibration value; a constant
        # dimension provides no ranking/association information.
        for did in dim_ids:
            vals=[e["scores"][did] for e in entries if did in e.get("scores",{})]
            if len(vals) >= 2 and len(set(vals)) == 1:
                errors.append(f"cohort {cohort.get('year')} dimension {did} is constant")

    guards=" ".join(doc.get("guardrails",[])).lower()
    for required in ["final score","rank","freeze","human"]:
        if required not in guards:
            errors.append(f"guardrails do not explicitly address {required!r}")

    if errors:
        for e in errors:
            print("STRUCTURED-HUMAN-BENCHMARK-FAIL:",e)
        return 78

    print(json.dumps({
        "status":"STRUCTURED-HUMAN-BENCHMARK-PASS",
        "benchmark_id":doc["benchmark_id"],
        "dimension_count":len(dims),
        "cohort_count":len(doc.get("cohorts",[])),
        "entry_count":sum(len(c.get("entries",[])) for c in doc.get("cohorts",[])),
        "concept_ids":sorted(d["concept_id"] for d in dims)
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
