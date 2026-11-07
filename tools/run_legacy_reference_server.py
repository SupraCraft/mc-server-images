#!/usr/bin/env python3
"""Run an original reference world on its exact historical vanilla server."""

from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, tempfile, time, urllib.request, zipfile
from pathlib import Path

MANIFEST="https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

def sha(path,algo):
    h=hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def get_json(url):
    with urllib.request.urlopen(url,timeout=120) as r:
        return json.load(r)

def resolve_version(version):
    manifest=get_json(MANIFEST)
    entry=next((x for x in manifest["versions"] if x["id"]==version),None)
    if entry is None:raise RuntimeError(f"version {version} not in Mojang manifest")
    meta=get_json(entry["url"])
    server=meta.get("downloads",{}).get("server")
    if not server:raise RuntimeError(f"version {version} has no server artifact")
    return entry,meta,server

def download(server,path):
    with urllib.request.urlopen(server["url"],timeout=300) as r, path.open("wb") as f:
        shutil.copyfileobj(r,f)
    observed=sha(path,"sha1")
    if observed!=server["sha1"]:
        raise RuntimeError(f"server sha1 mismatch expected={server['sha1']} observed={observed}")

def materialize_world(world_zip,dest):
    with tempfile.TemporaryDirectory(prefix="legacy-world-unzip-") as td:
        root=Path(td)
        with zipfile.ZipFile(world_zip) as zf:
            bad=zf.testzip()
            if bad is not None:raise RuntimeError(f"zip CRC failure {bad}")
            zf.extractall(root)
        levels=list(root.rglob("level.dat"))
        if len(levels)!=1:
            raise RuntimeError(f"expected one level.dat, found {len(levels)}")
        shutil.copytree(levels[0].parent,dest)

def wait_ready(proc,log_path,timeout):
    started=time.monotonic()
    deadline=started+timeout
    while time.monotonic()<deadline:
        if proc.poll() is not None:break
        if log_path.exists() and "Done (" in log_path.read_text("utf-8",errors="replace"):
            return time.monotonic()-started
        time.sleep(0.5)
    tail=log_path.read_text("utf-8",errors="replace")[-8000:] if log_path.exists() else ""
    raise RuntimeError(f"legacy server did not become ready rc={proc.poll()} tail={tail!r}")

def send(proc,line):
    if proc.stdin is None:raise RuntimeError("stdin unavailable")
    proc.stdin.write(line+"\n");proc.stdin.flush()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",required=True)
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--timeout-seconds",type=int,default=180)
    args=ap.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)

    entry,meta,server_meta=resolve_version(args.version)
    started_wall=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    with tempfile.TemporaryDirectory(prefix=f"legacy-{args.version}-") as td:
        root=Path(td)
        server=root/"server.jar"; world=root/"world"
        download(server_meta,server)
        materialize_world(args.world_zip,world)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
          "online-mode=false",
          "server-port=25578",
          "level-name=world",
          "enable-command-block=true",
          "spawn-protection=0",
          "max-players=1",
          "view-distance=6",
          "difficulty=1",
          "gamemode=2",
          "motd=SupraCraft exact historical reference runtime",
        ])+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            proc=subprocess.Popen(
              ["java","-Xms512M","-Xmx2G","-jar",str(server),"nogui"],
              cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True
            )
            ready=wait_ready(proc,log_path,args.timeout_seconds)
            send(proc,"say SUPRACRAFT_LEGACY_RUNTIME_READY")
            time.sleep(2)
            send(proc,"save-all")
            time.sleep(2)
            send(proc,"stop")
            rc=proc.wait(timeout=60)
        text=log_path.read_text("utf-8",errors="replace")
        shutil.copy2(log_path,args.output_dir/"server.log")
        if rc!=0 or "SUPRACRAFT_LEGACY_RUNTIME_READY" not in text:
            raise RuntimeError(f"legacy runtime failed rc={rc}")
        fatal=[line for line in text.splitlines() if "Exception in server tick loop" in line or "Encountered an unexpected exception" in line]
        if fatal:
            raise RuntimeError("legacy runtime fatal log: "+" | ".join(fatal[-10:]))

        receipt={
          "schema":"supracraft-historical-reference-runtime/1",
          "status":"success",
          "minecraft_version":args.version,
          "version_type":entry.get("type"),
          "version_release_time":entry.get("releaseTime"),
          "version_metadata_url":entry["url"],
          "server_url":server_meta["url"],
          "server_expected_sha1":server_meta["sha1"],
          "server_observed_sha1":sha(server,"sha1"),
          "server_observed_sha256":sha(server,"sha256"),
          "server_size":server.stat().st_size,
          "source_world_zip_sha256":sha(args.world_zip,"sha256"),
          "started_at":started_wall,
          "ready_seconds":round(ready,3),
          "java_version_output":subprocess.check_output(["java","-version"],stderr=subprocess.STDOUT,text=True).strip(),
          "runtime_policy":{
            "online_mode":False,
            "command_blocks":True,
            "world_upgrade":False,
            "datafix_to_current":False
          },
          "limitations":[
            "Server startup proves version-matched runtime compatibility, not full playthrough correctness.",
            "No player actor joined this baseline rep.",
            "Dynamic mechanism probes require bounded state-reset or disposable-world reps."
          ]
        }
        (args.output_dir/"runtime-receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
        print(json.dumps(receipt,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
