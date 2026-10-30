"""Source-free tests: clone mode custody fingerprint and egress fail closed."""
import hashlib
import json
import unittest

from test_inspect_legacy_piston_snapshot_inputs import graph_fixture
from tools.rank_legacy_electromechanical_witnesses import rank
from tools.inspect_legacy_piston_clone_modes import classify_modes


def fixture(mask="", mode=""):
    graph=graph_fixture()
    cid="50,70,50"
    raw="clone 100 70 100 102 70 100 0 71 0"
    if mask:
        raw+=" "+mask
    if mode:
        raw+=" "+mode
    graph["nodes"].append({
        "node_id":cid,"position":[50,70,50],"family":"command_block",
        "command":{"verb":"clone","sha256":hashlib.sha256(raw.encode()).hexdigest()},
    })
    graph["edges"]["command_world_targets"]=[
        {"source":cid,"target_kind":"source_start","target_position":[100,70,100]},
        {"source":cid,"target_kind":"source_end","target_position":[102,70,100]},
        {"source":cid,"target_kind":"destination","target_position":[0,71,0]},
    ]
    signature=rank(graph)["signatures"][0]["signature_sha256"]
    return graph,signature,{cid:raw}


class OriginalCloneModeTests(unittest.TestCase):
    def test_default_source_clone_mode_is_replace_normal_static_only(self):
        g,sig,source=fixture()
        out=classify_modes(g,sig,source)
        self.assertEqual(out["source_mask_mode_counts"],{"replace":1})
        self.assertEqual(out["source_clone_mode_counts"],{"normal":1})
        self.assertEqual(out["candidate_clone_command_count"],1)
        self.assertEqual(out["command_execution"],"NOT_OBSERVED")
        self.assertFalse(out["gameplay_promoted"])

    def test_masked_force_classification_keeps_mode_distinct(self):
        g,sig,source=fixture("masked","force")
        out=classify_modes(g,sig,source)
        self.assertEqual(out["source_mask_mode_counts"],{"masked":1})
        self.assertEqual(out["source_clone_mode_counts"],{"force":1})

    def test_filtered_move_remains_semantically_unproven(self):
        g,sig,source=fixture("filtered","move")
        out=classify_modes(g,sig,source)
        self.assertEqual(out["source_mask_mode_counts"],{"filtered":1})
        self.assertEqual(out["source_clone_mode_counts"],{"move":1})
        self.assertEqual(out["actual_target_write"],"NOT_OBSERVED")

    def test_exact_command_source_sha_prevents_fabricated_mode(self):
        g,sig,source=fixture()
        key=next(iter(source))
        source[key]+=" masked"
        with self.assertRaisesRegex(ValueError,"fingerprint mismatch"):
            classify_modes(g,sig,source)

    def test_missing_source_command_explicitly_unresolved(self):
        g,sig,_=fixture()
        out=classify_modes(g,sig,{})
        self.assertEqual(out["missing_saved_clone_commands"],1)
        self.assertEqual(out["source_matched_clone_command_count"],0)

    def test_non_clone_original_verbs_rejected(self):
        g,sig,src=fixture()
        key=next(iter(src))
        bad="fill 100 70 100 102 70 100 0 71 0"
        g["nodes"][-1]["command"]["sha256"]=hashlib.sha256(bad.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,"not a valid clone"):
            classify_modes(g,sig,{key:bad})

    def test_unrecognized_mask_stays_unknown(self):
        g,sig,src=fixture("new_unknown_mask","force")
        out=classify_modes(g,sig,src)
        self.assertEqual(out["source_mask_mode_counts"],{"unknown_mask_mode":1})

    def test_public_result_cannot_leak_original_source_text_or_position(self):
        g,sig,src=fixture("masked","normal")
        text=json.dumps(classify_modes(g,sig,src))
        for forbidden in ("50,70,50","100 70 100","masked normal",'"node_id"','"position"'):
            self.assertNotIn(forbidden,text)

    def test_invalid_graph_signature_rejected(self):
        g,_,src=fixture()
        with self.assertRaises(ValueError):
            classify_modes(g,"f"*64,src)


if __name__=="__main__":
    unittest.main()
