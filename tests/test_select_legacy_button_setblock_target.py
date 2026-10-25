"""Source-free adversarial CORE button->setblock target selection tests."""
import copy
import json
import unittest

from tools.select_legacy_button_setblock_target import (
    _source_candidates, qualify, _other_writer_class,
)


def n(family, pos, **kw):
    return dict(node_id=",".join(map(str, pos)), position=list(pos), family=family, **kw)


def graph():
    button = n("wooden_button", (0, 64, 0),
               metadata_semantics={"support_vector": [1, 0, 0]})
    command = n("command_block", (1, 64, 0),
                command={"verb": "setblock", "sha256": "a" * 64})
    return {"schema": "supracraft-legacy-causal-machinery/1",
            "nodes": [button, command],
            "edges": {
                "direct_redstone_edges": [{
                    "source": button["node_id"], "target": command["node_id"],
                    "edge_type": "legacy_button_attached_support_power"}],
                "command_world_targets": [{
                    "source": command["node_id"], "target_position": [20, 65, 20],
                    "target_kind": "point", "edge_type": "command_world_target"}]}}


def obs(valid=True):
    return {"1,64,0": {"sha_matches": valid, "syntax_target_matches": valid,
                       "saved": (1, 0)}}


class ButtonTargetQualification(unittest.TestCase):
    def result(self, g=None, o=None):
        g = g or graph()
        return qualify(g, _source_candidates(g), obs() if o is None else o)

    def test_valid_single_candidate_is_source_only(self):
        o = self.result()
        self.assertEqual(o["selected_trial_target_count"], 1)
        self.assertEqual(o["original_native_activation"], "NOT_RUN")
        self.assertFalse(o["gameplay_promoted"])
        text = json.dumps(o)
        for secret in ("1,64,0", "20,65,20", '"node_id"', '"position"',
                       '"command"', "aaaaaaaaaaaaaaaa"):
            self.assertNotIn(secret, text)

    def test_wrong_button_facing_is_not_a_candidate(self):
        g = graph()
        g["nodes"][0]["metadata_semantics"]["support_vector"] = [-1, 0, 0]
        self.assertEqual(_source_candidates(g), [])

    def test_forged_edge_is_not_a_candidate(self):
        g = graph()
        g["edges"]["direct_redstone_edges"][0]["edge_type"] = "physical_adjacency_candidate"
        self.assertEqual(_source_candidates(g), [])

    def test_duplicate_projection_yields_one_candidate(self):
        g = graph()
        g["edges"]["direct_redstone_edges"].append(
            copy.deepcopy(g["edges"]["direct_redstone_edges"][0]))
        self.assertEqual(len(_source_candidates(g)), 1)

    def test_unresolved_coordinate_fails_closed(self):
        g = graph()
        g["edges"]["command_world_targets"][0]["target_position"] = [20.3, 65, 20]
        self.assertEqual(self.result(g)["source_selection_disposition"], "BUTTON_TARGET_UNRESOLVED")

    def test_extra_target_edge_fails_closed(self):
        g = graph()
        g["edges"]["command_world_targets"].append(
            copy.deepcopy(g["edges"]["command_world_targets"][0]))
        self.assertEqual(self.result(g)["selected_trial_target_count"], 0)

    def test_original_tile_entity_sha_mismatch(self):
        o = self.result(o=obs(False))
        self.assertEqual(o["selection_rejection_reason_counts"],
                         {"ORIGINAL_TILE_ENTITY_COMMAND_SHA_MISMATCH": 1})

    def test_no_saved_target_state_is_not_proof(self):
        o = obs()
        o["1,64,0"]["saved"] = None
        self.assertEqual(self.result(o=o)["selected_trial_target_count"], 0)

    def test_ambiguity_from_second_setblock_writer(self):
        g = graph()
        g["nodes"].append(n("command_block", (4, 64, 0),
                            command={"verb": "setblock", "sha256": "b" * 64}))
        g["edges"]["command_world_targets"].append({
            "source": "4,64,0", "target_position": [20, 65, 20],
            "target_kind": "point", "edge_type": "command_world_target"})
        self.assertEqual(_other_writer_class(g, _source_candidates(g)[0]), "OTHER_POINT_WRITER")

    def test_spatial_overlap_rejects_independent_fill_writer(self):
        g = graph()
        g["nodes"].append(n("command_block", (4, 64, 0),
                            command={"verb": "fill", "sha256": "b" * 64}))
        g["edges"]["command_world_targets"] += [
            {"source": "4,64,0", "target_kind": kind,
             "target_position": pos, "edge_type": "command_world_target"}
            for kind, pos in (("region_start", [19, 64, 19]),
                              ("region_end", [21, 66, 21]))]
        self.assertEqual(_other_writer_class(g, _source_candidates(g)[0]),
                         "OTHER_BOUNDED_SPATIAL_WRITER")

    def test_duplicate_source_node_identity_fails_closed(self):
        g = graph()
        g["nodes"].append(copy.deepcopy(g["nodes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _source_candidates(g)

    def test_original_sensor_target_forbidden(self):
        g = graph()
        g["edges"]["command_world_targets"][0]["target_position"] = [0, 64, 0]
        self.assertEqual(self.result(g)["selected_trial_target_count"], 0)


if __name__ == "__main__":
    unittest.main()
