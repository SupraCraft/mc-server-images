#!/usr/bin/env python3
"""OP-3 bounded actual vanilla Java 26.3 world-artifact activation and rollback.

Runs only inside a fresh, self-owned TemporaryDirectory on a free public runner.
Consumes the *inner* ZIP and source manifest from the pinned public producer,
not a GHA outer artifact; neither worlds nor game binaries are published.
Uses the existing official-server status and command oracles. This is not
COLLAGE, managed TrueNAS, online authentication, or Two Rivers acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

from minecraft_world_agent import tree_hash
from probe_core_restoration_datapack_26_3 import (
    initial_predicate, restored_predicate, send, stop_server,
    wait_for_predicate,
)
from smoke_vanilla_runtime import download_verified_server, status_query

PRODUCER = "SupraCraft/mc-server-images@7f888b5829f4e5576d5ce512d86327348c43f01e"
MEMBERS = {
    "pack.mcmeta",
    "data/minecraft/tags/function/tick.json",
    "data/supracraft_core_restore/function/tick.mcfunction",
}
PORT = 25593
MAX_BYTES = 1024 * 1024
ROOT = pathlib.Path(__file__).resolve().parents[1]


class Refused(Exception):
    pass


def require(test: bool, code: str) -> None:
    if not test:
        raise Refused(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_candidate(source: pathlib.Path, manifest: dict) -> dict:
    """Fail before writing any game-world data if a digest/schema/member differs."""
    require(source.is_file() and not source.is_symlink(), "CANDIDATE_NOT_REGULAR_FILE")
    require(type(manifest) is dict and
            manifest.get("schema") == "supracraft-vanilla-datapack-candidate/1" and
            manifest.get("classification") == "SOURCE_ARTIFACT_EXPORTED",
            "CANDIDATE_MANIFEST_SCHEMA")
    require(manifest.get("producer") == PRODUCER and
            manifest.get("kind") == "datapack" and
            manifest.get("backend") == "vanilla" and
            manifest.get("minecraft_version") == "26.3" and
            manifest.get("world_id") == "lantern-rdte" and
            manifest.get("release_id") == "lantern-core-restore-26-3" and
            manifest.get("pack_format") == [121, 0],
            "CANDIDATE_AUTHORITY_VERSION_REALM_DRIFT")
    require(manifest.get("world_save_included") is False and
            manifest.get("collage_deployed") is False,
            "CANDIDATE_SCOPE_CLAIM_DRIFT")
    body = source.read_bytes()
    require(0 < len(body) <= MAX_BYTES and
            len(body) == manifest.get("archive_size") and
            digest(body) == manifest.get("sha256"),
            "CANDIDATE_INNER_SHA256_OR_SIZE_MISMATCH")
    require(zipfile.is_zipfile(source), "CANDIDATE_NOT_ZIP")
    with zipfile.ZipFile(source, "r") as zf:
        rows = zf.infolist()
        names = [x.filename for x in rows]
        require(set(names) == MEMBERS and len(names) == len(MEMBERS),
                "CANDIDATE_MEMBER_SET_DRIFT")
        members = manifest.get("members")
        require(type(members) is list and len(members) == len(MEMBERS),
                "CANDIDATE_MEMBER_MANIFEST_DRIFT")
        by_name = {x["path"]: x for x in members if type(x) is dict and "path" in x}
        require(set(by_name) == MEMBERS, "CANDIDATE_MEMBER_IDENTITY_DRIFT")
        for info in rows:
            require(not info.is_dir() and not info.filename.startswith("/") and
                    ".." not in pathlib.PurePosixPath(info.filename).parts and
                    "\\" not in info.filename and
                    info.file_size <= MAX_BYTES and
                    (info.external_attr >> 16) & 0o170000 != 0o120000,
                    "CANDIDATE_ZIP_PATH_OR_LINK_REFUSED")
            data = zf.read(info)
            require(len(data) == by_name[info.filename].get("bytes") and
                    digest(data) == by_name[info.filename].get("sha256"),
                    "CANDIDATE_MEMBER_DIGEST_MISMATCH")
        meta = json.loads(zf.read("pack.mcmeta"))
        require(meta.get("pack", {}).get("min_format") == [121, 0] and
                meta.get("pack", {}).get("max_format") == [121, 0],
                "CANDIDATE_MC_PACK_FORMAT_DRIFT")
    return {"sha256": digest(body), "archive_size": len(body),
            "member_count": len(MEMBERS), "producer": PRODUCER}


def server_config(home: pathlib.Path) -> None:
    (home / "eula.txt").write_text("eula=true\n")
    (home / "server.properties").write_text(
        f"server-ip=127.0.0.1\nserver-port={PORT}\n"
        "online-mode=false\nwhite-list=false\nenforce-whitelist=false\n"
        "view-distance=3\nsimulation-distance=2\nmax-players=2\n"
        "spawn-protection=0\ngenerate-structures=false\n"
        "enable-rcon=false\nenable-query=false\n"
        "level-seed=4242424242\nsync-chunk-writes=true\n"
        "motd=SupraCraft OP3 disposable vanilla 26.3\n"
    )


def launch(home: pathlib.Path, jar: pathlib.Path, evidence: dict,
           step: str, handles: list) -> tuple[subprocess.Popen, pathlib.Path]:
    path = home / ("server-" + step + ".log")
    stream = path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        ["java", "-Xms512M", "-Xmx1536M", "-jar", str(jar), "nogui"],
        cwd=home, stdin=subprocess.PIPE, stdout=stream,
        stderr=subprocess.STDOUT, text=True,
    )
    handles.append((proc, stream))
    end = time.monotonic() + 150
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise Refused("VANILLA_EARLY_EXIT_" + step)
        try:
            reply = status_query("127.0.0.1", PORT, 777)
            if (reply.get("version", {}).get("protocol") == 777 and
                    "Done (" in path.read_text(errors="replace")):
                return proc, path
        except (OSError, EOFError, TimeoutError, ValueError):
            pass
        time.sleep(1)
    raise Refused("VANILLA_READY_TIMEOUT_" + step)


def oracle(proc: subprocess.Popen, log: pathlib.Path,
           predicate: str, marker: str) -> None:
    try:
        wait_for_predicate(proc, log, marker=marker,
                           predicate=predicate, timeout=12)
    except RuntimeError as exc:
        raise Refused("INDEPENDENT_SERVER_ORACLE_" + marker) from exc


def baseline_without_pack_predicate() -> str:
    return ("execute if block 0 70 0 minecraft:redstone_block "
            "if block 2 70 0 minecraft:iron_bars "
            "if block 1 70 1 minecraft:black_concrete")


def execute(artifact: pathlib.Path, manifest: dict, evidence: dict) -> dict:
    info = evidence["artifact_version_json"]
    require(info["id"] == "26.3" and info["protocol_version"] == 777 and
            info["java_version"] == 25, "OFFICIAL_263_RUNTIME_IDENTITY_DRIFT")
    contract = json.loads((ROOT / "spec/minecraft-world-activation-transaction-v1.json").read_text())
    require(contract["schema"] == "minecraft-world-activation-transaction/1" and
            contract["ordered_steps"] ==
            ["quiesce", "snapshot_current", "activate_candidate", "resume", "health_check"] and
            contract["transport_boundary"]["docker_socket"] is False and
            contract["transport_boundary"]["foundry_credentials"] is False,
            "ACTIVATION_AUTHORITY_DRIFT")
    accepted = validate_candidate(artifact, manifest)

    with tempfile.TemporaryDirectory(prefix="supracraft-op3-world-") as td:
        root = pathlib.Path(td)
        home = root / "server"
        home.mkdir()
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        server_config(home)
        staged = root / "staged" / "candidate.zip"
        staged.parent.mkdir()
        shutil.copyfile(artifact, staged)
        require(digest(staged.read_bytes()) == accepted["sha256"],
                "CANDIDATE_STAGED_DIGEST_MISMATCH")
        active = home / "world"
        snapshot = root / "snapshot" / "baseline-world"
        operations = []
        handles = []

        try:
            proc, log = launch(home, jar, evidence, "baseline", handles)
            send(proc, "forceload add 0 0")
            send(proc, "fill -2 69 -2 4 69 3 minecraft:stone")
            send(proc, "fill -2 70 -2 4 72 3 minecraft:air")
            send(proc, "setblock 0 70 0 minecraft:air")
            send(proc, "setblock 2 70 0 minecraft:iron_bars")
            send(proc, "setblock 1 70 1 minecraft:black_concrete")
            oracle(proc, log, initial_predicate(), "OP3_BASELINE_NO_PACK")
            require(stop_server(proc) == 0, "BASELINE_QUIESCE_FAILED")
            operations.append("quiesce")
            require(active.is_dir() and not (active / "datapacks/candidate.zip").exists(),
                    "BASELINE_WORLD_INVALID")
            baseline_hash = tree_hash(active)
            snapshot.parent.mkdir()
            shutil.copytree(active, snapshot, symlinks=False)
            require(tree_hash(snapshot) == baseline_hash, "SNAPSHOT_READBACK_DRIFT")
            operations.append("snapshot_current")

            # Offline world activation after verified stage and accepted snapshot.
            packs = active / "datapacks"
            packs.mkdir(exist_ok=True)
            dest = packs / "candidate.zip"
            require(not dest.exists(), "CANDIDATE_ALREADY_PRESENT")
            shutil.copyfile(staged, dest)
            require(digest(dest.read_bytes()) == accepted["sha256"],
                    "ACTIVE_CANDIDATE_DIGEST_DRIFT")
            operations.append("activate_candidate")
            proc, log = launch(home, jar, evidence, "candidate", handles)
            operations.append("resume")
            oracle(proc, log, initial_predicate(), "OP3_CANDIDATE_INITIAL")
            send(proc, "setblock 0 70 0 minecraft:redstone_block")
            oracle(proc, log, restored_predicate(), "OP3_REAL_DATAPACK_TRIGGER")
            operations.append("health_check")
            require(stop_server(proc) == 0, "CANDIDATE_QUIESCE_FAILED")
            candidate_world_hash = tree_hash(active)
            require(candidate_world_hash != baseline_hash and
                    (active / "datapacks/candidate.zip").is_file(),
                    "CANDIDATE_WORLD_NOT_PERSISTED")

            # Inject one explicit health fault *after* real positive semantic proof;
            # rollback is required, rather than treating a successful launch as safe.
            operations.append("inject_health_fault_after_positive_oracle")
            require(proc.poll() == 0, "ROLLBACK_WITH_ACTIVE_SERVER_REFUSED")
            shutil.rmtree(active)
            shutil.copytree(snapshot, active, symlinks=False)
            restored_hash = tree_hash(active)
            require(restored_hash == baseline_hash and
                    not (active / "datapacks/candidate.zip").exists(),
                    "SNAPSHOT_RESTORE_HASH_OR_RESIDUE_DRIFT")
            operations.append("restore_snapshot")

            proc, log = launch(home, jar, evidence, "rollback", handles)
            # A baseline world must NOT respond to the datapack core trigger.
            send(proc, "setblock 0 70 0 minecraft:redstone_block")
            oracle(proc, log, baseline_without_pack_predicate(),
                   "OP3_ROLLBACK_DISALLOWS_CANDIDATE_BEHAVIOR")
            require(stop_server(proc) == 0, "ROLLBACK_SHUTDOWN_FAILED")
            operations.append("rollback_recheck")
            return {
                "schema": "supracraft.op3-disposable-world-activation/1",
                "classification": "REAL_VANILLA_DATAPACK_ACTIVATION_AND_FAULT_ROLLBACK",
                "producer": accepted["producer"],
                "source_artifact_sha256": accepted["sha256"],
                "source_archive_size": accepted["archive_size"],
                "source_member_count": accepted["member_count"],
                "minecraft_version": "26.3",
                "protocol": 777,
                "server_sha256": evidence["server_artifact"]["sha256"],
                "world_id": "lantern-rdte",
                "release_id": "lantern-core-restore-26-3",
                "baseline_world_hash": baseline_hash,
                "candidate_world_hash": candidate_world_hash,
                "restored_world_hash": restored_hash,
                "steps": operations,
                "independent_server_trigger_pass": True,
                "fault_injection_rollback_pass": True,
                "rollback_absence_of_datapack_behavior_pass": True,
                "world_restored_exact_bytes_before_restart": True,
                "world_backup_separate_from_image": True,
                "client_gameplay_qualified": False,
                "full_two_rivers_world_qualified": False,
                "collage_deployed": False,
                "truenas_deployed": False,
                "human_automation_agent_parity_qualified": False,
                "physical_truenas_apply": "HOLD",
                "operational_selection": False,
                "temporary_world_auto_retired": True,
            }
        finally:
            for proc, stream in handles:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=12)
                finally:
                    stream.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=pathlib.Path, required=True)
    ap.add_argument("--manifest", type=pathlib.Path, required=True)
    ap.add_argument("--evidence", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()
    try:
        record = execute(args.candidate, json.loads(args.manifest.read_text()),
                         json.loads(args.evidence.read_text()))
        code = 0
    except Exception as exc:
        record = {
            "schema": "supracraft.op3-disposable-world-activation/1",
            "classification": "FAIL",
            "reason": type(exc).__name__,
            "failure": str(exc)[:260],
            "physical_truenas_apply": "HOLD",
            "operational_selection": False,
        }
        code = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": record["classification"],
                      "failure": record.get("failure")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
