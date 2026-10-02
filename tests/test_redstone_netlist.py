import importlib.util
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



if __name__=="__main__":
    unittest.main()
