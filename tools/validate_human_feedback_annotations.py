#!/usr/bin/env python3
"""Validate public human-feedback annotations without turning them into quality labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

FORBIDDEN_KEYS = {
    "comment_text",
    "raw_comment",
    "overall_quality_label",
    "overall_quality_score",
    "winner",
    "rank",
}
ALLOWED_RELATIONS = {"supports","contradicts","mentions","ambiguous","not_applicable"}
ALLOWED_CERTAINTY = {"strong","adequate","weak","unknown"}

def walk_keys(obj):
    if isinstance(obj, dict):
        for k,v in obj.items():
            yield k
            yield from walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_keys(v)

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--feedback", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    args=ap.parse_args()

    doc=json.loads(args.feedback.read_text(encoding="utf-8"))
    projection=json.loads(args.projection.read_text(encoding="utf-8"))
    allowed=set(projection["candidate_concept_ids"])

    errors=[]
    seen=set()
    if not doc.get("metrics_frozen_ref"):
        errors.append("feedback corpus lacks metrics_frozen_ref")
    if not str(doc.get("artifact_version_ref","")).startswith("sha256:"):
        errors.append("feedback corpus is not bound to exact artifact sha256")

    bad_keys=sorted(set(walk_keys(doc)) & FORBIDDEN_KEYS)
    if bad_keys:
        errors.append("forbidden raw/aggregate judgment keys: "+", ".join(bad_keys))

    for ann in doc.get("annotations",[]):
        aid=ann.get("annotation_id")
        if not aid:
            errors.append("annotation missing id")
            continue
        if aid in seen:
            errors.append(f"duplicate annotation id {aid}")
        seen.add(aid)

        source=ann.get("source",{})
        if not source.get("source_ref"):
            errors.append(f"{aid}: missing source_ref")
        if not source.get("independence_group"):
            errors.append(f"{aid}: missing independence_group")
        if not ann.get("language"):
            errors.append(f"{aid}: missing language")
        if not ann.get("original_text_ref"):
            errors.append(f"{aid}: missing bounded original_text_ref")

        for ca in ann.get("concept_annotations",[]):
            cid=ca.get("concept_id")
            if cid not in allowed:
                errors.append(f"{aid}: concept not in CPE projection: {cid}")
            if ca.get("evidence_relation") not in ALLOWED_RELATIONS:
                errors.append(f"{aid}: invalid evidence_relation")
            if ca.get("certainty") not in ALLOWED_CERTAINTY:
                errors.append(f"{aid}: invalid certainty")

    if errors:
        for e in errors:
            print("HUMAN-FEEDBACK-FAIL:",e)
        return 78

    print(json.dumps({
        "status":"HUMAN-FEEDBACK-ANNOTATIONS-PASS",
        "world_ref":doc.get("world_ref"),
        "artifact_version_ref":doc.get("artifact_version_ref"),
        "metrics_frozen_ref":doc.get("metrics_frozen_ref"),
        "annotation_count":len(seen),
        "concept_ids":sorted({
            ca["concept_id"]
            for ann in doc["annotations"]
            for ca in ann.get("concept_annotations",[])
        }),
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
