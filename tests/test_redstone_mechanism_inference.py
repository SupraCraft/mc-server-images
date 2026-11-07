import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "infer_redstone_mechanisms",
    ROOT/"tools"/"infer_redstone_mechanisms.py",
)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def node(nid,pos,block,roles=None,properties=None):
    return {
        "node_id":nid,
        "position":list(pos),
        "block":block,
        "roles":roles or [],
        "properties":properties or {},
    }


class RedstoneMechanismInferenceTests(unittest.TestCase):
    def test_connected_path_infers_transmission_delay_and_command_chain(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                node("0,0,0",(0,0,0),"minecraft:lever",["sensor_input"]),
                node("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                node("2,0,0",(2,0,0),"minecraft:repeater",["signal_transport","timer_clock"]),
                node("3,0,0",(3,0,0),"minecraft:command_block",["actuator"]),
            ],
            "edges":[
                {"source":"0,0,0","target":"1,0,0","edge_type":"dust_connection","certainty":"strong"},
                {"source":"1,0,0","target":"2,0,0","edge_type":"oriented_rear_input","certainty":"strong"},
                {"source":"2,0,0","target":"3,0,0","edge_type":"oriented_front_output","certainty":"strong"},
            ],
        }
        doc=mod.infer(graph)
        self.assertEqual(doc["component_count"],1)
        comp=doc["components"][0]
        names={x["mechanism"] for x in comp["mechanism_candidates"]}
        self.assertIn("transmission_path",names)
        self.assertIn("buffered_delay_line",names)
        self.assertIn("command_actuation_chain",names)
        self.assertEqual(comp["runtime_validation"]["status"],"not_yet_correlated")

    def test_one_block_gap_splits_topology_and_does_not_infer_cross_gap_path(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                node("0,0,0",(0,0,0),"minecraft:redstone_block"),
                node("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
                node("3,0,0",(3,0,0),"minecraft:redstone_wire",["signal_transport"]),
                node("4,0,0",(4,0,0),"minecraft:command_block",["actuator"]),
            ],
            "edges":[
                {"source":"0,0,0","target":"1,0,0","edge_type":"dust_connection","certainty":"strong"},
                {"source":"3,0,0","target":"4,0,0","edge_type":"dust_connection","certainty":"strong"},
            ],
        }
        doc=mod.infer(graph)
        self.assertEqual(doc["component_count"],2)
        source_component=next(
            c for c in doc["components"]
            if "0,0,0" in {n["node_id"] for n in c["nodes"]}
        )
        self.assertEqual(source_component["mechanism_candidates"],[])

    def test_cycle_is_candidate_not_claimed_clock(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                node("0,0,0",(0,0,0),"minecraft:repeater",["signal_transport","timer_clock"]),
                node("1,0,0",(1,0,0),"minecraft:redstone_wire",["signal_transport"]),
            ],
            "edges":[
                {"source":"0,0,0","target":"1,0,0","edge_type":"oriented_front_output","certainty":"strong"},
                {"source":"1,0,0","target":"0,0,0","edge_type":"oriented_rear_input","certainty":"strong"},
            ],
        }
        comp=mod.infer(graph)["components"][0]
        candidates={x["mechanism"]:x for x in comp["mechanism_candidates"]}
        self.assertIn("oscillator_or_state_loop",candidates)
        self.assertEqual(
            candidates["oscillator_or_state_loop"]["confidence"],
            "structural_candidate_only",
        )
        self.assertNotIn("clock",candidates)

    def test_dot_contains_only_structural_labels_not_authored_command_text(self):
        graph={
            "schema":"supracraft-modern-causal-machinery/1",
            "nodes":[
                node("0,0,0",(0,0,0),"minecraft:command_block",["actuator"]),
            ],
            "edges":[],
        }
        dot=mod.emit_dot(mod.infer(graph))
        self.assertIn("command_block",dot)
        self.assertNotIn("Command:",dot)
        self.assertNotIn("tellraw",dot)


    def test_topology_signature_is_translation_invariant(self):
        def make(offset):
            ox,oy,oz=offset
            a=f"{ox},{oy},{oz}"
            b=f"{ox+1},{oy},{oz}"
            return {
                "schema":"supracraft-modern-causal-machinery/1",
                "nodes":[
                    node(a,(ox,oy,oz),"minecraft:redstone_block",["power_source"]),
                    node(b,(ox+1,oy,oz),"minecraft:redstone_wire",["signal_transport"]),
                ],
                "edges":[],
            }
        first=mod.infer(make((0,0,0)))["components"][0]
        moved=mod.infer(make((40,12,-90)))["components"][0]
        self.assertEqual(first["topology_sha256"],moved["topology_sha256"])
        self.assertEqual(
            first["functional_signature_sha256"],
            moved["functional_signature_sha256"],
        )
        self.assertEqual(
            first["signature_normalization"],
            "translation_invariant_rotation_sensitive",
        )



if __name__=="__main__":
    unittest.main()
