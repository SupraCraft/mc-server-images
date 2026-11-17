#!/usr/bin/env python3
"""H100 real official 26.3 wrong-object/wrong-support then valid player restoration.

Synthetic public-only redstone fixture. Same disposable world is saved/restarted.
Not private Lantern causal story, private item marker or human stock-client HIL.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

import probe_core_restoration_physical_26_3 as base
from smoke_vanilla_runtime import download_verified_server

SCHEMA = "supracraft-h100-vanilla-physical-negative-matrix/v1"
PROTOCOL = 777
PORT = base.PORT
MARK = re.compile(r"\[Server thread/INFO\]: \[Not Secure\] \[Server\] (H100_[A-Z_]+)\b")
WRONG_ITEM = "H100_WRONG_ITEM_REJECTED"
WRONG_SUPPORT = "H100_WRONG_SUPPORT_REJECTED"
VALID = "H100_VALID_CORE_INSTALLED"
RESTART = "H100_RESTART_CONSEQUENCE_RETAINED"


def exact_marker_count(path, tag):
    if not path.exists():
        return 0
    text=path.read_text(encoding="utf-8",errors="replace")
    return sum(1 for line in text.splitlines()
               if (m:=MARK.search(line)) and m.group(1)==tag)


def authoritative_probe(proc, log_path, predicate, marker, timeout=15):
    first=exact_marker_count(log_path,marker)
    began=time.monotonic()
    while time.monotonic()-began<timeout:
        base.send(proc, predicate+" run say "+marker)
        time.sleep(0.45)
        if exact_marker_count(log_path,marker)>first:
            return round(time.monotonic()-began,3)
    raise RuntimeError("OFFICIAL_SERVER_PREDICATE_NOT_OBSERVED:"+marker)


def run_bot(root, log_path, proc, suffix, configure):
    ready=root/("bot-"+suffix+".ready")
    result_path=root/("bot-"+suffix+".json")
    env=dict(os.environ)
    env.update({"MC_PORT":str(PORT),"BOT_READY_FILE":str(ready),
                "BOT_RESULT_FILE":str(result_path)})
    worker=subprocess.Popen(
        ["node",str(Path(__file__).with_name("probe_mineflayer_core_place.js"))],
        cwd=Path(__file__).resolve().parents[1],
        env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,text=True,
    )
    try:
        base.wait_file(ready,worker,55)
        configure(proc)
        try:
            text,_=worker.communicate(timeout=70)
        except subprocess.TimeoutExpired:
            worker.kill()
            text,_=worker.communicate(timeout=10)
            raise RuntimeError("MINEFLAYER_NEGATIVE_OR_POSITIVE_TIMEOUT")
        if not result_path.is_file():
            raise RuntimeError("MINEFLAYER_NO_RESULT:"+text[-700:])
        result=json.loads(result_path.read_text(encoding="utf-8"))
        result["_exit"]=worker.returncode
        result["_stdout_tail"]=text[-500:]
        return result
    finally:
        if worker.poll() is None:
            worker.terminate()
            try: worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.kill();worker.wait(timeout=10)


def validate_wrong_support(result):
    if result.get("_exit")==0 or result.get("placed") is not False:
        raise RuntimeError("WRONG_SUPPORT_PLAYER_UNEXPECTEDLY_PLACED")
    if "core socket support block is not stone" not in str(result.get("error")):
        raise RuntimeError("WRONG_SUPPORT_NOT_FAIL_CLOSED_BY_PLAYER")
    if result.get("requested_version")!="26.3" or result.get("protocol_version")!=PROTOCOL:
        raise RuntimeError("BOT_NOT_EXACT_PROTOCOL_777")


def validate_valid_install(result):
    if result.get("_exit")!=0 or result.get("placed") is not True or result.get("error"):
        raise RuntimeError("VALID_PLAYER_DID_NOT_PLACE_CORE")
    if result.get("before")!="air" or result.get("after")!="redstone_block":
        raise RuntimeError("VALID_PLAYER_CORE_BLOCK_MISMATCH")
    if result.get("requested_version")!="26.3" or result.get("protocol_version")!=PROTOCOL:
        raise RuntimeError("BOT_NOT_EXACT_PROTOCOL_777")


def configure(root):
    base.write_server_config(root)
    prop=root/"server.properties"
    source=prop.read_text(encoding="utf-8")
    if "online-mode=false" not in source or f"server-port={PORT}" not in source:
        raise RuntimeError("NO_OFFLINE_LOOPBACK_ISOLATION")
    prop.write_text(source+"server-ip=127.0.0.1\n",encoding="utf-8")


def start_server(root,jar,log_path):
    log=log_path.open("w",encoding="utf-8")
    server=subprocess.Popen(
        ["java","-Xms512M","-Xmx1536M","-jar",str(jar),"nogui"],
        cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,
    )
    return server,log


def check_server_errors(log):
    failures=base.server_error_lines(log)
    if failures:
        raise RuntimeError("SERVER_ERROR_LINES:"+repr(failures[-3:])[:500])


def run(evidence):
    ver=evidence.get("artifact_version_json",{})
    if ver.get("id")!="26.3" or ver.get("protocol_version")!=PROTOCOL:
        raise ValueError("REQUIRES_OFFICIAL_JAVA_26_3_PROTOCOL_777")
    with tempfile.TemporaryDirectory(prefix="h100-physical-negative-") as td:
        root=Path(td)
        jar=root/"server.jar"
        download_verified_server(evidence,jar)
        sha=hashlib.sha256(jar.read_bytes()).hexdigest()
        if sha!=evidence["server_artifact"]["sha256"]:
            raise RuntimeError("OFFICIAL_JAR_SHA256_MISMATCH")
        configure(root)
        first_log=root/"server-first.log"
        first,log=start_server(root,jar,first_log)
        observations={}
        try:
            status=base.wait_server(first,PROTOCOL,180)
            if int(status.get("version",{}).get("protocol",-1))!=PROTOCOL:
                raise RuntimeError("STATUS_PROTOCOL_MISMATCH")
            for cmd in [
                "forceload add 0 0",
                "fill -2 69 -2 4 69 3 minecraft:stone",
                "fill -2 70 -2 4 72 3 minecraft:air",
                "setblock 0 70 0 minecraft:air",
                "setblock 1 69 0 minecraft:redstone_lamp",
                "setblock 1 70 0 minecraft:redstone_wire",
                "setblock 2 70 0 minecraft:iron_trapdoor",
            ]:
                base.send(first,cmd)
            time.sleep(1)
            observations["initial"]=authoritative_probe(
                first,first_log,base.initial_predicate(),"H100_INITIAL_UNRESTORED")
            # Wrong object is deliberately injected by fixture controller, never
            # claimed to be a player interaction or an authored story marker.
            base.send(first,"setblock 0 70 0 minecraft:gold_block")
            wrong_item_predicate=(
                "execute if block 0 70 0 minecraft:gold_block "
                "if block 1 70 0 minecraft:redstone_wire[power=0] "
                "if block 2 70 0 minecraft:iron_trapdoor[open=false,powered=false] "
                "if block 1 69 0 minecraft:redstone_lamp[lit=false]"
            )
            observations["wrong_object"]=authoritative_probe(
                first,first_log,wrong_item_predicate,WRONG_ITEM)
            base.send(first,"setblock 0 70 0 minecraft:air")
            base.send(first,"setblock 0 69 0 minecraft:dirt")
            time.sleep(0.5)

            def first_actor_setup(srv):
                base.send(srv,f"gamemode survival {base.BOT_NAME}")
                base.send(srv,f"give {base.BOT_NAME} minecraft:redstone_block 1")
                base.send(srv,f"tp {base.BOT_NAME} 0.5 70.0 2.5 180 0")

            rejected=run_bot(root,first_log,first,"wrong-support",first_actor_setup)
            validate_wrong_support(rejected)
            observations["wrong_support"]=authoritative_probe(
                first,first_log,base.initial_predicate(),WRONG_SUPPORT)
            base.send(first,"setblock 0 69 0 minecraft:stone")
            time.sleep(0.6)

            def second_actor_setup(srv):
                # Do not grant a second core; prove the same player's held core
                # from the failed attempt persists across disconnect/reconnect.
                base.send(srv,f"gamemode survival {base.BOT_NAME}")
                base.send(srv,f"tp {base.BOT_NAME} 0.5 70.0 2.5 180 0")

            installed=run_bot(root,first_log,first,"valid",second_actor_setup)
            validate_valid_install(installed)
            observations["valid_player"]=authoritative_probe(
                first,first_log,base.restored_predicate(),VALID)
            first_exit=base.stop_server(first)
        finally:
            if first.poll() is None:
                first.kill();first.wait(timeout=10)
            log.close()
        if first_exit!=0:
            raise RuntimeError("FIRST_SERVER_NONZERO_EXIT")
        check_server_errors(first_log)

        restart_log=root/"server-restart.log"
        restarted,second_log=start_server(root,jar,restart_log)
        try:
            rs=base.wait_server(restarted,PROTOCOL,180)
            if int(rs.get("version",{}).get("protocol",-1))!=PROTOCOL:
                raise RuntimeError("RESTART_PROTOCOL_MISMATCH")
            observations["same_save_restart"]=authoritative_probe(
                restarted,restart_log,base.restored_predicate(),RESTART)
            restart_exit=base.stop_server(restarted)
        finally:
            if restarted.poll() is None:
                restarted.kill();restarted.wait(timeout=10)
            second_log.close()
        if restart_exit!=0:
            raise RuntimeError("RESTART_SERVER_NONZERO_EXIT")
        check_server_errors(restart_log)

        return {
            "schema":SCHEMA,
            "status":"PUBLIC_26_3_SYNTHETIC_NEGATIVES_AND_POSITIVE_ACCEPTED_BOUNDED",
            "version":"26.3","protocol":PROTOCOL,
            "official_server_sha256":sha,
            "negative_wrong_object":{"source":"fixture_console_injected","rejected":True},
            "negative_wrong_support":{"source":"real_connected_unprivileged_mineflayer_player",
                                      "refused":True,"player_reported_error":str(rejected["error"])[:200]},
            "valid_install":{"source":"real_connected_unprivileged_mineflayer_player",
                             "first_item_reused_after_negative":True,
                             "before":installed["before"],"after":installed["after"]},
            "authoritative_predicate_durations":observations,
            "restart_same_world_consequence":True,
            "world_private":False,"disposable_world":True,
            "lantern_authored_story_verified":False,
            "unique_marked_core_custody_verified":False,
            "human_or_stock_client_accepted":False,
        }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    try:
        report=run(json.loads(args.evidence.read_text(encoding="utf-8")))
    except (OSError,ValueError,RuntimeError,KeyError,subprocess.SubprocessError) as exc:
        report={"schema":SCHEMA,"status":"FIRST_LIVE_REP_RED","error":str(exc)[:500],
                "lantern_authored_story_verified":False,
                "human_or_stock_client_accepted":False}
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        raise
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
