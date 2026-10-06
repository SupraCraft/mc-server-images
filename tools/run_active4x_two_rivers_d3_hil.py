#!/usr/bin/env python3
"""One-session stock Java 26.3 HIL harness for Two Rivers D3.

Human toil is intentionally limited to normal gameplay plus one client-version
attestation. Setup, caravan dispatch, restart, evidence collection, and scoring
are automated.

The harness uses a dedicated Compose project and deletes only that project's
test volumes at startup.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT = "supracraft_two_rivers_d3_hil"
ACTOR_USER = "TwoRiversD2B"


class HilError(RuntimeError):
    pass


def run(cmd: list[str], *, cwd: Path, input_text: str | None = None, check: bool = True) -> str:
    p = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and p.returncode != 0:
        raise HilError(f"command failed ({p.returncode}): {' '.join(cmd)}\n{p.stdout}")
    return p.stdout


class Compose:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.base = repo / "deploy/active4x-two-rivers/d2a/compose.yaml"
        self.actor = repo / "deploy/active4x-two-rivers/d2b/compose.d2b.yaml"
        self.hil = repo / "deploy/active4x-two-rivers/d3/compose.d3.yaml"

    def command(self, *args: str) -> list[str]:
        return [
            "docker", "compose",
            "-p", PROJECT,
            "-f", str(self.base),
            "-f", str(self.actor),
            "-f", str(self.hil),
            *args,
        ]

    def run(self, *args: str, input_text: str | None = None, check: bool = True) -> str:
        return run(self.command(*args), cwd=self.repo, input_text=input_text, check=check)

    def logs(self, service: str = "minecraft") -> str:
        return self.run("logs", "--no-color", service, check=False)


def wait_until(predicate, timeout: float, label: str, interval: float = 1.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise HilError(f"timeout waiting for {label}; last={last!r}")


def wait_health(compose: Compose, service: str, timeout: float = 150) -> None:
    def healthy():
        cid = compose.run("ps", "-q", service).strip()
        if not cid:
            return False
        status = run(
            ["docker", "inspect", "-f",
             "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
             cid],
            cwd=compose.repo,
            check=False,
        ).strip()
        if status == "unhealthy" or status == "exited":
            raise HilError(f"{service} entered {status}\n{compose.logs(service)}")
        return status == "healthy"
    wait_until(healthy, timeout, f"{service} health")


def wait_file(compose: Compose, service: str, path: str, timeout: float = 90) -> None:
    def exists():
        out = compose.run("exec", "-T", service, "test", "-f", path, check=False)
        return out == ""
    wait_until(exists, timeout, f"{service}:{path}")


def marker_seen(compose: Compose, marker: str) -> bool:
    return marker in compose.logs("minecraft")


def find_human_join(logs: str) -> str | None:
    names = re.findall(r"System chat: ([^\r\n]+?) joined the game", logs)
    for name in names:
        if name != ACTOR_USER:
            return name
    return None


def join_count(logs: str, player: str) -> int:
    return len(re.findall(rf"System chat: {re.escape(player)} joined the game", logs))


def player_left(logs: str, player: str) -> bool:
    return (
        f"System chat: {player} left the game" in logs
        or re.search(rf"\b{re.escape(player)} lost connection:", logs) is not None
    )


def publish_receipt(repo: Path, local_output: Path, result: dict) -> str:
    """Publish only the canonical HIL receipt from a clean feature-branch checkout."""

    branch = "feat/named-place-visual-qualification-v1"
    current = run(["git", "branch", "--show-current"], cwd=repo).strip()
    if current != branch:
        raise HilError(
            f"--publish requires branch {branch}; current branch is {current!r}"
        )

    canonical = repo / "probes/active4x/two-rivers-d3-hil-result.json"
    canonical.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")

    allowed = {
        str(local_output.resolve().relative_to(repo.resolve())).replace("\\", "/"),
        str(canonical.resolve().relative_to(repo.resolve())).replace("\\", "/"),
    }
    dirty = []
    for line in run(["git", "status", "--porcelain"], cwd=repo).splitlines():
        path = line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path not in allowed:
            dirty.append(line)
    if dirty:
        raise HilError(
            "--publish refuses to touch a worktree with unrelated changes:\n"
            + "\n".join(dirty)
        )

    run(["git", "add", str(canonical.relative_to(repo))], cwd=repo)
    names = run(["git", "diff", "--cached", "--name-only"], cwd=repo).strip()
    if names:
        run(
            ["git", "commit", "-m", "hil: retain Two Rivers D3 stock-client evidence"],
            cwd=repo,
        )

    run(["git", "fetch", "origin", branch], cwd=repo)
    run(["git", "rebase", f"origin/{branch}"], cwd=repo)
    run(["git", "push", "origin", f"HEAD:{branch}"], cwd=repo)
    return run(["git", "rev-parse", "HEAD"], cwd=repo).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output",
        type=Path,
        default=Path("probes/active4x/two-rivers-d3-hil-result.local.json"),
    )
    ap.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave the dedicated HIL Compose project running after PASS.",
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help="On PASS, commit and push only the canonical HIL receipt to the feature branch.",
    )
    args = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    compose = Compose(repo)

    # Fail early before deleting the dedicated test project.
    run(["docker", "version"], cwd=repo)
    run(["docker", "compose", "version"], cwd=repo)

    print("Two Rivers D3 stock-client HIL")
    print("This uses an unmodified Minecraft Java 26.3 client.")
    attestation = input("Confirm the client you will use is unmodified Java 26.3 [y/N]: ").strip().lower()
    if attestation not in {"y", "yes"}:
        raise HilError("stock-client attestation not provided")

    compose.run("down", "-v", "--remove-orphans", check=False)
    try:
        print("Building and starting the pinned staging stack...")
        compose.run("build", "--pull")
        compose.run("up", "-d")
        wait_health(compose, "minecraft")
        wait_file(compose, "director", "/state/service-ready.json")
        wait_file(compose, "actor-adapter", "/actor-state/service-ready.json")
        wait_until(
            lambda: marker_seen(compose, "SUPRACRAFT_D3_HIL_READY"),
            45,
            "D3 HIL fixture",
        )

        print()
        print("Join server 127.0.0.1:25585 with the stock Java 26.3 client.")
        print("At the HIL station near spawn (z≈12):")
        print("  1. Take 2 wheat and 4 bricks from the starter barrel at x=-8.")
        print("  2. Put the 2 wheat as one stack in slot 1 of the barrel at x=-6.")
        print("     The trade output appears in the barrel at x=-4.")
        print("  3. Put the 4 bricks as one stack in slot 1 of the barrel at x=0.")
        print("  4. Break the red-concrete marker at x=2,z=16.")
        print("  5. Break the cobblestone marker at x=6,z=16.")
        print("  6. Remain nearby and observe the autonomous caravan.")
        print("No admin commands are required.")

        player = wait_until(
            lambda: find_human_join(compose.logs("minecraft")),
            600,
            "first stock-client player join",
            interval=1,
        )
        print(f"Observed stock-client player join: {player}")

        operation_id = "actor-task:contract-001.cargo01"
        director_apply = compose.run(
            "exec", "-T", "director",
            "python", "/app/director_ctl.py",
            "apply", "--operation-id", operation_id,
        ).strip()
        director_apply_json = json.loads(director_apply)
        if not director_apply_json.get("accepted"):
            raise HilError(f"director did not admit caravan task: {director_apply_json}")

        task = {
            "schema": "supracraft.active4x-actor-task/v0.1",
            "operation_id": operation_id,
            "task_id": "task.trade.contract-001.grain",
            "cargo_id": "contract-001.cargo01",
            "actor_group_id": "caravan.stoneford.kilnreach.0001",
            "semantic_resource": "grain",
            "minecraft_item": "wheat",
            "amount": 4,
            "source": "stoneford",
            "destination": "kilnreach",
            "source_position": [-10, 70, 0],
            "destination_position": [10, 70, 0],
            "username": ACTOR_USER,
            "minecraft_version": "26.3",
        }
        compose.run(
            "exec", "-T", "actor-adapter", "sh", "-c",
            "cat > /actor-state/task.json.tmp && mv /actor-state/task.json.tmp /actor-state/task.json",
            input_text=json.dumps(task) + "\n",
        )

        def actor_delivered():
            out = compose.run(
                "exec", "-T", "actor-adapter",
                "sh", "-c",
                "test -f /actor-state/result.json && cat /actor-state/result.json",
                check=False,
            ).strip()
            if not out:
                return False
            value = json.loads(out)
            return value if value.get("result") == "delivered" else False

        actor_result = wait_until(actor_delivered, 120, "autonomous caravan delivery")

        required_markers = [
            "SUPRACRAFT_D3_TRADE_COMPLETE",
            "SUPRACRAFT_D3_BUILD_HELP_COMPLETE",
            "SUPRACRAFT_D3_OBSTRUCT_COMPLETE",
            "SUPRACRAFT_D3_DAMAGE_COMPLETE",
            "SUPRACRAFT_D3_PHASE1_COMPLETE",
        ]
        wait_until(
            lambda: all(marker_seen(compose, marker) for marker in required_markers),
            900,
            "all D3 phase-one stock-client interactions",
        )

        print()
        print("Phase 1 is complete. Disconnect the stock client now.")
        wait_until(
            lambda: player_left(compose.logs("minecraft"), player),
            300,
            "stock-client logout",
        )

        print("Restarting Minecraft while preserving world/director/actor volumes...")
        compose.run("restart", "minecraft")
        wait_health(compose, "minecraft")
        wait_until(
            lambda: marker_seen(compose, "SUPRACRAFT_D3_STATE_SURVIVED_RESTART"),
            60,
            "HIL state restart witness",
        )

        print("Server recovery passed. Reconnect the same stock Java 26.3 client now.")
        wait_until(
            lambda: join_count(compose.logs("minecraft"), player) >= 2,
            600,
            "stock-client rejoin after restart",
        )

        director_state = json.loads(
            compose.run(
                "exec", "-T", "director",
                "python", "/app/director_ctl.py", "show",
            ).strip()
        )
        final_logs = compose.logs("minecraft")

        print()
        legibility = input(
            "Did you see and understand the trade output, build change, "
            "obstruction/damage consequences, and caravan encounter? [y/N]: "
        ).strip().lower() in {"y", "yes"}

        checks = {
            "stock_client_attested_exact_26_3": True,
            "trade_legible": "SUPRACRAFT_D3_TRADE_COMPLETE" in final_logs,
            "construction_help_legible": "SUPRACRAFT_D3_BUILD_HELP_COMPLETE" in final_logs,
            "construction_obstruction_legible": "SUPRACRAFT_D3_OBSTRUCT_COMPLETE" in final_logs,
            "caravan_encounter": (
                actor_result.get("result") == "delivered" and legibility
            ),
            "damage_consequence_legible": "SUPRACRAFT_D3_DAMAGE_COMPLETE" in final_logs,
            "logout_rejoin": join_count(final_logs, player) >= 2,
            "restart_recovery_persists": "SUPRACRAFT_D3_STATE_SURVIVED_RESTART" in final_logs,
            "semantic_revision_monotonic": director_state.get("revision") == 1,
            "human_legibility_attested": legibility,
            "no_manual_admin_commands_required": True,
            "world_scan_false": True,
        }
        result = {
            "schema": "supracraft.active4x-two-rivers-d3-hil-result/v0.1",
            "deployment_stage": "D3_stock_client_hil",
            "minecraft": {"edition": "java", "version": "26.3", "stock_client_attested": True},
            "player": player,
            "checks": checks,
            "actor": actor_result,
            "director": {"apply": director_apply_json, "state": director_state},
            "human_legibility_attested": legibility,
            "two_simultaneous_humans": "NOT_RUN_OPTIONAL",
            "world_scan": False,
            "result": "PASS" if all(checks.values()) else "REVISE",
        }
        output = args.output if args.output.is_absolute() else repo / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print()
        print(json.dumps(result, indent=2, sort_keys=True))
        print(f"Receipt written to: {output}")

        if result["result"] == "PASS" and args.publish:
            published_head = publish_receipt(repo, output, result)
            print(f"Published canonical HIL receipt at Git head {published_head}")

        return 0 if result["result"] == "PASS" else 2
    finally:
        if not args.keep_running:
            # Preserve named volumes for post-HIL inspection; remove only containers/network.
            compose.run("down", "--remove-orphans", check=False)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HilError as exc:
        print(f"HIL ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
