#!/usr/bin/env python3
"""Real status data-plane rep: exact Velocity 4.2.0 -> Paper 26.3 on loopback.

Source-only site intent is not enough: prove the proxy obtains its ping
description and version from the actual backend, loses it when the backend
stops, and recovers after backend restart with its same world.

This is NOT player login, modern forwarding, VIP authentication, vanilla or
TrueNAS provider qualification. Deliberately use offline mode ONLY in
127.0.0.1 ephemeral public CI; never expose an unauthenticated backend.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import zipfile

from smoke_vanilla_runtime import status_query
from resolve_operational_runtime_versions import Refused, official_url, UA

ROOT=pathlib.Path(__file__).resolve().parents[1]
PINS=ROOT/"spec/rdte-current-artifact-pins-v1.json"
PROXY_PORT=25577
BACKEND_PORT=25586
MOTD="SUPRACRAFT_263_PAPER_BACKEND_RDTE"
MAX_JAR=130*1024*1024


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Refused(reason)


def load_pins() -> dict:
    data=json.loads(PINS.read_text())
    require(data["schema"]=="supracraft.rdte-runtime-pins/1"
            and data["minecraft"]["version"]=="26.3"
            and data["minecraft"]["protocol"]==777
            and data["paper"]["build"]==177
            and data["velocity"]["build"]==30
            and data["velocity"]["version"]=="4.2.0"
            and data["proxy_link"]["modern_forwarding_qualified"] is False,
            "EXACT_RUNTIME_PIN_DRIFT")
    return data


def pinned_artifact(candidate: dict, expected: dict, target: pathlib.Path) -> str:
    require(candidate["build"]==expected["build"],
            "OFFICIAL_BUILD_CHANGED")
    require(candidate["version"]==expected.get("minecraft_version",
                                              expected.get("version")),
            "OFFICIAL_PRODUCT_VERSION_CHANGED")
    url=candidate["url"]
    require(official_url(url,"papermc.io"),"UNTRUSTED_ARTIFACT_HOST")
    observed=hashlib.sha256()
    count=0
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=90) as stream, target.open("wb") as out:
        require(official_url(stream.url,"papermc.io"),"UNTRUSTED_ARTIFACT_REDIRECT")
        while True:
            data=stream.read(1024*1024)
            if not data:
                break
            count+=len(data)
            require(count<=MAX_JAR,"ARTIFACT_OVERSIZED")
            observed.update(data)
            out.write(data)
    digest=observed.hexdigest()
    require(digest==expected["sha256"]
            and (not candidate.get("reported_sha256")
                 or candidate["reported_sha256"]==digest),
            "PINNED_ARTIFACT_SHA256_MISMATCH")
    require(count>1024*1024 and zipfile.is_zipfile(target),
            "ARTIFACT_NOT_JAVA_ARCHIVE")
    return digest


def replace_exact_value(source: str, key: str, value: str) -> str:
    pattern=r"(?m)^"+re.escape(key)+r"\s*=\s*[^\n]+$"
    result,count=re.subn(pattern,key+" = "+value,source)
    require(count==1,"VELOCITY_TEMPLATE_KEY_DRIFT_"+key)
    return result


def make_velocity_config(default: str) -> str:
    """Derive the 4.2.0 config from the actual pinned JAR's bundled template."""
    s=default
    for key,val in (
        ("bind",'"127.0.0.1:25577"'),
        ("online-mode","false"),
        ("force-key-authentication","false"),
        ("player-info-forwarding-mode",'"NONE"'),
    ):
        s=replace_exact_value(s,key,val)
    replacement=("[ping-passthrough]\n"
                 "version = true\nplayers = false\n"
                 "description = true\nfavicon = false\nmodinfo = false\n\n")
    s,n=re.subn(r"(?ms)^\[ping-passthrough\]\n.*?(?=^\[packet-limiter\])",
                replacement,s)
    require(n==1,"VELOCITY_PING_CONFIG_SCHEMA_DRIFT")
    s,n=re.subn(r"(?ms)^\[servers\]\n.*?(?=^\[forced-hosts\])",
                ('[servers]\n'
                 'lobby = "127.0.0.1:25586"\n'
                 'try = ["lobby"]\n\n'),s)
    require(n==1,"VELOCITY_SERVERS_SCHEMA_DRIFT")
    s,n=re.subn(r"(?ms)^\[forced-hosts\]\n.*?(?=^\[advanced\])",
                '[forced-hosts]\n\n',s)
    require(n==1,"VELOCITY_FORCED_HOSTS_SCHEMA_DRIFT")
    parsed=tomllib.loads(s)
    require(parsed["bind"]=="127.0.0.1:25577"
            and parsed["online-mode"] is False
            and parsed["player-info-forwarding-mode"].upper()=="NONE"
            and parsed["ping-passthrough"]["description"] is True
            and parsed["servers"]["try"]==["lobby"]
            and parsed["servers"]["lobby"]=="127.0.0.1:25586"
            and parsed["forced-hosts"]=={},
            "VELOCITY_GENERATED_CONFIGURATION_INVALID")
    return s


