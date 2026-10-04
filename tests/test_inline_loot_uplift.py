import unittest

from tools.uplift_inline_loot_snbt import rewrite_text


class InlineLootUpliftTests(unittest.TestCase):
    def test_rewrites_scoped_loot_entry_and_function_discriminators(self):
        old = (
            'loot replace entity @s contents fish {type:"item",name:"stone",'
            'functions:[{function:"set_components",components:{"minecraft:lore":[]}},'
            '{function:"copy_components",source:"tool"}]}\n'
        )
        new, receipt = rewrite_text(old)
        self.assertIn('modifier:[{type:"set_components"', new)
        self.assertIn('{type:"copy_components",source:"tool"}]', new)
        self.assertNotIn('functions:[', new)
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt[0]["loot_function_discriminator_changes"], 2)

    def test_execute_run_loot_is_in_scope(self):
        old = (
            'execute as @s run loot replace entity @s contents fish '
            '{type:"item",functions:[{function:"set_components",components:{}}]}\n'
        )
        new, receipt = rewrite_text(old)
        self.assertIn('modifier:[{type:"set_components"', new)
        self.assertEqual(len(receipt), 1)

    def test_non_loot_functions_field_is_hard_negative(self):
        old = (
            'data modify storage demo:state functions set value '
            '[{function:"set_components"}]\n'
        )
        new, receipt = rewrite_text(old)
        self.assertEqual(new, old)
        self.assertEqual(receipt, [])

    def test_nested_function_data_is_not_rewritten(self):
        old = (
            'loot give @s fish {type:"item",functions:['
            '{function:"set_components",components:{demo:{function:"domain_value"}}}]}\n'
        )
        new, receipt = rewrite_text(old)
        self.assertIn('{type:"set_components"', new)
        self.assertIn('demo:{function:"domain_value"}', new)
        self.assertEqual(receipt[0]["loot_function_discriminator_changes"], 1)

    def test_modern_input_is_unchanged(self):
        modern = (
            'loot give @s fish {type:"item",modifier:['
            '{type:"set_components",components:{}}]}\n'
        )
        new, receipt = rewrite_text(modern)
        self.assertEqual(new, modern)
        self.assertEqual(receipt, [])


if __name__ == "__main__":
    unittest.main()
