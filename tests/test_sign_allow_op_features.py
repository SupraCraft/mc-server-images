import unittest

from tools.uplift_sign_allow_op_features import rewrite_text


class SignAllowOpFeaturesTests(unittest.TestCase):
    def test_direct_sign_run_command_is_upgraded(self):
        src = (
            'execute if entity @s run setblock 1 2 3 '
            'minecraft:pale_oak_wall_sign[facing=south]'
            '{front_text:{messages:[{text:"",click_event:{action:"run_command",command:"trigger x"}}]},'
            'is_waxed:1b}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertIn('is_waxed:1b,allow_op_features:1b}', out)
        self.assertEqual(len(receipts), 1)

    def test_hanging_sign_is_supported(self):
        src = (
            'setblock ~ ~ ~ minecraft:oak_hanging_sign[rotation=0]'
            '{front_text:{messages:[{click_event:{action:"run_command",command:"say hi"}}]}}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertIn('allow_op_features:1b}', out)
        self.assertEqual(receipts[0]["block_id"], "minecraft:oak_hanging_sign")

    def test_non_sign_is_hard_negative(self):
        src = (
            'setblock 1 2 3 minecraft:chest'
            '{front_text:{messages:[{click_event:{action:"run_command",command:"say hi"}}]}}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])

    def test_non_privileged_sign_text_is_not_changed(self):
        src = (
            'setblock 1 2 3 minecraft:oak_sign'
            '{front_text:{messages:[{text:"hello"}]},is_waxed:1b}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])

    def test_existing_true_is_preserved(self):
        src = (
            'setblock 1 2 3 minecraft:oak_sign'
            '{front_text:{messages:[{click_event:{action:"run_command",command:"say hi"}}]},'
            'allow_op_features:1b}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])

    def test_existing_false_is_preserved_as_intentional_negative(self):
        src = (
            'setblock 1 2 3 minecraft:oak_sign'
            '{front_text:{messages:[{click_event:{action:"run_command",command:"say hi"}}]},'
            'allow_op_features:0b}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])

    def test_separate_data_merge_is_not_guessed(self):
        src = (
            'setblock 1 2 3 minecraft:oak_sign\n'
            'data merge block 1 2 3 {front_text:{messages:['
            '{click_event:{action:"run_command",command:"say hi"}}]}}\n'
        )
        out, receipts = rewrite_text(src)
        self.assertEqual(out, src)
        self.assertEqual(receipts, [])


if __name__ == "__main__":
    unittest.main()
