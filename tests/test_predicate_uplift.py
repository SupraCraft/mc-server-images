import unittest

from tools.uplift_predicate_26_2_to_26_3 import uplift_predicate_document


class PredicateUpliftTests(unittest.TestCase):
    def test_simple_root_discriminator(self):
        old = {
            "condition": "minecraft:entity_properties",
            "entity": "this",
            "predicate": {"minecraft:effects": {"minecraft:invisibility": {}}},
        }
        new, changes = uplift_predicate_document(old)
        self.assertEqual(new["type"], "minecraft:entity_properties")
        self.assertNotIn("condition", new)
        self.assertEqual(len(changes), 1)

    def test_nested_inverted_predicate(self):
        old = {
            "condition": "minecraft:inverted",
            "term": {
                "condition": "minecraft:entity_properties",
                "entity": "this",
                "predicate": {"minecraft:movement": {"x": {"min": -2, "max": 2}}},
            },
        }
        new, changes = uplift_predicate_document(old)
        self.assertEqual(new["type"], "minecraft:inverted")
        self.assertEqual(new["term"]["type"], "minecraft:entity_properties")
        self.assertEqual(
            [c["rule"] for c in changes],
            ["predicate_condition_to_type", "predicate_condition_to_type"],
        )

    def test_reference_terms_collapse_to_ids(self):
        old = {
            "condition": "minecraft:all_of",
            "terms": [
                {"condition": "minecraft:reference", "name": "demo:a"},
                {"condition": "minecraft:reference", "name": "demo:b"},
            ],
        }
        new, changes = uplift_predicate_document(old)
        self.assertEqual(new, {
            "type": "minecraft:all_of",
            "terms": ["demo:a", "demo:b"],
        })
        self.assertEqual(
            sum(c["rule"] == "predicate_reference_to_id" for c in changes), 2
        )

    def test_arbitrary_nested_condition_is_hard_negative(self):
        old = {
            "condition": "minecraft:entity_properties",
            "entity": "this",
            "predicate": {
                "demo:component": {
                    "condition": "this-is-domain-data",
                    "other": 1,
                }
            },
        }
        new, _ = uplift_predicate_document(old)
        self.assertEqual(
            new["predicate"]["demo:component"]["condition"],
            "this-is-domain-data",
        )

    def test_modern_document_unchanged(self):
        modern = {
            "type": "minecraft:inverted",
            "term": {
                "type": "minecraft:entity_properties",
                "entity": "this",
                "predicate": {},
            },
        }
        new, changes = uplift_predicate_document(modern)
        self.assertEqual(new, modern)
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
