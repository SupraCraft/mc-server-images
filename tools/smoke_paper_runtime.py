#!/usr/bin/env python3
"""Boot one verified Paper build and retain compact runtime evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import status_query


FILL_BASE = "https://fill.papermc.io/v3/projects/paper"
USER_AGENT = "SupraCraft-mc-server-images-probe/1.0 (https://github.com/SupraCraft/mc-server-images)"


def fetch_json(url: str, timeout: int = 120) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, destination: Path, timeout: int = 300) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        with destination.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def select_newest_build(version: str) -> dict[str, Any]:
    builds = fetch_json(f"{FILL_BASE}/versions/{version}/builds")
    if not isinstance(builds, list) or not builds:
        raise RuntimeError(f"Paper Fill returned no builds for {version}")
    candidates = [item for item in builds if isinstance(item, dict) and isinstance(item.get("id"), int)]
    if not candidates:
        raise RuntimeError(f"Paper Fill returned no numeric build ids for {version}")
    return max(candidates, key=lambda item: int(item["id"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="26.3")
    parser.add_argument("--protocol", type=int, default=777)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()

    build = select_newest_build(args.version)
    download_meta = (build.get("downloads") or {}).get("server:default") or {}
    url = download_meta.get("url")
    name = download_meta.get("name")
    expected_sha256 = (download_meta.get("checksums") or {}).get("sha256")
    expected_size = download_meta.get("size")
    if not all([url, name, expected_sha256]) or expected_size is None:
        raise RuntimeError("Paper Fill build lacks complete server:default provenance")

    java_version = subprocess.run(
        ["java", "-version"],
        text=True,
        capture_output=True,
        check=True,
    )
    java_text = (java_version.stderr or java_version.stdout).strip()

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"paper-{args.version}-") as tmp:
        root = Path(tmp)
        paper_jar = root / "paper.jar"
        download(str(url), paper_jar)

        actual_sha256 = sha256_file(paper_jar)
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Paper SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        actual_size = paper_jar.stat().st_size
        if actual_size != int(expected_size):
            raise RuntimeError(
                f"Paper size mismatch: expected {expected_size}, got {actual_size}"
            )

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join(
                [
                    "online-mode=false",
                    "server-port=25565",
                    "view-distance=2",
                    "simulation-distance=2",
                    "spawn-protection=0",
                    "max-players=1",
                    "enable-rcon=false",
                    "enable-query=false",
                    "motd=SupraCraft Paper 26.3 qualification",
                    "",
                ]
            ),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    "java",
                    "-Xms512M",
                    "-Xmx1536M",
                    "-jar",
                    str(paper_jar),
                    "--nogui",
                ],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            status: dict[str, Any] | None = None
            last_error = ""
            deadline = time.monotonic() + args.timeout_seconds
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    status = status_query("127.0.0.1", 25565, args.protocol)
                    observed = int(status.get("version", {}).get("protocol", -1))
                    if observed == args.protocol:
                        break
                    last_error = f"status protocol {observed} != expected {args.protocol}"
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(1)

            if status is None or int(status.get("version", {}).get("protocol", -1)) != args.protocol:
                if process.poll() is None and process.stdin is not None:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                log.flush()
                log.seek(0)
                tail = log.read()[-8000:]
                raise RuntimeError(
                    "Paper never produced protocol-777 status; "
                    f"last_error={last_error!r}; exit={process.returncode}; tail={tail!r}"
                )

            ready_elapsed = time.monotonic() - started

            if process.stdin is None:
                raise RuntimeError("Paper stdin unavailable for graceful stop")
            process.stdin.write("stop\n")
            process.stdin.flush()
            try:
                exit_code = process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        if exit_code != 0:
            raise RuntimeError(f"Paper exited {exit_code} after matching status")
        error_lines = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if error_lines:
            raise RuntimeError(
                "Paper emitted ERROR log lines: " + " | ".join(error_lines[-20:])
            )

    result = {
        "schema": "supracraft-paper-runtime-smoke/1",
        "minecraft_version": args.version,
        "expected_protocol": args.protocol,
        "paper_build": {
            "id": build.get("id"),
            "time": build.get("time"),
            "channel": build.get("channel"),
            "name": name,
            "url": url,
            "sha256": actual_sha256,
            "size": actual_size,
        },
        "java_runtime": java_text,
        "status_response": status,
        "ready_elapsed_seconds": round(ready_elapsed, 3),
        "graceful_stop_exit_code": exit_code,
        "done_log_observed": "Done (" in server_log,
        "error_log_count": len(error_lines),
        "classification": (
            "stable-qualified-smoke"
            if str(build.get("channel", "")).upper() == "STABLE"
            else "rdte-nonstable-smoke"
        ),
        "server_log_tail": server_log[-4000:],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps({
        "version": args.version,
        "protocol": args.protocol,
        "paper_build": build.get("id"),
        "paper_channel": build.get("channel"),
        "classification": result["classification"],
        "ready_elapsed_seconds": result["ready_elapsed_seconds"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
