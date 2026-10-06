#!/usr/bin/env python3
import json, pathlib, sys
d=json.loads(pathlib.Path("spec/minecraft-world-activation-transaction-v1.json").read_text())
errors=[]
if d["ordered_steps"] != ["quiesce","snapshot_current","activate_candidate","resume","health_check"]: errors.append("unsafe transaction ordering")
b=d["transport_boundary"]
if b["docker_socket"] or b["foundry_credentials"] or b["game_semantics"]: errors.append("authority leak")
for key in ("before_activate_candidate","after_activate_candidate_before_health","health_check_failed"):
    if key not in d["failure_policy"]: errors.append("missing failure policy "+key)
required=("transaction_id","prior_release","candidate_release","prior_hash","candidate_hash","steps","outcome")
for key in required:
    if key not in d["receipt_required"]: errors.append("missing receipt field "+key)
if errors:
    print("\n".join("FAIL "+x for x in errors)); sys.exit(1)
print("PASS world activation transaction contract")
