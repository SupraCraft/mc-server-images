#!/usr/bin/env python3
"""Qualify sequential fixture-assisted MCBUILD execution on official Java 26.3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import threading
from collections import deque
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query


BOT_NAME = "SupraBuildProbe"
PORT = 25571


def write_server_config(root: Path) -> None:
    (root / "eula.txt").write_text("eula=true\n", "utf-8")
    (root / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
                "white-list=false",
                "enforce-whitelist=false",
                f"server-port={PORT}",
                "view-distance=4",
                "simulation-distance=3",
                "spawn-protection=0",
                "max-players=2",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft fixture-assisted MCBUILD qualification",
                "",
            ]
        ),
        "utf-8",
    )


def send_server(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_server(
    process: subprocess.Popen[str], protocol: int, timeout: int = 180
) -> dict[str, Any]:
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


class JsonLinePeer:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        if (
            process.stdout is None
            or process.stdin is None
            or process.stderr is None
        ):
            raise RuntimeError("worker pipes unavailable")
        self.process = process
        self.stdout = process.stdout
        self.stdin = process.stdin
        self.stderr = process.stderr
        self.messages: queue.Queue[dict[str, Any]] = queue.Queue()
        self.last_control_message: dict[str, Any] | None = None
        self.reader_error: str | None = None
        self.stderr_tail: deque[str] = deque(maxlen=200)
        self.stderr_lock = threading.Lock()
        self.stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="mcbuild-worker-stdout",
            daemon=True,
        )
        self.stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="mcbuild-worker-stderr",
            daemon=True,
        )
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _read_stdout(self) -> None:
        try:
            for line in self.stdout:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    self.messages.put(value)
        except Exception as exc:
            self.reader_error = repr(exc)

    def _read_stderr(self) -> None:
        try:
            for line in self.stderr:
                with self.stderr_lock:
                    self.stderr_tail.append(line)
        except Exception as exc:
            with self.stderr_lock:
                self.stderr_tail.append(
                    f"<stderr reader error: {exc!r}>\n"
                )

    def _diagnostic(
        self,
        phase: str,
        action_id: str | None,
    ) -> dict[str, Any]:
        with self.stderr_lock:
            stderr_tail = "".join(list(self.stderr_tail))[-4000:]
        return {
            "phase": phase,
            "action_id": action_id,
            "worker_poll": self.process.poll(),
            "reader_error": self.reader_error,
            "last_control_message": self.last_control_message,
            "queued_control_messages": self.messages.qsize(),
            "stderr_tail": stderr_tail,
        }

    def recv(
        self,
        timeout: float = 30.0,
        *,
        phase: str,
        action_id: str | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                value = self.messages.get(timeout=min(0.5, remaining))
            except queue.Empty:
                if self.process.poll() is not None:
                    diagnostic = self._diagnostic(phase, action_id)
                    raise RuntimeError(
                        "worker exited before control message: "
                        + json.dumps(diagnostic, sort_keys=True)
                    )
                continue
            self.last_control_message = value
            return value
        diagnostic = self._diagnostic(phase, action_id)
        raise RuntimeError(
            "timeout waiting for worker control message: "
            + json.dumps(diagnostic, sort_keys=True)
        )

    def send(self, value: dict[str, Any]) -> None:
        self.stdin.write(json.dumps(value, sort_keys=True) + "\n")
        self.stdin.flush()


def verify_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != "mcbuild/v0.1-public-fixture":
        raise ValueError("unsupported synthetic MCBUILD schema")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("plan requires actions")
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("invalid action")
        action_id = action.get("id")
        if not isinstance(action_id, str) or action_id in seen:
            raise ValueError("invalid or duplicate action id")
        for dep in action.get("depends_on", []):
            if dep not in seen:
                raise ValueError(
                    f"dependency {dep!r} for {action_id!r} is not prior"
                )
        seen.add(action_id)


def marker(index: int) -> str:
    return f"SUPRACRAFT_MCBUILD_ACTION_{index:02d}_OK"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("qualification requires Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    verify_plan(plan)

    with tempfile.TemporaryDirectory(prefix="mcbuild-sequential-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    "java",
                    "-Xms512M",
                    "-Xmx1536M",
                    "-jar",
                    str(server_jar),
                    "nogui",
                ],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                status = wait_server(server, protocol)
                send_server(server, "forceload add 0 0")
                send_server(server, "setworldspawn 0 70 0")
                send_server(server, "fill -2 68 -2 7 73 3 minecraft:air")
                bootstrap = plan["initial_condition"]["bootstrap_support"]
                bx, by, bz = map(int, bootstrap["at"])
                send_server(
                    server,
                    f"setblock {bx} {by} {bz} {bootstrap['block']}",
                )
                time.sleep(1)

                bot_result_path = root / "bot-result.json"
                env = dict(os.environ)
                env.update(
                    {
                        "MC_PORT": str(PORT),
                        "MCBUILD_PLAN": str(args.plan.resolve()),
                        "BOT_RESULT_FILE": str(bot_result_path),
                    }
                )
                worker = subprocess.Popen(
                    [
                        "node",
                        str(
                            Path(__file__).with_name(
                                "probe_mcbuild_sequential.js"
                            )
                        ),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )
                peer = JsonLinePeer(worker)

                ready = peer.recv(40, phase="await-ready")
                if (
                    ready.get("type") != "ready"
                    or int(ready.get("protocol", -1)) != protocol
                ):
                    raise RuntimeError(f"unexpected worker ready: {ready!r}")

                send_server(server, f"gamemode survival {BOT_NAME}")
                controller_receipts: list[dict[str, Any]] = []
                placed = 0
                wait_phase = "await-prepare"
                wait_action_id: str | None = plan["actions"][0]["id"]

                while True:
                    msg = peer.recv(
                        40,
                        phase=wait_phase,
                        action_id=wait_action_id,
                    )
                    kind = msg.get("type")
                    if kind == "prepare":
                        index = int(msg["index"])
                        action = plan["actions"][index]
                        if msg.get("id") != action["id"]:
                            raise RuntimeError("worker/action identity mismatch")

                        pos = action["bot_position"]
                        yaw = float(action.get("bot_yaw", 0))
                        pitch = float(action.get("bot_pitch", 0))
                        send_server(server, f"clear {BOT_NAME}")
                        send_server(
                            server,
                            f"give {BOT_NAME} minecraft:{action['item']} 1",
                        )
                        send_server(
                            server,
                            f"tp {BOT_NAME} {pos[0]} {pos[1]} {pos[2]} "
                            f"{yaw} {pitch}",
                        )
                        time.sleep(0.25)
                        peer.send({"type": "prepared", "id": action["id"]})
                        wait_phase = "await-placement-result"
                        wait_action_id = action["id"]
                        controller_receipts.append(
                            {
                                "index": index,
                                "id": action["id"],
                                "item_provisioned": action["item"],
                                "position_requested": pos,
                                "yaw_requested": yaw,
                            }
                        )
                    elif kind == "placed":
                        expected = plan["actions"][placed]["id"]
                        if msg.get("id") != expected:
                            raise RuntimeError(
                                "worker placed/action identity mismatch"
                            )
                        placed += 1
                        if placed < len(plan["actions"]):
                            wait_phase = "await-prepare"
                            wait_action_id = plan["actions"][placed]["id"]
                        else:
                            wait_phase = "await-complete"
                            wait_action_id = None
                    elif kind == "complete":
                        break
                    elif kind == "error":
                        raise RuntimeError(
                            "worker error: " + str(msg.get("error"))
                        )
                    else:
                        raise RuntimeError(
                            f"unexpected worker message {msg!r}"
                        )

                try:
                    worker_exit = worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker_exit = worker.wait(timeout=5)
                if worker_exit != 0:
                    diagnostic = peer._diagnostic("worker-exit", None)
                    raise RuntimeError(
                        f"worker exit {worker_exit}: "
                        + json.dumps(diagnostic, sort_keys=True)
                    )
                if placed != len(plan["actions"]):
                    raise RuntimeError(
                        f"worker placed {placed}, expected {len(plan['actions'])}"
                    )
                if not bot_result_path.exists():
                    raise RuntimeError("worker produced no result receipt")
                bot_result = json.loads(
                    bot_result_path.read_text("utf-8")
                )
                if (
                    not bot_result.get("completed")
                    or len(bot_result.get("actions", []))
                    != len(plan["actions"])
                ):
                    raise RuntimeError("worker receipt is incomplete")

                for index, action in enumerate(plan["actions"]):
                    x, y, z = map(int, action["at"])
                    send_server(
                        server,
                        f"execute if block {x} {y} {z} "
                        f"{action['desired_state']} run say {marker(index)}",
                    )
                    if action.get("require_block_entity"):
                        send_server(
                            server,
                            f"execute if data block {x} {y} {z} id "
                            f"run say SUPRACRAFT_MCBUILD_BE_{index:02d}_OK",
                        )
                time.sleep(2)
                send_server(server, "stop")
                try:
                    server_exit = server.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server_exit = server.wait(timeout=10)

                log.flush()
                log.seek(0)
                server_log = log.read()
            finally:
                if server.poll() is None:
                    try:
                        send_server(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

        if server_exit != 0:
            raise RuntimeError(f"server exit code {server_exit}")

        missing_markers = [
            marker(index)
            for index in range(len(plan["actions"]))
            if marker(index) not in server_log
        ]
        missing_be = [
            f"SUPRACRAFT_MCBUILD_BE_{index:02d}_OK"
            for index, action in enumerate(plan["actions"])
            if action.get("require_block_entity")
            and f"SUPRACRAFT_MCBUILD_BE_{index:02d}_OK" not in server_log
        ]
        if missing_markers or missing_be:
            raise RuntimeError(
                f"independent server oracle failed: "
                f"states={missing_markers}, block_entities={missing_be}"
            )

        errors = [
            line
            for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if errors:
            raise RuntimeError(
                "server emitted ERROR lines: " + " | ".join(errors[-20:])
            )

    result = {
        "schema": "supracraft.fixture-assisted-mcbuild-qualification/v0.1",
        "minecraft": {
            "edition": "java",
            "version": "26.3",
            "protocol": protocol,
            "world_version": int(info["world_version"]),
        },
        "plan": {
            "schema": plan["schema"],
            "sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "actions": len(plan["actions"]),
        },
        "controller": {
            "positioning": "server-console-teleport",
            "inventory_provisioning": "server-console-clear-and-give",
            "receipts": controller_receipts,
        },
        "worker": bot_result,
        "official_server_verified_actions": len(plan["actions"]),
        "official_server_verified_block_entities": sum(
            1 for action in plan["actions"]
            if action.get("require_block_entity")
        ),
        "status_protocol": int(
            status.get("version", {}).get("protocol", -1)
        ),
        "qualified_capabilities": [
            "execution.position.fixture-controller",
            "inventory.provision.fixture-controller",
            "plan.execute.sequential",
        ],
        "explicit_exclusions": [
            "pathfinding",
            "survival-resource-acquisition",
            "autonomous-inventory-planning",
        ],
        "result": "qualified",
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
