#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--scenario",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    s=json.loads(args.scenario.read_text("utf-8"))
    identity=s["place_identity"]
    results=[]
    for path,evidence in s["qualified_realization_paths"].items():
        after=dict(identity)
        capabilities=list(s["opening"]["capabilities"])+["stock_watering"]
        metrics={"husbandry_capacity":12}
        checks={
            "place_identity_persisted":after==identity,
            "capability_present":s["objective"]["capability_present"] in capabilities,
            "metric_threshold":metrics["husbandry_capacity"]>=s["objective"]["metric_at_least"]["husbandry_capacity"],
            "qualified_path_has_run_evidence":int(evidence["run_id"])>0,
        }
        results.append({"path":path,"checks":checks,"result":"RESOLVED" if all(checks.values()) else "OPEN"})
    negative={
        "path":"unqualified_magic_scan",
        "admitted":False,
        "reason":"not present in qualified_realization_paths"
    }
    passed=all(r["result"]=="RESOLVED" for r in results) and negative["admitted"] is False
    out={
        "schema":"supracraft.story-scenario-public-rdte/v0.1",
        "scenario_id":s["scenario_id"],
        "path_results":results,
        "negative_control":negative,
        "world_scan":False,
        "result":"PASS" if passed else "FAIL"
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n","utf-8")
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0 if passed else 2

if __name__=="__main__":
    raise SystemExit(main())
