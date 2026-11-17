#!/usr/bin/env python3
"""Strict source-neutral critic interview scoring, not model promotion."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

MANIFEST_SCHEMA = "supracraft-critic-frozen-manifest/v1"
OUTPUT_SCHEMA = "supracraft-critic-raw-output/v1"
RESULT_SCHEMA = "supracraft-critic-falsification-score/v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def score(manifest, output):
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("MANIFEST_SCHEMA_UNTRUSTED")
    if output.get("schema") != OUTPUT_SCHEMA:
        raise ValueError("RAW_OUTPUT_SCHEMA_UNTRUSTED")
    if not isinstance(manifest.get("campaign"), str) or not manifest["campaign"].strip():
        raise ValueError("CAMPAIGN_MISSING")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 2 <= len(cases) <= 64:
        raise ValueError("CASE_COUNT_UNBOUNDED")
    by_id = {}
    by_pair = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("CASE_INVALID")
        cid, digest, label, allowed, pair = (
            case.get("id"), case.get("sha256"), case.get("expected"),
            case.get("allowed_labels"), case.get("pair_id"),
        )
        if not isinstance(cid, str) or not re.fullmatch(r"[a-zA-Z][\w.-]{0,63}", cid):
            raise ValueError("CASE_ID_INVALID")
        if cid in by_id:
            raise ValueError("DUPLICATE_CASE_ID")
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise ValueError("CASE_HASH_INVALID")
        if not isinstance(allowed, list) or not 2 <= len(allowed) <= 8:
            raise ValueError("LABEL_SET_INVALID")
        if any(not isinstance(s, str) or not re.fullmatch(r"[a-z]{2,24}", s) for s in allowed):
            raise ValueError("LABEL_SET_INVALID")
        if len(set(allowed)) != len(allowed) or label not in allowed:
            raise ValueError("LABEL_SET_INVALID")
        if not isinstance(pair, str) or not re.fullmatch(r"[a-zA-Z][\w.-]{0,63}", pair):
            raise ValueError("PAIR_INVALID")
        by_id[cid] = case
        by_pair.setdefault(pair, []).append(case)
    for pair, members in by_pair.items():
        if len(members) != 2:
            raise ValueError("PAIR_REQUIRES_TWO_CASES")
        a, b = members
        if a["expected"] == b["expected"] or a["sha256"] == b["sha256"]:
            raise ValueError("PAIR_IS_NOT_COUNTERFACTUAL")
        if a["allowed_labels"] != b["allowed_labels"]:
            raise ValueError("PAIR_LABEL_SETS_DIFFER")

    actor = output.get("actor")
    if not isinstance(actor, dict) or any(
        not isinstance(actor.get(k), str) or not actor[k].strip()
        for k in ("provider", "model", "family", "version")
    ):
        raise ValueError("ACTOR_IDENTITY_MISSING")
    observations = output.get("observations")
    if not isinstance(observations, list) or len(observations) != len(cases):
        raise ValueError("OBSERVATION_CARDINALITY")
    seen = set()
    receipts = []
    for obs in observations:
        if not isinstance(obs, dict):
            raise ValueError("OBSERVATION_INVALID")
        cid = obs.get("id")
        if not isinstance(cid, str) or cid not in by_id:
            raise ValueError("UNDECLARED_OBSERVATION")
        if cid in seen:
            raise ValueError("DUPLICATE_OBSERVATION")
        seen.add(cid)
        case = by_id[cid]
        if obs.get("input_sha256") != case["sha256"]:
            raise ValueError("SOURCE_HASH_MISMATCH")
        raw = obs.get("raw_response")
        if not isinstance(raw, str) or not 1 <= len(raw) <= 512:
            raise ValueError("RAW_RESPONSE_INVALID")
        # No unsourced AI parser; exact one-token normalized responses only.
        decoded = raw.strip().lower().rstrip(".")
        if decoded == "abstain":
            predicted = None
        elif decoded in case["allowed_labels"]:
            predicted = decoded
        else:
            predicted = None  # Invalid/ambiguous free text is not a correct answer.
        if obs.get("parsed_label") != predicted:
            raise ValueError("PARSED_LABEL_DISAGREES_WITH_RAW")
        receipts.append({
            "id": cid, "pair_id": case["pair_id"], "expected": case["expected"],
            "predicted": predicted, "correct": predicted == case["expected"],
            "abstained": predicted is None,
            "input_sha256": case["sha256"],
        })
    receipts.sort(key=lambda r: r["id"])
    by_receipt = {r["id"]: r for r in receipts}
    paired = []
    for key in sorted(by_pair):
        a, b = sorted(by_pair[key], key=lambda c: c["id"])
        ra, rb = by_receipt[a["id"]], by_receipt[b["id"]]
        paired.append({
            "pair_id": key, "both_correct": ra["correct"] and rb["correct"],
            "changed_prediction": ra["predicted"] != rb["predicted"],
            "any_abstained": ra["abstained"] or rb["abstained"],
        })
    return {
        "schema": RESULT_SCHEMA,
        "campaign": manifest["campaign"],
        "model": actor,
        "correct": sum(r["correct"] for r in receipts),
        "total": len(receipts),
        "abstentions_or_invalid": sum(r["abstained"] for r in receipts),
        "counterfactual_pairs_correct": sum(p["both_correct"] for p in paired),
        "counterfactual_pairs_total": len(paired),
        "results": receipts,
        "pairs": paired,
        "status": "REVIEW_REQUIRED_NO_MODEL_PROMOTION",
        "qualified_critic": False,
        "minecraft_gameplay_verified": False,
        "human_accepted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--out", required=True)
    opts = parser.parse_args()
    try:
        manifest_raw = Path(opts.manifest).read_bytes()
        candidate_raw = Path(opts.candidate).read_bytes()
        result = score(json.loads(manifest_raw), json.loads(candidate_raw))
        result["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
        result["candidate_sha256"] = hashlib.sha256(candidate_raw).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    data = json.dumps(result, sort_keys=True, indent=2) + "\n"
    Path(opts.out).write_text(data, encoding="utf-8")
    print(data, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
