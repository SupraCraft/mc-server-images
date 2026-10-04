#!/usr/bin/env python3
"""Run a bounded exact-Java-26.3 server/client/render visual smoke.

The official server remains semantic authority. Mineflayer supplies a real
protocol client/traversal actor. Prismarine-viewer is presentation-only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25571
BOT_NAME = "SupraCraftVisual"


def write_server_config(root: Path) -> None:
    (root / "eula.txt").write_text("eula=true\n", "utf-8")
    (root / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
                "white-list=false",
                "enforce-whitelist=false",
                f"server-port={PORT}",
                "view-distance=6",
                "simulation-distance=4",
                "spawn-protection=0",
                "max-players=4",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft named-place visual qualification",
                "",
            ]
        ),
        "utf-8",
    )


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_server(process: subprocess.Popen[str], protocol: int, timeout: int = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early: {process.returncode}")
        try:
            status = status_query("127.0.0.1", PORT, protocol)
            if int(status.get("version", {}).get("protocol", -1)) == protocol:
                return status
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"server readiness timeout: {last_error}")


def wait_file(path: Path, process: subprocess.Popen[str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            out = ""
            if process.stdout is not None:
                out = process.stdout.read()[-5000:]
            raise RuntimeError(f"worker exited before {path.name}: {process.returncode}; {out!r}")
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def build_barn_fixture(server: subprocess.Popen[str]) -> None:
    # A deliberately simple recognizable silhouette using common vanilla blocks
    # that the current 26.x viewer asset fallback can render.
    commands = [
        "forceload add -3 -3 3 3",
        "setworldspawn 0 70 20",
        "fill -32 68 -32 32 90 48 minecraft:air",
        "fill -32 69 -32 32 69 48 minecraft:grass_block",
        # brick barn shell
        "fill -8 70 -6 8 76 6 minecraft:bricks hollow",
        "fill -2 70 6 2 74 6 minecraft:air",
        "fill -2 70 -6 2 74 -6 minecraft:air",
        # dark timber floor / loft
        "fill -7 70 -5 7 70 5 minecraft:dark_oak_planks",
        "fill -7 75 -5 7 75 5 minecraft:spruce_planks",
        # red stepped gable roof
        "fill -10 77 -8 10 77 8 minecraft:red_terracotta",
        "fill -9 78 -7 9 78 7 minecraft:red_terracotta",
        "fill -8 79 -6 8 79 6 minecraft:red_terracotta",
        "fill -7 80 -5 7 80 5 minecraft:red_terracotta",
        "fill -6 81 -4 6 81 4 minecraft:red_terracotta",
        "fill -5 82 -3 5 82 3 minecraft:red_terracotta",
        "fill -4 83 -2 4 83 2 minecraft:red_terracotta",
        "fill -3 84 -1 3 84 1 minecraft:red_terracotta",
        # cupola
        "fill -2 84 -2 2 87 2 minecraft:dark_oak_planks hollow",
        "setblock 0 88 0 minecraft:lantern",
        # pens and hay recognition cues
        "fill -14 70 -5 -10 70 5 minecraft:oak_fence",
        "fill 10 70 -5 14 70 5 minecraft:oak_fence",
        "fill -6 71 3 -4 73 5 minecraft:hay_block",
        "fill 4 71 3 6 73 5 minecraft:hay_block",
        # approach path
        "fill -2 69 7 2 69 24 minecraft:dirt_path",
    ]
    for command in commands:
        send(server, command)
    time.sleep(2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3 identity")
    protocol = int(info["protocol_version"])

    chrome = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if not chrome:
        raise RuntimeError("no Chrome/Chromium executable found on runner")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="named-place-visual-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            bot = None
            try:
                status = wait_server(server, protocol)
                build_barn_fixture(server)

                ready = root / "bot.ready"
                op_ready = root / "op.ready"
                result_path = args.output_dir / "visual-receipt.json"

                env = dict(os.environ)
                env.update(
                    {
                        "MC_HOST": "127.0.0.1",
                        "MC_PORT": str(PORT),
                        "MC_USER": BOT_NAME,
                        "BOT_READY_FILE": str(ready),
                        "OP_READY_FILE": str(op_ready),
                        "VISUAL_OUTPUT_DIR": str(args.output_dir),
                        "VISUAL_RESULT_FILE": str(result_path),
                        "CHROME_PATH": chrome,
                    }
                )

                bot = subprocess.Popen(
                    ["node", str(Path(__file__).with_name("probe_named_place_visual.js"))],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_file(ready, bot, 45)
                send(server, f"op {BOT_NAME}")
                send(server, f"gamemode creative {BOT_NAME}")
                time.sleep(1)
                op_ready.write_text("ready\n", "utf-8")

                try:
                    bot_stdout, _ = bot.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    bot_stdout, _ = bot.communicate(timeout=10)
                    raise RuntimeError("visual worker timed out: " + bot_stdout[-5000:])

                if not result_path.exists():
                    raise RuntimeError("visual worker produced no receipt: " + bot_stdout[-5000:])
                receipt = json.loads(result_path.read_text("utf-8"))
                if bot.returncode != 0 or not receipt.get("traversal", {}).get("passed"):
                    raise RuntimeError(
                        "visual worker failed: "
                        + json.dumps(receipt, sort_keys=True)
                        + " stdout="
                        + bot_stdout[-5000:]
                    )

                send(server, "execute if block 0 88 0 minecraft:lantern run say SUPRACRAFT_VISUAL_FIXTURE_OK")
                time.sleep(1)
                send(server, "save-all flush")
                time.sleep(1)
                send(server, "stop")
                exit_code = server.wait(timeout=45)
                log.flush()
                log.seek(0)
                server_log = log.read()
            finally:
                if bot is not None and bot.poll() is None:
                    bot.kill()
                    bot.wait(timeout=10)
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

        if exit_code != 0:
            raise RuntimeError(f"server exit code {exit_code}")
        if "SUPRACRAFT_VISUAL_FIXTURE_OK" not in server_log:
            raise RuntimeError("official server did not verify visual fixture")
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if errors:
            raise RuntimeError("server emitted ERROR lines: " + " | ".join(errors[-20:]))

        receipt["official_server_verified"] = True
        receipt["status_protocol"] = int(status.get("version", {}).get("protocol", -1))
        receipt["chrome_executable"] = Path(chrome).name
        result_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
