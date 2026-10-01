#!/usr/bin/env python3
"""Exact-version Minecraft causal-microscope frontier discovery.

Discovery is intentionally separate from adapter qualification. It resolves the
current release/snapshot from Mojang metadata, verifies the exact server
artifact, detects symbol exposure, records the native Minecraft JFR catalog,
and reports conservative semantic coverage gaps. It does not promote causal
relations or create a qualified adapter manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

VERSION_MANIFEST_URL = (
    "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
)
SCHEMA = "supracraft-causal-version-discovery/1"

SEMANTIC_EVENT_FAMILIES = (
    "tick_boundary",
    "block_state_write",
    "neighbor_notify",
    "scheduled_tick_enqueue",
    "scheduled_tick_execute",
    "redstone_power_query",
    "block_power_query",
    "wire_recompute",
    "command_block_neighbor",
    "command_block_scheduled_tick",
    "command_trigger",
    "command_execute",
    "packet_send",
    "packet_receive",
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SupraCraft-causal-microscope/1"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def resolve_frontier(manifest: dict, detail_loader=fetch_json) -> list[dict]:
    latest = manifest.get("latest") or {}
    by_id = {row.get("id"): row for row in manifest.get("versions", [])}
    rows = []
    for channel, key in (("release", "release"), ("snapshot", "snapshot")):
        version_id = latest.get(key)
        if not version_id or version_id not in by_id:
            raise RuntimeError(f"missing latest {channel} version in manifest")
        index_row = by_id[version_id]
        detail = detail_loader(index_row["url"])
        java_major = int((detail.get("javaVersion") or {}).get("majorVersion", 0))
        server = (detail.get("downloads") or {}).get("server") or {}
        if java_major < 8:
            raise RuntimeError(f"{version_id}: missing/invalid Java requirement")
        if not all(server.get(k) for k in ("url", "sha1", "size")):
            raise RuntimeError(f"{version_id}: missing dedicated-server download")
        rows.append(
            {
                "channel": channel,
                "minecraft_version": version_id,
                "version_metadata_url": index_row["url"],
                "release_time": detail.get("releaseTime") or index_row.get("releaseTime"),
                "java_major": java_major,
                "server_url": server["url"],
                "server_sha1": server["sha1"],
                "server_size": int(server["size"]),
            }
        )
    if rows[0]["minecraft_version"] == rows[1]["minecraft_version"]:
        raise RuntimeError("release and snapshot frontier unexpectedly resolve identically")
    return rows


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download_verified(row: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        row["server_url"],
        headers={"User-Agent": "SupraCraft-causal-microscope/1"},
    )
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as out:
        shutil.copyfileobj(response, out)
    observed = sha1_file(target)
    if observed != row["server_sha1"]:
        raise RuntimeError(
            f"server SHA-1 mismatch expected={row['server_sha1']} observed={observed}"
        )
    if target.stat().st_size != row["server_size"]:
        raise RuntimeError(
            f"server size mismatch expected={row['server_size']} "
            f"observed={target.stat().st_size}"
        )


def _class_entries_from_zip_bytes(data: bytes) -> set[str]:
    classes: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith(".class"):
                classes.add(name)
    return classes


def server_class_entries(server_jar: Path) -> set[str]:
    classes: set[str] = set()
    with zipfile.ZipFile(server_jar) as zf:
        names = zf.namelist()
        classes.update(name for name in names if name.endswith(".class"))
        for name in names:
            if not name.endswith(".jar"):
                continue
            try:
                nested = zf.read(name)
                classes.update(_class_entries_from_zip_bytes(nested))
            except (KeyError, zipfile.BadZipFile):
                continue
    return classes


def detect_symbol_mode(classes: set[str]) -> tuple[str, list[str]]:
    witnesses = [
        "net/minecraft/server/MinecraftServer.class",
        "net/minecraft/commands/Commands.class",
        "net/minecraft/world/level/block/RedStoneWireBlock.class",
    ]
    found = [name for name in witnesses if name in classes]
    if len(found) >= 2:
        return "unobfuscated", found
    descriptive = [
        name
        for name in classes
        if name.startswith("net/minecraft/")
        and name.count("/") >= 4
        and len(Path(name).stem) > 3
    ]
    if len(descriptive) >= 100:
        return "mapped", sorted(descriptive)[:8]
    return "structural", sorted(classes)[:8]


def java_executable(name: str) -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"required JDK tool not found: {name}")
    return found


def detect_jfr_profile_option(server_jar: Path) -> str | None:
    java = java_executable("java")
    proc = subprocess.run(
        [java, "-jar", str(server_jar.resolve()), "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=45,
        check=False,
    )
    output = proc.stdout or ""
    for option in ("--jfrProfile", "--jfr-profile"):
        if option in output:
            return option
    return None


def run_native_jfr_probe(
    server_jar: Path,
    run_dir: Path,
    *,
    minecraft_jfr_profile_option: str | None,
) -> tuple[Path, str, str]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (run_dir / "server.properties").write_text(
        "\n".join(
            [
                "online-mode=false",
                "server-port=25592",
                "level-name=world",
                "max-players=1",
                "view-distance=2",
                "simulation-distance=2",
                "spawn-protection=0",
                "motd=SupraCraft causal microscope frontier discovery",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    java = java_executable("java")
    cmd = [java, "-Xms512M", "-Xmx1536M", "-jar", str(server_jar.resolve())]
    activation_mode = "minecraft_jfr_profile_flag"
    external_recording = run_dir / "external-discovery.jfr"
    if minecraft_jfr_profile_option:
        cmd.append(minecraft_jfr_profile_option)
    else:
        activation_mode = "external_jfr_fallback"
        cmd.insert(
            1,
            "-XX:StartFlightRecording="
            f"filename={external_recording.resolve()},settings=profile,dumponexit=true",
        )
    cmd.append("nogui")

    log_path = run_dir / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=run_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        deadline = time.monotonic() + 240
        ready = False
        captured: list[str] = []
        try:
            assert proc.stdout is not None
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if line:
                    captured.append(line)
                    log.write(line)
                    log.flush()
                    if "Done (" in line and "For help, type" in line:
                        ready = True
                        break
                elif proc.poll() is not None:
                    break
            if not ready:
                raise RuntimeError(
                    "modern server did not become ready; tail="
                    + "".join(captured[-40:])
                )
            time.sleep(12)
            assert proc.stdin is not None
            proc.stdin.write("stop\n")
            proc.stdin.flush()
            rest, _ = proc.communicate(timeout=90)
            if rest:
                log.write(rest)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

    if proc.returncode != 0:
        raise RuntimeError(f"server exited with rc={proc.returncode}")

    recordings = sorted(run_dir.rglob("*.jfr"), key=lambda p: p.stat().st_mtime)
    if not recordings:
        raise RuntimeError("no JFR recording produced")
    recording = recordings[-1]

    jfr = java_executable("jfr")
    meta = subprocess.run(
        [jfr, "metadata", str(recording.resolve())],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=90,
        check=True,
    ).stdout
    summary = subprocess.run(
        [jfr, "summary", str(recording.resolve())],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=90,
        check=True,
    ).stdout
    return recording, meta, summary


def parse_minecraft_jfr_event_names(metadata_text: str) -> list[str]:
    names = set(re.findall(r'@Name\("([^"]+)"\)', metadata_text))
    names.update(re.findall(r"\b(minecraft\.[A-Za-z0-9_.]+)\b", metadata_text))
    return sorted(name for name in names if name.startswith("minecraft."))


def semantic_coverage(native_events: list[str]) -> list[dict]:
    lowered = {event: event.lower() for event in native_events}
    rows = []
    for family in SEMANTIC_EVENT_FAMILIES:
        candidates: list[str] = []
        if family == "tick_boundary":
            candidates = [e for e, low in lowered.items() if "tick" in low]
        elif family == "packet_send":
            candidates = [e for e, low in lowered.items() if "packet" in low and "sent" in low]
        elif family == "packet_receive":
            candidates = [
                e for e, low in lowered.items()
                if "packet" in low and ("received" in low or "read" in low)
            ]
        status = "native_candidate" if candidates else "missing"
        rows.append(
            {
                "event_family": family,
                "status": status,
                "native_event_candidates": sorted(candidates),
                "direct_hook_required": not bool(candidates),
            }
        )
    return rows


def build_discovery_receipt(
    row: dict,
    server_jar: Path,
    *,
    symbol_mode: str,
    symbol_witnesses: list[str],
    jfr_profile_option: str | None,
    activation_mode: str,
    recording: Path,
    native_events: list[str],
) -> dict:
    return {
        "schema": SCHEMA,
        "channel": row["channel"],
        "minecraft_version": row["minecraft_version"],
        "edition": "java",
        "side": "dedicated_server",
        "fail_closed": True,
        "release_time": row.get("release_time"),
        "java_major": row["java_major"],
        "symbol_mode": symbol_mode,
        "symbol_witnesses": symbol_witnesses,
        "artifact_provenance": {
            "frontier_manifest_url": VERSION_MANIFEST_URL,
            "version_metadata_url": row["version_metadata_url"],
            "server_url": row["server_url"],
            "server_sha1_expected": row["server_sha1"],
            "server_sha1_observed": sha1_file(server_jar),
            "server_size": server_jar.stat().st_size,
        },
        "native_observability": {
            "jfr_profile_flag_detected": jfr_profile_option is not None,
            "jfr_profile_option": jfr_profile_option,
            "activation_mode": activation_mode,
            "recording_file": recording.name,
            "minecraft_event_count": len(native_events),
            "minecraft_events": native_events,
        },
        "semantic_coverage": semantic_coverage(native_events),
        "qualification_status": "discovery_only_not_adapter_qualified",
        "boundaries": [
            "native event name matching is candidate evidence, not causal coverage",
            "discovery does not qualify injected hooks",
            "exact-version adapter qualification requires stock-vs-instrumented observer-effect testing",
        ],
    }


def resolve_command(args: argparse.Namespace) -> None:
    manifest = fetch_json(args.manifest_url)
    rows = resolve_frontier(manifest)
    payload = {
        "schema": "supracraft-causal-frontier-resolution/1",
        "manifest_url": args.manifest_url,
        "resolved": rows,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    matrix = {"include": rows}
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as stream:
            stream.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


def probe_command(args: argparse.Namespace) -> None:
    manifest = fetch_json(args.manifest_url)
    rows = resolve_frontier(manifest)
    row = next(r for r in rows if r["channel"] == args.channel)
    if args.expected_version and row["minecraft_version"] != args.expected_version:
        raise RuntimeError(
            "frontier changed after resolution: "
            f"expected={args.expected_version} observed={row['minecraft_version']}"
        )
    if args.expected_java and row["java_major"] != args.expected_java:
        raise RuntimeError(
            "Java requirement changed after resolution: "
            f"expected={args.expected_java} observed={row['java_major']}"
        )

    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    server_jar = work / "server.jar"
    download_verified(row, server_jar)
    classes = server_class_entries(server_jar)
    symbol_mode, witnesses = detect_symbol_mode(classes)
    jfr_option = detect_jfr_profile_option(server_jar)
    recording, metadata, summary = run_native_jfr_probe(
        server_jar,
        work / "runtime",
        minecraft_jfr_profile_option=jfr_option,
    )
    native_events = parse_minecraft_jfr_event_names(metadata)

    (work / "jfr-metadata.txt").write_text(metadata, encoding="utf-8")
    (work / "jfr-summary.txt").write_text(summary, encoding="utf-8")
    receipt = build_discovery_receipt(
        row,
        server_jar,
        symbol_mode=symbol_mode,
        symbol_witnesses=witnesses,
        jfr_profile_option=jfr_option,
        activation_mode=(
            "minecraft_jfr_profile_flag"
            if jfr_option
            else "external_jfr_fallback"
        ),
        recording=recording,
        native_events=native_events,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


def summarize_command(args: argparse.Namespace) -> None:
    root = Path(args.root)
    docs = []
    for path in root.rglob("discovery.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("schema") == SCHEMA:
            docs.append(doc)
    by_channel = {doc["channel"]: doc for doc in docs}
    if set(by_channel) != {"release", "snapshot"}:
        raise RuntimeError(f"expected release+snapshot discovery, got {sorted(by_channel)}")

    families = {}
    for family in SEMANTIC_EVENT_FAMILIES:
        families[family] = {
            channel: next(
                row["status"]
                for row in by_channel[channel]["semantic_coverage"]
                if row["event_family"] == family
            )
            for channel in ("release", "snapshot")
        }

    summary = {
        "schema": "supracraft-causal-frontier-discovery-summary/1",
        "release": by_channel["release"]["minecraft_version"],
        "snapshot": by_channel["snapshot"]["minecraft_version"],
        "java_major": {
            channel: by_channel[channel]["java_major"]
            for channel in ("release", "snapshot")
        },
        "symbol_mode": {
            channel: by_channel[channel]["symbol_mode"]
            for channel in ("release", "snapshot")
        },
        "native_jfr_event_count": {
            channel: by_channel[channel]["native_observability"][
                "minecraft_event_count"
            ]
            for channel in ("release", "snapshot")
        },
        "semantic_coverage_status": families,
        "boundary": (
            "frontier discovery inventories native evidence only; "
            "it does not qualify direct hooks or causal relations"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest-url", default=VERSION_MANIFEST_URL)
    sub = p.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--output", required=True)
    resolve.add_argument("--github-output")
    resolve.set_defaults(func=resolve_command)

    probe = sub.add_parser("probe")
    probe.add_argument("--channel", choices=("release", "snapshot"), required=True)
    probe.add_argument("--expected-version")
    probe.add_argument("--expected-java", type=int)
    probe.add_argument("--work-dir", required=True)
    probe.add_argument("--output", required=True)
    probe.set_defaults(func=probe_command)

    summarize = sub.add_parser("summarize")
    summarize.add_argument("--root", required=True)
    summarize.add_argument("--output", required=True)
    summarize.set_defaults(func=summarize_command)
    return p


def main() -> int:
    args = parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
