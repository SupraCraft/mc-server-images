import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "inventory_modern_microscope_symbols.py"
SPEC = importlib.util.spec_from_file_location(
    "inventory_modern_microscope_symbols", MODULE_PATH
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class ModernSymbolInventoryTests(unittest.TestCase):
    def test_roles_are_exact_named_runtime_classes(self):
        self.assertEqual(
            mod.ROLE_SUFFIXES["server_tick_host"],
            "net/minecraft/server/MinecraftServer.class",
        )
        self.assertEqual(
            mod.ROLE_SUFFIXES["command_dispatch"],
            "net/minecraft/commands/Commands.class",
        )
        self.assertEqual(
            mod.ROLE_SUFFIXES["redstone_wire"],
            "net/minecraft/world/level/block/RedStoneWireBlock.class",
        )

    def test_candidate_methods_are_search_aids_only(self):
        methods = [
            {
                "name": "tickServer",
                "descriptor": "(Ljava/util/function/BooleanSupplier;)V",
                "declaration_sha256": "0" * 64,
            },
            {
                "name": "stopServer",
                "descriptor": "()V",
                "declaration_sha256": "1" * 64,
            },
        ]
        rows = mod.candidate_methods("server_tick_host", methods)
        self.assertEqual([row["name"] for row in rows], ["tickServer"])

    def test_symbol_inventory_schema_is_not_capability_manifest(self):
        schema = json.loads(
            (
                ROOT
                / "bench"
                / "worldgen"
                / "observability"
                / "supracraft-causal-symbol-inventory-v1.schema.json"
            ).read_text()
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "supracraft-causal-symbol-inventory/1",
        )
        self.assertEqual(
            schema["properties"]["qualification_status"]["const"],
            "inventory_only_not_hook_qualified",
        )

    def test_required_roles_cover_first_modern_canary_surface(self):
        required = {
            "server_tick_host",
            "world_state_host",
            "server_world_host",
            "command_block",
            "command_block_entity",
            "command_dispatch",
            "packet_listener",
            "redstone_wire",
        }
        self.assertEqual(set(mod.ROLE_SUFFIXES), required)


if __name__ == "__main__":
    unittest.main()
