import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "inspect_modern_microscope_hook_structure.py"
SPEC = importlib.util.spec_from_file_location(
    "inspect_modern_microscope_hook_structure", MODULE_PATH
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class ModernHookStructureTests(unittest.TestCase):
    def test_targets_are_server_only_first_canary(self):
        ids = {row["id"] for row in mod.TARGETS}
        self.assertEqual(
            ids,
            {
                "server_tick",
                "block_state_write",
                "command_block_neighbor",
                "command_block_tick",
                "command_block_execute",
                "command_dispatch",
                "command_dispatch_prefixed",
            },
        )
        self.assertFalse(any("packet" in row["id"] for row in mod.TARGETS))
        self.assertFalse(any("wire" in row["id"] for row in mod.TARGETS))

    def test_redstone_targets_are_bounded_and_distinct(self):
        ids={row["id"] for row in mod.REDSTONE_TARGETS}
        self.assertEqual(
            ids,
            {
                "wire_update_power_strength",
                "wire_get_block_signal",
                "wire_get_signal",
                "wire_get_direct_signal",
                "wire_neighbor_changed",
                "server_level_neighbor_changed",
                "server_level_update_neighbors_at",
            },
        )
        self.assertTrue(all("packet" not in row["id"] for row in mod.REDSTONE_TARGETS))
        self.assertTrue(all("command" not in row["id"] for row in mod.REDSTONE_TARGETS))
        self.assertEqual(set(mod.TARGET_SETS),{"core","redstone","piston"})
        roles={row["id"]:row["role"] for row in mod.REDSTONE_TARGETS}
        self.assertEqual(
            roles["server_level_neighbor_changed"],"server_world_host"
        )
        self.assertEqual(
            roles["server_level_update_neighbors_at"],"server_world_host"
        )
        self.assertFalse(
            any(
                row["role"]=="world_state_host"
                for row in mod.REDSTONE_TARGETS
                if row["event_family"]=="neighbor_notify"
            )
        )

    def test_piston_targets_are_bounded_structure_only_candidates(self):
        ids={row["id"] for row in mod.PISTON_TARGETS}
        self.assertEqual(
            ids,
            {
                "piston_check_if_extend",
                "piston_get_neighbor_signal",
                "piston_move_blocks",
                "piston_trigger_event",
                "piston_structure_resolve",
                "piston_moving_tick",
                "piston_final_tick",
            },
        )
        self.assertTrue(all(row["role"].startswith("piston_") for row in mod.PISTON_TARGETS))
        self.assertTrue(all("candidate" in row["event_family"] for row in mod.PISTON_TARGETS))
        self.assertEqual(set(mod.TARGET_SETS),{"core","redstone","piston"})

    def test_parse_sections_selects_exact_descriptor(self):
        text = """
public class net.minecraft.Example {
  private int field;
    descriptor: I

  public void tick(java.lang.String);
    descriptor: (Ljava/lang/String;)V
    Code:
       0: aload_0
       1: return

  public void tick(int);
    descriptor: (I)V
    Code:
       0: return
}
"""
        sections = mod.parse_javap_sections(text, "net.minecraft.Example")
        self.assertEqual(
            set(sections),
            {
                ("tick", "(Ljava/lang/String;)V"),
                ("tick", "(I)V"),
            },
        )

    def test_method_suffix_collision_is_not_constructor(self):
        text = """
public class net.minecraft.world.level.Level {
  protected net.minecraft.world.level.Level(float);
    descriptor: (F)V
    Code:
       0: return

  public float getRainLevel(float);
    descriptor: (F)F
    Code:
       0: fconst_0
       1: freturn
}
"""
        sections = mod.parse_javap_sections(
            text,
            "net.minecraft.world.level.Level",
        )
        self.assertIn(("<init>", "(F)V"), sections)
        self.assertIn(("getRainLevel", "(F)F"), sections)

    def test_normalization_removes_offsets_and_constant_pool_indices(self):
        a = [
            "    Code:",
            "       0: aload_0",
            "       1: invokevirtual #12 // Method net/minecraft/Foo.bar:()V",
            "       4: return",
        ]
        b = [
            "    Code:",
            "      10: aload_0",
            "      11: invokevirtual #99 // Method net/minecraft/Foo.bar:()V",
            "      14: return",
        ]
        na, ca = mod.normalize_method_section(a)
        nb, cb = mod.normalize_method_section(b)
        self.assertEqual(na, nb)
        self.assertEqual(ca, 3)
        self.assertEqual(cb, 3)

    def test_symbolic_references_are_bounded_names_not_disassembly(self):
        refs = mod.symbolic_references(
            [
                "1: invokevirtual #12 // Method net/minecraft/Foo.bar:()V",
                "4: getfield #13 // Field state:I",
                "7: checkcast #14 // class net/minecraft/Baz",
            ],
            "net.minecraft.Example",
        )
        self.assertEqual(
            refs["method_refs"],
            ["net/minecraft/Foo.bar:()V"],
        )
        self.assertEqual(
            refs["field_refs"],
            ["net/minecraft/Example.state:I"],
        )
        self.assertEqual(refs["class_refs"], ["net/minecraft/Baz"])

    def test_schema_retains_prequalification_boundary(self):
        schema = json.loads(
            (
                ROOT
                / "bench"
                / "worldgen"
                / "observability"
                / "supracraft-causal-hook-structure-v1.schema.json"
            ).read_text()
        )
        self.assertEqual(
            schema["properties"]["qualification_status"]["const"],
            "structure_only_not_hook_qualified",
        )


if __name__ == "__main__":
    unittest.main()
