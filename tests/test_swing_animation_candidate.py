import unittest

from tools.uplift_swing_animation_candidate import (
    classify_unhandled,
    rewrite_direct_component_keys,
)


class SwingAnimationCandidateTests(unittest.TestCase):
    def test_attack_mode(self):
        src = '{"minecraft:swing_animation":{duration:10,type:"stab"},"demo:x":1}'
        out, receipt = rewrite_direct_component_keys(src, "attack")
        self.assertEqual(
            out,
            '{"minecraft:attack_animation":{duration:10,type:"stab"},"demo:x":1}',
        )
        self.assertEqual(len(receipt), 1)

    def test_both_mode_duplicates_value(self):
        src = '{"minecraft:swing_animation":{duration:10,type:"stab"}}'
        out, receipt = rewrite_direct_component_keys(src, "both")
        self.assertEqual(
            out,
            '{"minecraft:attack_animation":{duration:10,type:"stab"},'
            '"minecraft:interact_animation":{duration:10,type:"stab"}}',
        )
        self.assertEqual(receipt[0]["mode"], "both")

    def test_negated_key_is_not_automatic(self):
        src = '{"!minecraft:swing_animation":{}}'
        out, receipt = rewrite_direct_component_keys(src, "both")
        self.assertEqual(out, src)
        self.assertEqual(receipt, [])
        self.assertEqual(classify_unhandled(src)["negated_component_key"], 1)

    def test_control_flow_references_are_reported_not_rewritten(self):
        src = (
            'data remove storage demo data.minecraft:swing_animation\n'
            'execute if items entity @s contents *[swing_animation={}] run say yes\n'
        )
        out, receipt = rewrite_direct_component_keys(src, "both")
        self.assertEqual(out, src)
        self.assertEqual(receipt, [])
        counts = classify_unhandled(src)
        self.assertEqual(counts["component_predicate"], 1)
        self.assertEqual(counts["storage_or_path_reference"], 1)


if __name__ == "__main__":
    unittest.main()
