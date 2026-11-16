#!/usr/bin/env python3
"""Public Java 26.3 official-server cursor-held objective RED/BLUE probe.

One public synthetic redstone block and a disposable loopback server. The legacy
branch intentionally omits cursor/crafting replenishment guards; the corrected
branch retains them. Neither is a Lantern world or human gameplay acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server
from probe_keeper_core_replenishment_26_3 import (
    BOT_NAME, CORE, PORT, inventory_has_core, require_false, send,
    source_has_core, source_lacks_core, wait_file, wait_for_predicate,
    wait_server, write_datapack, write_server_config,
)

SCHEMA = "supracraft.keeper-cursor-hold-263/v0.1"


def cursor_predicate(*, held: bool) -> str:
    return f"execute {'if' if held else 'unless'} items entity {BOT_NAME} player.cursor {CORE}"


def configure_guard(root: Path, variant: str) -> dict[str, Any]:
    datapack = write_datapack(root)
    command = datapack["command"]
    cursor = f"unless items entity @a[limit=1] player.cursor {CORE} "
    crafting = f"unless items entity @a[limit=1] player.crafting.* {CORE} "
    if command.count(cursor) != 1 or command.count(crafting) != 1:
        raise RuntimeError("guarded source has no exact cursor/crafting predicates")
    if variant == "legacy":
        command = command.replace(cursor, "").replace(crafting, "")
    elif variant != "guarded":
        raise RuntimeError(f"unknown variant: {variant}")
    fn = (root / "world" / "datapacks" / "supracraft_keeper_core_source" /
          "data" / "supracraft_keeper_core_source" / "function" / "tick.mcfunction")
    fn.write_text(command + "\n", "utf-8")
    return {"variant": variant, "command": command, "legacy_guard_removed": variant == "legacy"}


def execute(evidence: dict[str, Any], variant: str) -> dict[str, Any]:
    release = evidence["artifact_version_json"]
    if release["id"] != "26.3" or int(release["protocol_version"]) != 777:
        raise RuntimeError("requires pinned official Java 26.3 / protocol777")
    with tempfile.TemporaryDirectory(prefix=f"supracraft-cursor-{variant}-") as temp:
        root = Path(temp)
        download_verified_server(evidence, root / "server.jar")
        write_server_config(root)
        pack = configure_guard(root, variant)
        log_path = root / "server.log"
        files = {name: root / f"bot-{name}.ready" for name in ("ready", "start", "held", "release", "done")}
        receipt = root / "bot-receipt.json"
        with log_path.open("w", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(root / "server.jar"), "nogui"],
                cwd=root, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True,
            )
            bot: subprocess.Popen[str] | None = None
            try:
                status = wait_server(server, 777)
                send(server, "forceload add 0 0")
                send(server, "fill -2 69 -2 3 69 4 minecraft:stone")
                send(server, "fill -2 70 -2 3 72 4 minecraft:air")
                send(server, "setblock 0 70 0 minecraft:chest[facing=south]")
                source_attempts, source_seconds = wait_for_predicate(
                    server, log_path, marker="CURSOR_SOURCE_READY", predicate=source_has_core(), timeout=15.0,
                )
                env = dict(os.environ)
                env.update({
                    "CURSOR_BOT_READY": str(files["ready"]),
                    "CURSOR_BOT_START": str(files["start"]),
                    "CURSOR_BOT_HELD": str(files["held"]),
                    "CURSOR_BOT_RELEASE": str(files["release"]),
                    "CURSOR_BOT_DONE": str(files["done"]),
                    "CURSOR_BOT_RESULT": str(receipt),
                })
                bot = subprocess.Popen(
                    ["node", str(Path(__file__).with_name("probe_mineflayer_cursor_hold.js"))],
                    cwd=Path(__file__).resolve().parents[1], env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                )
                wait_file(files["ready"], bot, 45)
                send(server, f"gamemode survival {BOT_NAME}")
                send(server, f"tp {BOT_NAME} 0.5 70.0 2.5 180 0")
                files["start"].write_text("source-ready\n", "utf-8")
                wait_file(files["held"], bot, 45)
                cursor_attempts, cursor_seconds = wait_for_predicate(
                    server, log_path, marker="CURSOR_OBSERVED", predicate=cursor_predicate(held=True), timeout=12.0,
                )
                if variant == "legacy":
                    source_after_attempts, source_after_seconds = wait_for_predicate(
                        server, log_path, marker="CURSOR_LEGACY_REFILL", predicate=source_has_core(), timeout=12.0,
                    )
                    source_while_held = True
                else:
                    source_after_attempts, source_after_seconds = wait_for_predicate(
                        server, log_path, marker="CURSOR_GUARDED_EMPTY", predicate=source_lacks_core(), timeout=12.0,
                    )
                    # With an actively held item, the automatic replacement
                    # must remain absent for multiple server ticks.
                    require_false(server, log_path, marker="CURSOR_UNEXPECTED_REFILL",
                                  predicate=source_has_core(), settle=1.5)
                    source_while_held = False
                files["release"].write_text("server-verified\n", "utf-8")
                wait_file(files["done"], bot, 30)
                after_attempts, after_seconds = wait_for_predicate(
                    server, log_path, marker="CURSOR_DEPOSITED_INVENTORY", predicate=inventory_has_core(),
                    timeout=12.0,
                )
                wait_for_predicate(server, log_path, marker="CURSOR_NO_LONGER_HELD",
                                   predicate=cursor_predicate(held=False), timeout=12.0)
                if variant == "guarded":
                    require_false(server, log_path, marker="CURSOR_DEPOSIT_DUPLICATE",
                                  predicate=source_has_core(), settle=0.8)
                try:
                    out, _ = bot.communicate(timeout=20)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    out, _ = bot.communicate(timeout=5)
                    raise RuntimeError("client worker did not exit: " + out[-1600:])
                if bot.returncode != 0 or not receipt.exists():
                    raise RuntimeError("client failed: " + out[-1600:])
                bot_result = json.loads(receipt.read_text("utf-8"))
                if bot_result.get("error") or not bot_result.get("player_inventory_has_core"):
                    raise RuntimeError("invalid client evidence: " + json.dumps(bot_result)[-1600:])
                send(server, "stop")
                if server.wait(timeout=40) != 0:
                    raise RuntimeError("official server exited nonzero")
            finally:
                if bot is not None and bot.poll() is None:
                    bot.terminate()
                    try:
                        bot.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        bot.kill(); bot.wait(timeout=5)
                if server.poll() is None:
                    try:
                        send(server, "stop"); server.wait(timeout=15)
                    except Exception:
                        server.kill(); server.wait(timeout=5)
        logs = log_path.read_text("utf-8", errors="replace")
        errors = [line for line in logs.splitlines() if "/ERROR]:" in line or "/ERROR] " in line]
        if errors:
            raise RuntimeError("server reported errors: " + " | ".join(errors[-5:]))
        return {
            "schema": SCHEMA, "result": "EXPECTED_RED_OBSERVED" if variant == "legacy" else "BOUNDED_BLUE_OBSERVED",
            "variant": variant, "release": {"version": "26.3", "protocol": 777,
              "server_sha256": evidence["server_artifact"]["sha256"]},
            "policy": pack, "official_server": {"status_protocol": int(status["version"]["protocol"]),
              "source_ready": True, "cursor_held_on_server": True,
              "source_refilled_while_cursor_held": source_while_held,
              "player_inventory_recovered_after_cursor": True,
              "source_readiness_attempts": source_attempts, "cursor_attempts": cursor_attempts,
              "source_after_cursor_attempts": source_after_attempts,
              "inventory_deposit_attempts": after_attempts,
              "server_errors": 0},
            "player": bot_result,
            "limitations": ["single connected public synthetic player, not H83 private world",
              "test controller uses setup commands, player performs actual chest/window clicks",
              "does not prove crafting slot occupancy, item entities, restart or stock-human story"],
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--variant", choices=("legacy", "guarded"), required=True)
    args = p.parse_args()
    try:
        result = execute(json.loads(args.evidence.read_text("utf-8")), args.variant)
        code = 0
    except Exception as exc:
        result = {"schema": SCHEMA, "variant": args.variant, "result": "NOT_QUALIFIED", "error": str(exc)[:1600]}
        code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