def wait_status(proc: subprocess.Popen, port: int, expected: str, timeout=150):
    started=time.monotonic()
    last="no socket"
    while time.monotonic()-started < timeout:
        if proc.poll() is not None:
            raise Refused("SERVICE_EARLY_EXIT_"+expected)
        try:
            result=status_query("127.0.0.1",port,777)
            protocol=result.get("version",{}).get("protocol")
            if protocol==777:
                return result
            last="wrong protocol"
        except (OSError, EOFError, ValueError, TimeoutError):
            last="transient connection"
        time.sleep(1)
    raise Refused("SERVICE_STATUS_TIMEOUT_"+expected+"_"+last)


def backend_status(status: dict) -> bool:
    return MOTD in json.dumps(status.get("description",""),sort_keys=True)


def graceful_stop(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        raise Refused(name+"_DIED")
    require(proc.stdin is not None,name+"_STDIN_UNAVAILABLE")
    proc.stdin.write("stop\n" if name=="PAPER" else "shutdown\n")
    proc.stdin.flush()
    require(proc.wait(timeout=50)==0,name+"_STOP_FAILURE")


def execute(discovery: dict) -> dict:
    require(discovery.get("classification")=="READ_ONLY_CANDIDATES_DISCOVERED",
            "OFFICIAL_SOURCE_NOT_QUALIFIED")
    pins=load_pins()
    with tempfile.TemporaryDirectory(prefix="supracraft-velocity-paper-link-") as td:
        root=pathlib.Path(td)
        p_dir=root/"paper";v_dir=root/"velocity"
        p_dir.mkdir();v_dir.mkdir()
        p_jar=p_dir/"paper.jar";v_jar=v_dir/"velocity.jar"
        pdigest=pinned_artifact(discovery["stable"]["paper"],pins["paper"],p_jar)
        vdigest=pinned_artifact(discovery["stable"]["velocity"],pins["velocity"],v_jar)
        with zipfile.ZipFile(v_jar) as archive:
            require("default-velocity.toml" in archive.namelist(),
                    "VELOCITY_BUNDLED_TEMPLATE_MISSING")
            template=archive.read("default-velocity.toml").decode("utf-8")
        (v_dir/"velocity.toml").write_text(make_velocity_config(template))
        # Runtime-only, random, not logged or emitted. NONE forwarding phase
        # is an isolated L3 ping qualification, NOT an auth credential.
        secret=v_dir/"forwarding.secret"
        secret.write_bytes(os.urandom(32).hex().encode()+b"\n")
        secret.chmod(0o600)
        (p_dir/"eula.txt").write_text("eula=true\n")
        (p_dir/"server.properties").write_text(
            f"server-ip=127.0.0.1\nserver-port={BACKEND_PORT}\n"
            "online-mode=false\nmax-players=1\nview-distance=2\nsimulation-distance=2\n"
            "spawn-protection=0\nenable-rcon=false\nenable-query=false\n"
            f"motd={MOTD}\n"
        )
        processes=[]
        def start_jar(jar,home,log):
            handle=log.open("w",encoding="utf-8")
            proc=subprocess.Popen(
                ["java","-Xms256M","-Xmx1536M","-jar",str(jar),"nogui"],
                cwd=home,stdin=subprocess.PIPE,stdout=handle,
                stderr=subprocess.STDOUT,text=True)
            processes.append((proc,handle))
            return proc
        paper_log=p_dir/"paper.log";velocity_log=v_dir/"velocity.log"
        try:
            paper=start_jar(p_jar,p_dir,paper_log)
            direct=wait_status(paper,BACKEND_PORT,"PAPER")
            require(backend_status(direct),"DIRECT_PAPER_MOTD_MISSING")
            velocity=start_jar(v_jar,v_dir,velocity_log)
            proxied=wait_status(velocity,PROXY_PORT,"VELOCITY")
            require(backend_status(proxied),
                    "VELOCITY_STATUS_DOES_NOT_PASS_THROUGH_PAPER")
            graceful_stop(paper,"PAPER")
            # No backend means no evidence of the backend's marker.
            off=None
            deadline=time.monotonic()+18
            while time.monotonic()<deadline:
                try:
                    off=status_query("127.0.0.1",PROXY_PORT,777)
                    if not backend_status(off):
                        break
                except (OSError,EOFError,TimeoutError,ValueError):
                    pass
                time.sleep(1)
            require(off is None or not backend_status(off),
                    "VELOCITY_STALE_BACKEND_DATA_AFTER_STOP")
            paper=start_jar(p_jar,p_dir,paper_log)
            restored=wait_status(paper,BACKEND_PORT,"PAPER_RESTART")
            require(backend_status(restored),"PAPER_RESTART_MOTD_MISSING")
            retry=None
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                try:
                    retry=status_query("127.0.0.1",PROXY_PORT,777)
                    if backend_status(retry):
                        break
                except (OSError,EOFError,TimeoutError,ValueError):
                    pass
                time.sleep(1)
            require(retry is not None and backend_status(retry),
                    "VELOCITY_BACKEND_REJOIN_NOT_OBSERVED")
            require((p_dir/"world/level.dat").is_file(),
                    "BACKEND_PERSISTENT_WORLD_NOT_CREATED")
            graceful_stop(paper,"PAPER")
            graceful_stop(velocity,"VELOCITY")
            return {
                "schema":"supracraft.velocity-paper-263-data-plane/1",
                "classification":"REAL_PROXY_TO_BACKEND_STATUS_PASSTHROUGH",
                "paper":{"minecraft_version":"26.3","build":177,
                         "sha256":pdigest,"protocol":777},
                "velocity":{"version":"4.2.0","build":30,
                            "sha256":vdigest},
                "proxy_status_inherits_backend_marker":True,
                "proxy_status_loses_backend_marker_on_stop":True,
                "proxy_status_restores_after_backend_restart":True,
                "backend_world_level_dat_observed":True,
                "backend_listening_on_loopback_only":True,
                "proxy_listening_on_loopback_only":True,
                "player_login_tested":False,
                "modern_player_info_forwarding_tested":False,
                "vip_admission_tested":False,
                "vanillacord_tested":False,
                "gameplay_tested":False,
                "truenas_guest_tested":False,
                "collage_deployed":False,
                "operationally_selected":False,
                "physical_truenas_apply":"HOLD",
                "next_gate":"REAL_PROXY_LOGIN_WITH_MODERN_FORWARDING_AND_DENIED_BACKEND_BYPASS",
            }
        finally:
            for proc,handle in processes:
                try:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait(timeout=15)
                finally:
                    handle.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--discovery",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    a=p.parse_args()
    record=execute(json.loads(a.discovery.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"classification":record["classification"],
                      "paper_sha256":record["paper"]["sha256"],
                      "velocity_sha256":record["velocity"]["sha256"]},sort_keys=True))


if __name__=="__main__":
    main()
