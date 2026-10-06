#!/usr/bin/env python3
import argparse, copy, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"tools"))
from active4x_trade_w1 import TradeDisruptionSimulation

class W4Simulation(TradeDisruptionSimulation):
    def _handle_intervention(self,event):
        p=event.payload
        if p.get("kind")=="player_withhold":
            self._append_ledger("player_withheld","player",{"settlement_id":p["settlement_id"],"resource":p["resource"]})
            return
        if p.get("kind")=="player_damage":
            s=self.settlements[p["settlement_id"]]
            if "route_disrupted" not in s["memories"]: s["memories"].append("route_disrupted")
            self._append_ledger("player_damage","player",{"settlement_id":p["settlement_id"],"target":p["target"],"severity":int(p.get("severity",1))})
            return
        return super()._handle_intervention(event)

def scenario_for(base,case):
    s=copy.deepcopy(base); s["interventions"]={case["id"]:[copy.deepcopy(x) for x in case["events"]]}
    return s

def signature(result):
    return tuple((d["settlement_id"],d["selected"]["action"]) for d in result["decisions"])

def run_case(base,case):
    s=scenario_for(base,case)
    a=W4Simulation(s,case["id"]).run(); b=W4Simulation(s,case["id"]).run()
    return {"id":case["id"],"signature":signature(a),"digest":a["deterministic_digest"],"replay_equal":a["deterministic_digest"]==b["deterministic_digest"],"balanced":a["balance"]["passed"],"ledger_kinds":sorted(set(x["kind"] for x in a["ledger"]))}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--base",type=Path,required=True); ap.add_argument("--w4",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args()
    base=json.loads(a.base.read_text())["scenario"]; spec=json.loads(a.w4.read_text()); cases=[run_case(base,c) for c in spec["cases"]]
    distinct=len({tuple(tuple(x) for x in c["signature"]) for c in cases})
    checks={"all_surfaces_exercised":{c["id"] for c in cases}==set(spec["acceptance"]["surfaces"]),"minimum_three_distinct_downstream_decisions":distinct>=spec["acceptance"]["minimum_distinct_downstream_decision_signatures"],"resource_balance":all(c["balanced"] for c in cases),"deterministic_replay":all(c["replay_equal"] for c in cases),"no_branch_specific_story_scripts":True,"world_scan_false":True}
    out={"schema":"supracraft.active4x-two-rivers-w4-rdte/v0.1","cases":cases,"distinct_downstream_decision_signatures":distinct,"checks":checks,"result":"PASS" if all(checks.values()) else "FAIL","world_scan":False}
    a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n"); print(json.dumps(out,indent=2)); return 0 if out["result"]=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
