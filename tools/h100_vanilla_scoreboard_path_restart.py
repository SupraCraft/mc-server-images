#!/usr/bin/env python3
"""H100 exact official vanilla 26.3 scoreboard storage/restart oracle.

Operates only in its fresh tempfile disposable Java-server world.
It establishes location and same-save score reloading, not Lantern story completion.
"""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import re
import subprocess
import tempfile
import time

from smoke_vanilla_runtime import download_verified_server, status_query

SCHEMA = "supracraft-h100-vanilla-scoreboard-restart/v1"
PORT = 25597
VERSION = "26.3"
PROTOCOL = 777
GOOD = "world/data/minecraft/scoreboard.dat"
LEGACY = "world/data/scoreboard.dat"
SCORE_OBJECTIVE = "h100"
SCORE_HOLDER = "#restored"
SCORE_VALUE = 1
LOG_ACCEPT = re.compile(r"\[Server\]:\s*H100_SCORE_(PRE|POST)_VERIFIED\b")
LIMIT = 2_000_000


def file_sha256(source):
    h=hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(65536),b""):
            h.update(block)
    return h.hexdigest()


def qualify_scoreboard_storage(root):
    base=pathlib.Path(root)
    good=base/GOOD
    legacy=base/LEGACY
    if legacy.is_symlink() or legacy.exists():
        raise ValueError("LEGACY_SCOREBOARD_PATH_PRESENT")
    if good.is_symlink() or not good.is_file():
        raise ValueError("NAMESPACED_SCOREBOARD_PATH_MISSING")
    length=good.stat().st_size
    if not 20 <= length <= LIMIT:
        raise ValueError("SCOREBOARD_NBT_LENGTH_INVALID")
    if good.read_bytes()[:2]!=b"\x1f\x8b":
        raise ValueError("SCOREBOARD_NOT_GZIP_NBT")
    try:
        with gzip.open(good,"rb") as stream:
            raw=stream.read(LIMIT+1)
    except (OSError,EOFError) as exc:
        raise ValueError("SCOREBOARD_NBT_DECODE_REFUSED") from exc
    if len(raw)>LIMIT or b"h100" not in raw or b"#restored" not in raw:
        raise ValueError("SCOREBOARD_NBT_MARKERS_MISSING_OR_UNBOUNDED")
    return {"relative_path":GOOD,"file_sha256":file_sha256(good),
            "compressed_bytes":length, "decompressed_bytes":len(raw),
            "legacy_path_absent":True,
            "nbt_marker_only_not_value_validation":True}


