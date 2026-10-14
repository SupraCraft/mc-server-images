#!/usr/bin/env python3
"""Qualify deterministic four-worker fixture-assisted MCBUILD scheduling."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query


PORT = 25572
WORKERS = 4
BOT_PREFIX = "SupraPar"


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
                "max-players=8",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "sync-chunk-writes=true",
                "motd=SupraCraft four-worker MCBUILD qualification",
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


class WorkerPeer:
    def __init__(
        self,
        worker_index: int,
        process: subprocess.Popen[str],
        events: queue.Queue[tuple[int, dict[str, Any]]],
    ) -> None:
        if (
            process.stdout is None
            or process.stdin is None
            or process.stderr is None
        ):
            raise RuntimeError("worker pipes unavailable")
        self.worker_index = worker_index
        self.process = process
        self.stdout = process.stdout
        self.stdin = process.stdin
        self.stderr = process.stderr
        self.events = events
        self.stderr_tail: deque[str] = deque(maxlen=200)
        self.stderr_lock = threading.Lock()
        self.reader_error: str | None = None
        threading.Thread(
            target=self._read_stdout,
            name=f"parallel-worker-{worker_index}-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            name=f"parallel-worker-{worker_index}-stderr",
            daemon=True,
        ).start()

    def _read_stdout(self) -> None:
        try:
            for line in self.stdout:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    self.events.put((self.worker_index, value))
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

    def send(self, value: dict[str, Any]) -> None:
        self.stdin.write(json.dumps(value, sort_keys=True) + "\n")
        self.stdin.flush()

    def diagnostic(self) -> dict[str, Any]:
        with self.stderr_lock:
            stderr_tail = "".join(list(self.stderr_tail))[-4000:]
        return {
            "worker_index": self.worker_index,
            "worker_poll": self.process.poll(),
            "reader_error": self.reader_error,
            "stderr_tail": stderr_tail,
        }


def verify_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != "mcbuild/v0.1-public-fixture":
        raise ValueError("unsupported synthetic MCBUILD schema")
    actions = plan.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("plan requires actions")

    seen: set[str] = set()
    targets: dict[tuple[int, int, int], str] = {}
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("invalid action")
        action_id = action.get("id")
        if not isinstance(action_id, str) or action_id in seen:
            raise ValueError("invalid or duplicate action id")
        at = tuple(map(int, action["at"]))
        if at in targets:
            raise ValueError(f"duplicate target {at}")
        for dep in action.get("depends_on", []):
            if dep not in seen:
                raise ValueError(
                    f"dependency {dep!r} for {action_id!r} is not prior"
                )
        reference = action.get("reference", {})
        if reference.get("kind") == "prior-target":
            ref_at = tuple(map(int, reference["at"]))
            ref_id = targets.get(ref_at)
            if ref_id is None or ref_id not in action.get("depends_on", []):
                raise ValueError(
                    f"reference for {action_id!r} is not an explicit "
                    "completed dependency"
                )
        seen.add(action_id)
        targets[at] = action_id


def marker(index: int) -> str:
    return f"SUPRACRAFT_PAR_ACTION_{index:02d}_OK"


def support_marker(index: int) -> str:
    return f"SUPRACRAFT_PAR_SUPPORT_{index:02d}_CLEARED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    if args.workers != WORKERS:
        raise ValueError("this bounded qualification requires exactly 4 workers")

    evidence = json.loads(args.evidence.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("qualification requires Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    verify_plan(plan)
    actions = plan["actions"]
    index_by_id = {action["id"]: i for i, action in enumerate(actions)}

    with tempfile.TemporaryDirectory(prefix="mcbuild-parallel-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)
        write_server_config(root)

        log_path = root / "server.log"
        worker_processes: list[subprocess.Popen[str]] = []
        peers: list[WorkerPeer] = []
        events: queue.Queue[tuple[int, dict[str, Any]]] = queue.Queue()
        server_exit: int | None = None

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
                send_server(server, "team add SupraParallel")
                send_server(
                    server,
                    "team modify SupraParallel collisionRule never",
                )
                time.sleep(1)

                for worker_index in range(WORKERS):
                    bot_name = f"{BOT_PREFIX}{worker_index}"
                    result_path = root / f"worker-{worker_index}.json"
                    env = dict(os.environ)
                    env.update(
                        {
                            "MC_PORT": str(PORT),
                            "BOT_NAME": bot_name,
                            "BOT_RESULT_FILE": str(result_path),
                        }
                    )
                    process = subprocess.Popen(
                        [
                            "node",
                            str(
                                Path(__file__).with_name(
                                    "probe_mcbuild_parallel_worker.js"
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
                    worker_processes.append(process)
                    peers.append(WorkerPeer(worker_index, process, events))

                ready: set[int] = set()
                deadline = time.monotonic() + 60
                while len(ready) < WORKERS:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("timeout waiting for worker readiness")
                    try:
                        worker_index, msg = events.get(
                            timeout=min(1.0, remaining)
                        )
                    except queue.Empty:
                        for peer in peers:
                            if peer.process.poll() is not None:
                                raise RuntimeError(
                                    "worker exited before readiness: "
                                    + json.dumps(
                                        peer.diagnostic(), sort_keys=True
                                    )
                                )
                        continue
                    if msg.get("type") == "error":
                        raise RuntimeError(
                            f"worker {worker_index} readiness error: "
                            + str(msg.get("error"))
                        )
                    if (
                        msg.get("type") != "ready"
                        or int(msg.get("protocol", -1)) != protocol
                    ):
                        raise RuntimeError(
                            f"unexpected worker readiness message: {msg!r}"
                        )
                    ready.add(worker_index)

                for worker_index in range(WORKERS):
                    bot_name = f"{BOT_PREFIX}{worker_index}"
                    send_server(
                        server,
                        f"team join SupraParallel {bot_name}",
                    )
                    send_server(server, f"gamemode survival {bot_name}")

                pending = {action["id"] for action in actions}
                completed: set[str] = set()
                idle = set(range(WORKERS))
                in_flight: dict[int, dict[str, Any]] = {}
                controller_receipts: list[dict[str, Any]] = []
                max_inflight = 0
                active_started_ns = time.perf_counter_ns()

                while len(completed) < len(actions):
                    while idle:
                        ready_actions = [
                            action
                            for action in actions
                            if action["id"] in pending
                            and all(
                                dep in completed
                                for dep in action.get("depends_on", [])
                            )
                        ]
                        if not ready_actions:
                            break

                        action = ready_actions[0]
                        worker_index = min(idle)
                        bot_name = f"{BOT_PREFIX}{worker_index}"
                        index = index_by_id[action["id"]]
                        pos = action["bot_position"]
                        yaw = float(action.get("bot_yaw", 0))
                        pitch = float(action.get("bot_pitch", 0))
                        support_at = [
                            int(pos[0]),
                            int(pos[1]) - 1,
                            int(pos[2]),
                        ]

                        prepare_started_ns = time.perf_counter_ns()
                        send_server(
                            server,
                            f"setblock {support_at[0]} {support_at[1]} "
                            f"{support_at[2]} minecraft:barrier",
                        )
                        send_server(server, f"clear {bot_name}")
                        send_server(
                            server,
                            f"give {bot_name} minecraft:{action['item']} 1",
                        )
                        send_server(
                            server,
                            f"tp {bot_name} {pos[0]} {pos[1]} {pos[2]} "
                            f"{yaw} {pitch}",
                        )
                        peers[worker_index].send(
                            {
                                "type": "execute",
                                "index": index,
                                "action": action,
                            }
                        )
                        dispatched_ns = time.perf_counter_ns()

                        receipt = {
                            "index": index,
                            "id": action["id"],
                            "worker_index": worker_index,
                            "bot_name": bot_name,
                            "fixture_support_at": support_at,
                            "controller_prepare_ms": round(
                                (
                                    dispatched_ns - prepare_started_ns
                                )
                                / 1_000_000,
                                3,
                            ),
                            "_dispatched_ns": dispatched_ns,
                        }
                        in_flight[worker_index] = receipt
                        pending.remove(action["id"])
                        idle.remove(worker_index)
                        max_inflight = max(max_inflight, len(in_flight))

                    if not in_flight and pending:
                        unresolved = sorted(pending)
                        raise RuntimeError(
                            "scheduler deadlock with pending actions: "
                            + json.dumps(unresolved)
                        )

                    try:
                        worker_index, msg = events.get(timeout=40)
                    except queue.Empty:
                        diagnostics = [
                            peers[i].diagnostic()
                            for i in sorted(in_flight)
                        ]
                        raise RuntimeError(
                            "timeout waiting for parallel worker: "
                            + json.dumps(diagnostics, sort_keys=True)
                        )

                    kind = msg.get("type")
                    if kind == "error":
                        raise RuntimeError(
                            f"worker {worker_index} error: "
                            + str(msg.get("error"))
                        )
                    if kind != "placed":
                        raise RuntimeError(
                            f"unexpected worker message {msg!r}"
                        )
                    if worker_index not in in_flight:
                        raise RuntimeError(
                            f"worker {worker_index} has no assigned action"
                        )

                    receipt = in_flight.pop(worker_index)
                    if (
                        msg.get("id") != receipt["id"]
                        or int(msg.get("index", -1)) != receipt["index"]
                    ):
                        raise RuntimeError(
                            "worker/action identity mismatch"
                        )
                    placed_ns = time.perf_counter_ns()
                    receipt["dispatch_to_placed_ms"] = round(
                        (
                            placed_ns - int(receipt.pop("_dispatched_ns"))
                        )
                        / 1_000_000,
                        3,
                    )
                    receipt["worker_elapsed_ms"] = round(
                        float(msg["worker_elapsed_ms"]), 3
                    )

                    support_at = receipt["fixture_support_at"]
                    send_server(
                        server,
                        f"setblock {support_at[0]} {support_at[1]} "
                        f"{support_at[2]} minecraft:air",
                    )
                    receipt["fixture_support_cleanup_requested"] = True
                    controller_receipts.append(receipt)
                    completed.add(receipt["id"])
                    idle.add(worker_index)

                active_plan_ms = round(
                    (time.perf_counter_ns() - active_started_ns) / 1_000_000,
                    3,
                )

                if max_inflight != WORKERS:
                    raise RuntimeError(
                        f"four-worker frontier not exercised: {max_inflight}"
                    )

                for peer in peers:
                    peer.send({"type": "stop"})

                stopped: set[int] = set()
                deadline = time.monotonic() + 20
                while len(stopped) < WORKERS:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("timeout waiting for worker stop")
                    worker_index, msg = events.get(
                        timeout=min(1.0, remaining)
                    )
                    if msg.get("type") == "error":
                        raise RuntimeError(
                            f"worker {worker_index} stop error: "
                            + str(msg.get("error"))
                        )
                    if msg.get("type") == "stopped":
                        stopped.add(worker_index)

                worker_results: list[dict[str, Any]] = []
                for worker_index, process in enumerate(worker_processes):
                    try:
                        worker_exit = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        worker_exit = process.wait(timeout=5)
                    if worker_exit != 0:
                        raise RuntimeError(
                            f"worker {worker_index} exit {worker_exit}: "
                            + json.dumps(
                                peers[worker_index].diagnostic(),
                                sort_keys=True,
                            )
                        )
                    result_path = root / f"worker-{worker_index}.json"
                    if not result_path.exists():
                        raise RuntimeError(
                            f"worker {worker_index} produced no result"
                        )
                    worker_result = json.loads(
                        result_path.read_text("utf-8")
                    )
                    if not worker_result.get("completed"):
                        raise RuntimeError(
                            f"worker {worker_index} result incomplete"
                        )
                    worker_results.append(worker_result)

                if sum(
                    len(result.get("actions", []))
                    for result in worker_results
                ) != len(actions):
                    raise RuntimeError("worker action receipt count mismatch")
                if any(
                    len(result.get("actions", [])) == 0
                    for result in worker_results
                ):
                    raise RuntimeError("not every worker executed an action")

                receipts_by_id = {
                    receipt["id"]: receipt
                    for receipt in controller_receipts
                }
                for index, action in enumerate(actions):
                    x, y, z = map(int, action["at"])
                    send_server(
                        server,
                        f"execute if block {x} {y} {z} "
                        f"{action['desired_state']} run say {marker(index)}",
                    )
                    support_at = receipts_by_id[action["id"]][
                        "fixture_support_at"
                    ]
                    send_server(
                        server,
                        f"execute if block {support_at[0]} "
                        f"{support_at[1]} {support_at[2]} minecraft:air "
                        f"run say {support_marker(index)}",
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
                for process in worker_processes:
                    if process.poll() is None:
                        process.kill()
                        try:
                            process.wait(timeout=5)
                        except Exception:
                            pass
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
            for index in range(len(actions))
            if marker(index) not in server_log
        ]
        missing_support_cleanup = [
            support_marker(index)
            for index in range(len(actions))
            if support_marker(index) not in server_log
        ]
        if missing_markers or missing_support_cleanup:
            raise RuntimeError(
                "independent server oracle failed: "
                f"states={missing_markers}, "
                f"fixture_support_cleanup={missing_support_cleanup}"
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

    worker_action_counts = [
        len(result["actions"]) for result in worker_results
    ]
    result = {
        "schema": (
            "supracraft.fixture-assisted-parallel-mcbuild-"
            "qualification/v0.1"
        ),
        "minecraft": {
            "edition": "java",
            "version": "26.3",
            "protocol": protocol,
            "world_version": int(info["world_version"]),
        },
        "plan": {
            "schema": plan["schema"],
            "sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "actions": len(actions),
        },
        "scheduler": {
            "workers": WORKERS,
            "policy": (
                "lowest-plan-index-ready-action-to-lowest-idle-worker"
            ),
            "dependency_authority": "plan.depends_on",
            "placement_retries": 0,
            "max_inflight_observed": max_inflight,
            "worker_action_counts": worker_action_counts,
        },
        "controller": {
            "positioning": (
                "server-console-teleport-with-temporary-barrier-support"
            ),
            "inventory_provisioning": "server-console-clear-and-give",
            "collision_rule": "team-collisionRule-never",
            "fixture_support_cleanup": "server-console-setblock-air",
            "receipts": sorted(
                controller_receipts,
                key=lambda receipt: int(receipt["index"]),
            ),
        },
        "timing": {
            "clock": "time.perf_counter_ns",
            "active_plan_ms": active_plan_ms,
            "dispatch_to_placed_ms": [
                receipt["dispatch_to_placed_ms"]
                for receipt in controller_receipts
            ],
        },
        "workers": worker_results,
        "official_server_verified_actions": len(actions),
        "official_server_verified_fixture_support_cleanup": len(actions),
        "status_protocol": int(
            status.get("version", {}).get("protocol", -1)
        ),
        "qualified_capabilities": [
            "execution.position.fixture-controller",
            "inventory.provision.fixture-controller",
            "plan.execute.parallel.fixture-assisted.4-worker",
        ],
        "explicit_exclusions": [
            "pathfinding",
            "survival-resource-acquisition",
            "autonomous-inventory-planning",
            "generalized-worker-count",
            "private-5533-action-end-to-end-realization",
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
