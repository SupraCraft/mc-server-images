#!/usr/bin/env python3
"""Correlate collapsed redstone netlists with positive/gap runtime evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def motifs(doc,name):
    return [x for x in doc.get("motif_candidates",[]) if x.get("template")==name]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--positive-netlist",type=Path,required=True)
    ap.add_argument("--gap-netlist",type=Path,required=True)
    ap.add_argument("--runtime-report",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    positive=load(args.positive_netlist)
    gap=load(args.gap_netlist)
    runtime=load(args.runtime_report)

    positive_tx=motifs(positive,"wire_transmission_path")
    gap_tx=motifs(gap,"wire_transmission_path")
    assert positive_tx,positive["motif_candidates"]
    assert not gap_tx,gap_tx
    assert runtime["fixtures"]["positive"]["actual_actuation"] is True
    assert runtime["fixtures"]["gap"]["actual_actuation"] is False

    report={
        "schema":"supracraft-redstone-netlist-runtime-correlation/1",
        "minecraft_version":runtime["minecraft_version"],
        "positive":{
            "motif":"wire_transmission_path",
            "net_count":positive["net_count"],
            "collapsed_wire_node_count":positive["collapsed_wire_node_count"],
            "horizontal_d4_topology_sha256":
                positive["signatures"]["horizontal_d4_topology_sha256"],
            "functional_netlist_sha256":
                positive["signatures"]["functional_netlist_sha256"],
            "observed_actuation":True,
            "correlation_class":
                "collapsed_net_transmission_candidate_supported_by_runtime",
        },
        "gap_hard_negative":{
            "wire_transmission_motif_count":0,
            "net_count":gap["net_count"],
            "horizontal_d4_topology_sha256":
                gap["signatures"]["horizontal_d4_topology_sha256"],
            "functional_netlist_sha256":
                gap["signatures"]["functional_netlist_sha256"],
            "observed_actuation":False,
            "correlation_class":
                "collapsed_net_disconnection_supported_by_runtime_hard_negative",
        },
        "boundary":"collapsed dust nets simplify representation but do not create causal conduction not present in exact structural/runtime evidence",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