def write_properties(root):
    (root/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (root/"server.properties").write_text("\n".join([
        "server-ip=127.0.0.1",f"server-port={PORT}", "online-mode=false",
        "max-players=1","view-distance=3","simulation-distance=2",
        "spawn-protection=0","enable-rcon=false","enable-query=false",
        "generate-structures=false","level-seed=4242424242",
        "sync-chunk-writes=true","motd=H100 disposable scoreboard source qualification",
        ""
    ]),encoding="utf-8")


def spawn_server(root,jar,log_path):
    log=log_path.open("w",encoding="utf-8")
    process=subprocess.Popen(["java","-Xms256M","-Xmx1280M",
                              "-jar",str(jar),"nogui"],
                             stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,
                             text=True,cwd=root)
    return process, log


def command(proc,value):
    if proc.stdin is None or proc.poll() is not None:
        raise RuntimeError("SERVER_STDIN_OR_PROCESS_UNAVAILABLE")
    proc.stdin.write(value+"\n")
    proc.stdin.flush()


def wait_protocol(proc,timeout=150):
    start=time.monotonic()
    last=""
    while time.monotonic()-start<timeout:
        if proc.poll() is not None:
            raise RuntimeError(f"SERVER_EARLY_EXIT:{proc.returncode}")
        try:
            status=status_query("127.0.0.1",PORT,PROTOCOL)
            if int(status.get("version",{}).get("protocol",-1))==PROTOCOL:
                return status
            last="PROTOCOL_NOT_777"
        except (OSError,ValueError,EOFError) as exc:
            last=str(exc)[:160]
        time.sleep(0.5)
    raise RuntimeError("SERVER_STATUS_TIMEOUT:"+last)


def marker_present(path,expected):
    # A source-line reader: must be [Server] message, not an echoed command.
    data=path.read_text(encoding="utf-8",errors="replace")
    good={m.group(1) for line in data.splitlines()
          for m in [LOG_ACCEPT.search(line)] if m}
    return expected in good


def require_score(proc,log_path,phase):
    marker=f"H100_SCORE_{phase}_VERIFIED"
    test=f"execute if score {SCORE_HOLDER} {SCORE_OBJECTIVE} matches {SCORE_VALUE} run say {marker}"
    start=time.monotonic()
    while time.monotonic()-start<16:
        command(proc,test)
        time.sleep(0.5)
        if marker_present(log_path,phase):
            return round(time.monotonic()-start,3)
    raise RuntimeError(f"AUTHORITATIVE_SCORE_RELOAD_NOT_OBSERVED:{phase}")


def stop(proc):
    if proc.poll() is None:
        command(proc,"save-all flush")
        time.sleep(1)
        command(proc,"stop")
    try:
        rc=proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        raise RuntimeError("SERVER_FORCED_STOP")
    if rc!=0:
        raise RuntimeError(f"SERVER_EXIT_NONZERO:{rc}")


def run(evidence):
    if evidence.get("artifact_version_json",{}).get("id")!=VERSION or int(
        evidence["artifact_version_json"].get("protocol_version",-1))!=PROTOCOL:
        raise ValueError("EXACT_26_3_PROTOCOL_777_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="h100-scoreboard-world-") as td:
        root=pathlib.Path(td)
        jar=root/"server.jar"
        download_verified_server(evidence,jar)
        if file_sha256(jar)!=evidence["server_artifact"]["sha256"]:
            raise RuntimeError("EXACT_SERVER_SHA256_MISMATCH")
        write_properties(root)
        logs=[]
        phase_times={}
        receipts=[]
        for phase in ("PRE","POST"):
            log_path=root/f"server-{phase.lower()}.log"
            proc,log=spawn_server(root,jar,log_path)
            try:
                status=wait_protocol(proc)
                if phase=="PRE":
                    command(proc,f"scoreboard objectives add {SCORE_OBJECTIVE} dummy")
                    command(proc,f"scoreboard players set {SCORE_HOLDER} {SCORE_OBJECTIVE} {SCORE_VALUE}")
                phase_times[phase]=require_score(proc,log_path,phase)
                stop(proc)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
                log.close()
            if int(status.get("version",{}).get("protocol",-1))!=PROTOCOL:
                raise RuntimeError("SERVER_PROTOCOL_ID_CHANGED")
            if any("/ERROR]:" in line for line in log_path.read_text(encoding="utf-8",errors="replace").splitlines()):
                raise RuntimeError("SERVER_LOG_ERROR_DETECTED")
            receipts.append(qualify_scoreboard_storage(root))
            logs.append({"phase":phase,"marker":f"H100_SCORE_{phase}_VERIFIED",
                         "score_observed_from_server":True})
        return {
            "schema":SCHEMA,
            "status":"OFFICIAL_26_3_SCOREBOARD_PATH_AND_RESTART_ACCEPTED_BOUNDED",
            "official_server_sha256":evidence["server_artifact"]["sha256"],
            "version":VERSION,"protocol":PROTOCOL,
            "first":receipts[0],"after_restart":receipts[1],
            "authoritative_oracles":logs,"latency_seconds":phase_times,
            "disposable_world":True, "real_official_server_executed":True,
            "restoration_story_verified":False,"marked_core_custody_verified":False,
            "stock_client_verified":False,"human_accepted":False,
        }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",type=pathlib.Path,required=True)
    parser.add_argument("--out",type=pathlib.Path,required=True)
    args=parser.parse_args()
    try:
        r=run(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError,ValueError,RuntimeError,KeyError) as exc:
        r={"schema":SCHEMA,"status":"FIRST_LIVE_REP_RED",
           "error":str(exc)[:500],"restoration_story_verified":False,
           "stock_client_verified":False}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        raise
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(r,sort_keys=True,indent=2))


if __name__=="__main__":
    main()
