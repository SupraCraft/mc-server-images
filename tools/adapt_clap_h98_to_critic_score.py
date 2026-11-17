#!/usr/bin/env python3
"""Fail-closed CLAP raw-logit -> H97 frozen-manifest scorer, never gameplay acceptance.

This adapter does not authenticate the origin of a model receipt; provenance must
be separately admitted through the connected, immutable GHA run and artifact SHA.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from score_critic_interview_h97 import score, MANIFEST_SCHEMA

SCHEMA = "supracraft-h98-clap-temporal-counterfactual/v1"
ADAPTER = "supracraft-h98-clap-logit-adapter/v1"
KEYS = ("first_a", "first_b")
# H97 source-neutral scorer accepts alphabetic labels only: lossless fixed mapping.
SCORER_LABELS = {"first_a": "alpha", "first_b": "beta"}
MODEL_FIELDS = ("model", "revision", "weights_sha256", "fixture_plan_sha256")


def label_from_logits(row):
    if not isinstance(row, dict) or set(row) != set(KEYS):
        raise ValueError("RAW_LOGITS_SCHEMA_REFUSED")
    values = []
    for key in KEYS:
        v = row[key]
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError("RAW_LOGITS_NOT_FINITE")
        values.append(float(v))
    if values[0] == values[1]:
        return None
    return KEYS[0 if values[0] > values[1] else 1]


def adapt(manifest, receipt):
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("FROZEN_MANIFEST_UNTRUSTED")
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("SOURCE_RECEIPT_SCHEMA_UNTRUSTED")
    if receipt.get("status") != "FIRST_FROZEN_REAL_MODEL_OUTPUT_REVIEW_REQUIRED":
        raise ValueError("SOURCE_NOT_FIRST_REAL_INFERENCE")
    if receipt.get("qualified_model") is not False or receipt.get("authentic_minecraft_audio") is not False:
        raise ValueError("SOURCE_SELF_AUTHORITY_REFUSED")
    expected = manifest.get("model_constraints")
    if not isinstance(expected, dict) or any(
        not isinstance(expected.get(k), str) or not expected[k].strip()
        for k in MODEL_FIELDS
    ):
        raise ValueError("MODEL_CONSTRAINTS_REQUIRED")
    for field in MODEL_FIELDS:
        if receipt.get(field) != expected[field]:
            raise ValueError("MODEL_OR_PLAN_PROVENANCE_MISMATCH")
    if len(expected["weights_sha256"]) != 64 or any(
        c not in "0123456789abcdef" for c in expected["weights_sha256"]
    ):
        raise ValueError("MODEL_WEIGHT_DIGEST_INVALID")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 2 <= len(cases) <= 64:
        raise ValueError("MANIFEST_SIZE_UNSAFE")
    by_id = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise ValueError("MANIFEST_CASE_INVALID")
        if item["id"] in by_id:
            raise ValueError("DUPLICATE_MANIFEST_CASE")
        if item.get("allowed_labels") != list(KEYS):
            raise ValueError("H98_LABEL_ORDER_NOT_FROZEN")
        prompts = item.get("captions")
        if not isinstance(prompts, list) or len(prompts) != 2 or any(
            not isinstance(c, str) or len(c.strip()) < 12 for c in prompts
        ):
            raise ValueError("MANIFEST_PROMPT_MISSING")
        by_id[item["id"]] = item
    observations = receipt.get("results")
    if not isinstance(observations, list) or len(observations) != len(cases):
        raise ValueError("RECEIPT_CARDINALITY_MISMATCH")
    seen = set()
    transformed = []
    for item in observations:
        if not isinstance(item, dict):
            raise ValueError("RECEIPT_ITEM_INVALID")
        cid = item.get("id")
        if not isinstance(cid, str) or cid not in by_id or cid in seen:
            raise ValueError("UNEXPECTED_OR_DUPLICATE_RECEIPT_ID")
        seen.add(cid)
        case = by_id[cid]
        if item.get("pair_id") != case.get("pair_id"):
            raise ValueError("COUNTERFACTUAL_PAIR_MISMATCH")
        if item.get("input_sha256") != case.get("sha256"):
            raise ValueError("INPUT_MEDIA_HASH_MISMATCH")
        if item.get("captions") != case.get("captions"):
            raise ValueError("PROMPT_TEXT_MISMATCH")
        a = label_from_logits(item.get("raw_logits_forward_order"))
        b = label_from_logits(item.get("raw_logits_reverse_order"))
        if a != b:
            raise ValueError("PROMPT_ORDER_UNSTABLE_REFUSED")
        # H98 reported top1/correct fields are NOT the scoring source.
        if item.get("predicted_forward_order") != a or item.get("predicted_reverse_order") != b:
            raise ValueError("PREPARSED_CANDIDATE_DISAGREES_WITH_LOGITS")
        # Only exact argmax; a tie is a real abstention and never a correct answer.
        transformed.append({
            "id": cid, "input_sha256": case["sha256"],
            "raw_response": SCORER_LABELS[a] if a is not None else "abstain",
            "parsed_label": SCORER_LABELS[a] if a is not None else None,
        })
    actor = {
        "provider": "local_open_weights",
        "model": expected["model"],
        "version": expected["revision"],
        "family": "CLAP",
    }
    model_input = {
        "schema": "supracraft-critic-raw-output/v1",
        "actor": actor,
        "observations": transformed,
    }
    # This is a semantics-preserving alphabetic encoding for the H97 scorer,
    # not a rewrite of the independent source evidence or the original manifest.
    scorer_manifest = json.loads(json.dumps(manifest))
    for item in scorer_manifest["cases"]:
        if item["expected"] not in SCORER_LABELS:
            raise ValueError("REFERENCE_LABEL_UNEXPECTED")
        item["expected"] = SCORER_LABELS[item["expected"]]
        item["allowed_labels"] = [SCORER_LABELS[k] for k in KEYS]
    report = score(scorer_manifest, model_input)
    report["source_label_to_scorer_label"] = dict(SCORER_LABELS)
    report["adapter_schema"] = ADAPTER
    report["raw_logit_receipt_authenticated"] = False
    report["model_promoted"] = False
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    opts = parser.parse_args()
    try:
        mbytes = Path(opts.manifest).read_bytes()
        rbytes = Path(opts.candidate).read_bytes()
        report = adapt(json.loads(mbytes), json.loads(rbytes))
        report["manifest_sha256"] = hashlib.sha256(mbytes).hexdigest()
        report["candidate_sha256"] = hashlib.sha256(rbytes).hexdigest()
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    encoded = json.dumps(report, sort_keys=True, indent=2) + "\n"
    Path(opts.out).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
