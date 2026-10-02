import importlib.util
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "build_redstone_netlist",
    ROOT/"tools"/"build_redstone_netlist.py",
)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def n(nid,p,block,roles=None,props=None):
    return {
        "node_id":nid,
        "position":list(p),
        "block":block,
        "roles":roles or [],
        "properties":props or {},
    }


def edge(a,b,kind="dust_connection",certainty="strong"):
    return {
        "source":a,
        "target":b,
        "edge_type":kind,
        "certainty":certainty,
    }


class RedstoneNetlistTests(unittest.TestCase):
    def test_three_dust_blocks_collapse_to_one_net_and_transmission_motif(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("0,0,0",(0,0,0),"minecraft:redstone_block",["power_source"]),
                n("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("2,0,0",(2,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("3,0,0",(3,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("4,0,0",(4,0,0),"minecraft:command_block",["actuator","orchestrator"]),
            ],
            "edges":[
                edge("1,0,0","2,0,0"),
                edge("2,0,0","1,0,0"),
                edge("2,0,0","3,0,0"),
                edge("3,0,0","2,0,0"),
                edge("3,0,0","4,0,0"),
            ],
        }
        doc,_=mod.build(graph)
        self.assertEqual(doc["net_count"],1)
        self.assertEqual(doc["nets"][0]["wire_node_count"],3)
        self.assertIn(
            "wire_transmission_path",
            {x["template"] for x in doc["motif_candidates"]},
        )
        port_kinds={
            (p["component_id"],p["kind"])
            for p in doc["nets"][0]["ports"]
        }
        self.assertIn(("0,0,0","output"),port_kinds)
        self.assertIn(("4,0,0","input"),port_kinds)

    def test_air_gap_produces_two_nets_and_no_cross_gap_transmission(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("0,0,0",(0,0,0),"minecraft:redstone_block",["power_source"]),
                n("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("3,0,0",(3,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("4,0,0",(4,0,0),"minecraft:command_block",["actuator"]),
            ],
            "edges":[
                edge("3,0,0","4,0,0"),
            ],
        }
        doc,_=mod.build(graph)
        self.assertEqual(doc["net_count"],2)
        self.assertNotIn(
            "wire_transmission_path",
            {x["template"] for x in doc["motif_candidates"]},
        )

    def test_repeater_has_distinct_input_output_nets_and_delay_motif(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("0,0,0",(0,0,0),"minecraft:redstone_block",["power_source"]),
                n("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("2,0,0",(2,0,0),"minecraft:repeater",["signal_transport","timer_clock"],
                  {"facing":"west","delay":"3","locked":"false","powered":"false"}),
                n("3,0,0",(3,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("4,0,0",(4,0,0),"minecraft:command_block",["actuator"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        self.assertEqual(doc["net_count"],2)
        repeater=next(c for c in doc["components"] if c["primitive"]=="buffer_delay")
        self.assertEqual(
            {(p["kind"],p["net_id"]) for p in repeater["ports"]},
            {("input","net::1"),("output","net::2")},
        )
        motifs=[x for x in doc["motif_candidates"] if x["template"]=="repeater_delay_line"]
        self.assertEqual(len(motifs),1)
        self.assertEqual(motifs[0]["configured_delay"],"3")

    def test_floor_torch_is_inverter_candidate_not_accepted_not_gate(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("1,1,0",(1,1,0),"minecraft:redstone_torch",["signal_transport","logic_gate"],
                  {"lit":"true"}),
                n("2,1,0",(2,1,0),"minecraft:redstone_wire",["signal_transport"]),
                n("3,1,0",(3,1,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        motifs=[x for x in doc["motif_candidates"] if x["template"]=="not_gate"]
        self.assertEqual(len(motifs),1)
        self.assertEqual(motifs[0]["confidence"],"structural_candidate_only")
        self.assertIs(motifs[0]["input_support_resolved"],False)
        self.assertIn("truth",motifs[0]["required_runtime_contract"].lower())

    def test_floor_torch_support_resolves_input_dust_net_and_source(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("source",(-1,100,0),"minecraft:redstone_block",["power_source"]),
                n("input",(0,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("torch",(1,101,0),"minecraft:redstone_torch",["signal_transport","logic_gate"],
                  {"lit":"false"}),
                n("output",(2,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(3,101,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        motif=next(x for x in doc["motif_candidates"] if x["template"]=="not_gate")
        self.assertIs(motif["input_support_resolved"],True)
        self.assertEqual(motif["input_source_component_ids"],["source"])
        self.assertEqual(len(motif["input_support_net_ids"]),1)
        torch=next(x for x in doc["components"] if x["component_id"]=="torch")
        support=next(p for p in torch["ports"] if p["kind"]=="input_support")
        self.assertEqual(support["support_position"],[1,100,0])
        self.assertEqual(support["peer_component_ids"],["source"])
        self.assertEqual(support["support_net_ids"],motif["input_support_net_ids"])
        self.assertEqual(support["basis"],"topology_support_wire_net_candidate")


    def test_two_sources_shared_net_is_or_candidate_pending_runtime_truth_table(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a",(-1,0,-1),"minecraft:redstone_block",["power_source"]),
                n("aw",(0,0,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("aj",(1,0,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("b",(-1,0,1),"minecraft:redstone_block",["power_source"]),
                n("bw",(0,0,1),"minecraft:redstone_wire",["signal_transport"]),
                n("bj",(1,0,1),"minecraft:redstone_wire",["signal_transport"]),
                n("j",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("out",(2,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(3,0,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[
                edge("aw","aj"),edge("aj","j"),edge("j","bj"),
                edge("bj","bw"),edge("j","out"),
            ],
        }
        doc,_=mod.build(graph)
        rows=[x for x in doc["motif_candidates"] if x["template"]=="or_gate"]
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["confidence"],"structural_candidate_only")
        self.assertEqual(row["input_source_component_ids"],["a","b"])
        self.assertEqual(row["output_sink_component_ids"],["lamp"])
        self.assertIn("truth table",row["required_runtime_contract"].lower())

    def test_single_source_shared_net_is_not_or_candidate(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a",(0,0,0),"minecraft:redstone_block",["power_source"]),
                n("w",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(2,0,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        self.assertFalse(any(
            x["template"]=="or_gate" for x in doc["motif_candidates"]
        ))


    def test_two_source_shared_net_driving_inverter_is_nor_candidate_only(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("sa",(-1,100,-1),"minecraft:redstone_block",["power_source"]),
                n("aw",(0,100,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("aj",(1,100,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("sb",(-1,100,1),"minecraft:redstone_block",["power_source"]),
                n("bw",(0,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("bj",(1,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("j",(1,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("inv",(2,101,0),"minecraft:redstone_torch",
                  ["signal_transport","logic_gate"],{"lit":"false"}),
                n("out",(3,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(4,101,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[
                edge("aw","aj"),edge("aj","j"),edge("j","bj"),
                edge("bj","bw"),
            ],
        }
        doc,_=mod.build(graph)
        rows=[x for x in doc["motif_candidates"] if x["template"]=="nor_gate"]
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["confidence"],"structural_candidate_only")
        self.assertEqual(row["input_source_component_ids"],["sa","sb"])
        self.assertEqual(row["inverter_component_id"],"inv")
        self.assertEqual(row["output_sink_component_ids"],["lamp"])
        self.assertIn("truth table",row["required_runtime_contract"].lower())

    def test_single_source_inverter_is_not_nor_candidate(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("sa",(-1,100,0),"minecraft:redstone_block",["power_source"]),
                n("w",(0,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("inv",(1,101,0),"minecraft:redstone_torch",
                  ["signal_transport","logic_gate"],{"lit":"false"}),
                n("out",(2,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(3,101,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        self.assertFalse(any(
            x["template"]=="nor_gate" for x in doc["motif_candidates"]
        ))

    def test_reference_catalog_keeps_unqualified_families_candidate_only(self):
        catalog=json.loads(
            (ROOT/"bench"/"worldgen"/"observability"/
             "redstone-mechanism-reference-catalog-v0.json").read_text()
        )
        by_id={x["id"]:x for x in catalog["entries"]}
        self.assertEqual(by_id["wire_transmission_path"]["status"],"qualified_template")
        self.assertEqual(by_id["repeater_delay_line"]["status"],"qualified_template")
        self.assertEqual(by_id["not_gate"]["status"],"qualified_template")
        self.assertEqual(by_id["or_gate"]["status"],"qualified_template")
        self.assertEqual(by_id["and_gate"]["status"],"qualified_template")
        self.assertEqual(by_id["nor_gate"]["status"],"reference_candidate_only")
        self.assertEqual(by_id["rs_latch"]["status"],"qualified_template")
        self.assertEqual(by_id["piston_clock"]["status"],"reference_candidate_only")

    def test_d4_and_functional_signatures_match_rotated_equivalent(self):
        first={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a",(0,0,0),"minecraft:redstone_block",["power_source"]),
                n("b",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                n("c",(2,0,0),"minecraft:command_block",["actuator"],{"facing":"east"}),
            ],
            "edges":[],
        }
        rotated={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("x",(20,5,-30),"minecraft:redstone_block",["power_source"]),
                n("y",(20,5,-29),"minecraft:redstone_wire",["signal_transport"]),
                n("z",(20,5,-28),"minecraft:command_block",["actuator"],{"facing":"south"}),
            ],
            "edges":[],
        }
        a,_=mod.build(first)
        b,_=mod.build(rotated)
        self.assertEqual(
            a["signatures"]["horizontal_d4_topology_sha256"],
            b["signatures"]["horizontal_d4_topology_sha256"],
        )
        self.assertEqual(
            a["signatures"]["functional_netlist_sha256"],
            b["signatures"]["functional_netlist_sha256"],
        )

    def test_layered_view_preserves_exact_positions(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a",(3,90,4),"minecraft:redstone_wire",["signal_transport"]),
                n("b",(3,91,4),"minecraft:repeater",["signal_transport"],{"facing":"north"}),
            ],
            "edges":[],
        }
        _,layers=mod.build(graph)
        self.assertEqual([x["y"] for x in layers["layers"]],[90,91])
        self.assertEqual(layers["layers"][0]["cells"][0]["position"],[3,90,4])


    def test_floor_torch_support_candidate_resolves_adjacent_lever(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("lever",(0,100,0),"minecraft:lever",["sensor_input","state_memory"],
                  {"face":"wall","facing":"west","powered":"false"}),
                n("torch",(1,101,0),"minecraft:redstone_torch",["signal_transport","logic_gate"],
                  {"lit":"true"}),
                n("wire",(2,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(3,101,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[],
        }
        doc,_=mod.build(graph)
        motif=next(x for x in doc["motif_candidates"] if x["template"]=="not_gate")
        self.assertIs(motif["input_support_resolved"],True)
        self.assertEqual(motif["input_source_component_ids"],["lever"])
        torch=next(x for x in doc["components"] if x["component_id"]=="torch")
        support=next(p for p in torch["ports"] if p["kind"]=="input_support")
        self.assertEqual(support["support_position"],[1,100,0])
        self.assertEqual(support["peer_component_ids"],["lever"])
        self.assertEqual(support["certainty"],"topology_candidate")



    def test_three_inverter_de_morgan_shape_is_and_candidate_only(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("sa",(-1,100,-1),"minecraft:redstone_block",["power_source"]),
                n("aw",(0,100,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("ia",(1,101,-1),"minecraft:redstone_torch",["signal_transport","logic_gate"],{"lit":"false"}),
                n("ib",(1,101,1),"minecraft:redstone_torch",["signal_transport","logic_gate"],{"lit":"false"}),
                n("bw",(0,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("sb",(-1,100,1),"minecraft:redstone_block",["power_source"]),
                n("m1",(2,101,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("mj",(2,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("m2",(2,101,1),"minecraft:redstone_wire",["signal_transport"]),
                n("final",(3,102,0),"minecraft:redstone_torch",["signal_transport","logic_gate"],{"lit":"true"}),
                n("out",(4,102,0),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(5,102,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[
                edge("m1","mj"),edge("mj","m1"),
                edge("mj","m2"),edge("m2","mj"),
            ],
        }
        doc,_=mod.build(graph)
        rows=[x for x in doc["motif_candidates"] if x["template"]=="and_gate"]
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["confidence"],"structural_candidate_only")
        self.assertEqual(row["input_source_component_ids"],["sa","sb"])
        self.assertEqual(row["input_inverter_component_ids"],["ia","ib"])
        self.assertEqual(row["final_inverter_component_id"],"final")
        self.assertEqual(row["output_sink_component_ids"],["lamp"])
        self.assertIn("truth table",row["required_runtime_contract"].lower())

    def test_two_inverter_shared_net_without_final_inverter_is_not_and(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("sa",(-1,100,-1),"minecraft:redstone_block",["power_source"]),
                n("aw",(0,100,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("ia",(1,101,-1),"minecraft:redstone_torch",["signal_transport","logic_gate"],{"lit":"false"}),
                n("ib",(1,101,1),"minecraft:redstone_torch",["signal_transport","logic_gate"],{"lit":"false"}),
                n("bw",(0,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("sb",(-1,100,1),"minecraft:redstone_block",["power_source"]),
                n("m1",(2,101,-1),"minecraft:redstone_wire",["signal_transport"]),
                n("mj",(2,101,0),"minecraft:redstone_wire",["signal_transport"]),
                n("m2",(2,101,1),"minecraft:redstone_wire",["signal_transport"]),
                n("lamp",(3,101,0),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[
                edge("m1","mj"),edge("mj","m1"),
                edge("mj","m2"),edge("m2","mj"),
            ],
        }
        doc,_=mod.build(graph)
        self.assertFalse(any(
            x["template"]=="and_gate" for x in doc["motif_candidates"]
        ))


    def test_cross_coupled_two_inverter_shape_is_rs_latch_candidate_only(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a_support",(0,100,0),"minecraft:stone"),
                n("a_torch",(1,100,0),"minecraft:redstone_wall_torch",
                  ["signal_transport","logic_gate"],{"facing":"east","lit":"true"}),
                n("a1",(2,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("a2",(3,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("a3",(4,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("a4",(4,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("b_support",(4,100,2),"minecraft:stone"),
                n("b_torch",(3,100,2),"minecraft:redstone_wall_torch",
                  ["signal_transport","logic_gate"],{"facing":"west","lit":"false"}),
                n("b1",(2,100,2),"minecraft:redstone_wire",["signal_transport"]),
                n("b2",(1,100,2),"minecraft:redstone_wire",["signal_transport"]),
                n("b3",(0,100,2),"minecraft:redstone_wire",["signal_transport"]),
                n("b4",(0,100,1),"minecraft:redstone_wire",["signal_transport"]),
                n("q_lamp",(3,100,-1),"minecraft:redstone_lamp",["presentation_feedback"]),
                n("qb_lamp",(1,100,3),"minecraft:redstone_lamp",["presentation_feedback"]),
            ],
            "edges":[
                edge("a1","a2"),edge("a2","a1"),edge("a2","a3"),edge("a3","a2"),
                edge("a3","a4"),edge("a4","a3"),
                edge("b1","b2"),edge("b2","b1"),edge("b2","b3"),edge("b3","b2"),
                edge("b3","b4"),edge("b4","b3"),
            ],
        }
        doc,_=mod.build(graph)
        rows=[x for x in doc["motif_candidates"] if x["template"]=="rs_latch"]
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row["confidence"],"structural_candidate_only")
        self.assertEqual(row["inverter_component_ids"],["a_torch","b_torch"])
        self.assertEqual(len(row["feedback_a_to_b_net_ids"]),1)
        self.assertEqual(len(row["feedback_b_to_a_net_ids"]),1)
        self.assertIn("retained state",row["required_runtime_contract"].lower())

    def test_two_inverters_without_closed_cross_coupling_are_not_rs_latch(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                n("a_torch",(1,100,0),"minecraft:redstone_wall_torch",
                  ["signal_transport","logic_gate"],{"facing":"east","lit":"true"}),
                n("a1",(2,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("a2",(3,100,0),"minecraft:redstone_wire",["signal_transport"]),
                n("b_torch",(3,100,2),"minecraft:redstone_wall_torch",
                  ["signal_transport","logic_gate"],{"facing":"west","lit":"false"}),
                n("b1",(2,100,2),"minecraft:redstone_wire",["signal_transport"]),
            ],
            "edges":[edge("a1","a2"),edge("a2","a1")],
        }
        doc,_=mod.build(graph)
        self.assertFalse(any(
            x["template"]=="rs_latch" for x in doc["motif_candidates"]
        ))


if __name__=="__main__":
    unittest.main()
