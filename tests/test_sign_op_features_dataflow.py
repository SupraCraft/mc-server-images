import unittest

from tools.analyze_sign_op_features_dataflow import classify_file


class SignDataflowTests(unittest.TestCase):
    def test_local_privileged_merge(self):
        old = (
            'setblock 1 2 3 minecraft:oak_sign\n'
            'data merge block 1 2 3 {front_text:{messages:['
            '{click_event:{action:"run_command",command:"say hi"}}]}}\n'
        )
        new = old.replace(
            '{front_text:',
            '{allow_op_features:1b,front_text:',
            1,
        )
        row = classify_file(old, new)
        self.assertEqual(row["classification"], "LOCAL_PRIVILEGED_MERGE")

    def test_local_text_copy(self):
        old = (
            'setblock 1 2 3 minecraft:oak_sign\n'
            'data modify block 1 2 3 front_text.messages set from block 4 5 6 front_text.messages\n'
        )
        new = old.replace('minecraft:oak_sign', 'minecraft:oak_sign{allow_op_features:1b}')
        row = classify_file(old, new)
        self.assertEqual(row["classification"], "LOCAL_TEXT_COPY")

    def test_unresolved_cross_function(self):
        old = 'data merge block 1 2 3 {front_text:{messages:[{click_event:{action:"run_command",command:"say hi"}}]}}\n'
        new = old.replace('{front_text:', '{allow_op_features:1b,front_text:')
        row = classify_file(old, new)
        self.assertEqual(row["classification"], "UNRESOLVED_OR_CROSS_FUNCTION")


if __name__ == "__main__":
    unittest.main()
