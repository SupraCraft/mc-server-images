#!/usr/bin/env python3
"""Hydrate an exact Mojang Java client runtime from pinned launcher metadata.

The hydrated runtime is disposable and MUST NOT be uploaded as a benchmark artifact.
Only launch/evidence metadata derived from the official public launcher manifest is retained.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import shutil
import urllib.request
import uuid
import zipfile
from typing import Any

UA = "SupraCraft-worldgen-public-camera/1"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read()


def digest(data: bytes, algo: str) -> str:
    return hashlib.new(algo, data).hexdigest()


def fetch_verified(url: str, dest: pathlib.Path, *, sha1: str | None = None, sha256: str | None = None, size: int | None = None) -> None:
    if dest.exists():
        data = dest.read_bytes()
        if ((sha1 is None or digest(data, "sha1") == sha1)
                and (sha256 is None or digest(data, "sha256") == sha256)
                and (size is None or len(data) == size)):
            return
    data = get(url)
    if sha1 is not None and digest(data, "sha1") != sha1:
        raise RuntimeError(f"SHA-1 mismatch for {url}")
    if sha256 is not None and digest(data, "sha256") != sha256:
        raise RuntimeError(f"SHA-256 mismatch for {url}")
    if size is not None and len(data) != size:
        raise RuntimeError(f"size mismatch for {url}: {len(data)} != {size}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def rule_matches(rule: dict[str, Any], features: dict[str, bool]) -> bool:
    os_rule = rule.get("os")
    if os_rule:
        if os_rule.get("name") not in (None, "linux"):
            return False
        arch = os_rule.get("arch")
        if arch and arch not in ("x86_64", "x64"):
            return False
    for name, value in (rule.get("features") or {}).items():
        if bool(features.get(name, False)) != bool(value):
            return False
    return True


def allowed(item: dict[str, Any], features: dict[str, bool]) -> bool:
    rules = item.get("rules")
    if not rules:
        return True
    state = False
    for rule in rules:
        if rule_matches(rule, features):
            state = rule.get("action") == "allow"
    return state


def expand(value: str, vars: dict[str, str]) -> str:
    for key, replacement in vars.items():
        value = value.replace("${" + key + "}", replacement)
    return value


def offline_uuid(name: str) -> str:
    raw = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    raw[6] = (raw[6] & 0x0F) | 0x30
    raw[8] = (raw[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(raw)))


def collect_args(entries: list[Any], features: dict[str, bool], vars: dict[str, str]) -> list[str]:
    out: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            out.append(expand(entry, vars))
            continue
        if not isinstance(entry, dict) or not allowed(entry, features):
            continue
        value = entry.get("value")
        values = value if isinstance(value, list) else [value]
        for part in values:
            if isinstance(part, str):
                out.append(expand(part, vars))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release-evidence", type=pathlib.Path, required=True)
    ap.add_argument("--runtime-dir", type=pathlib.Path, required=True)
    ap.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    ap.add_argument("--username", default="SupraCraftTourBot")
    ap.add_argument("--server", default="127.0.0.1:25571")
    ap.add_argument("--width", default="640")
    ap.add_argument("--height", default="360")
    args = ap.parse_args()

    evidence = json.loads(args.release_evidence.read_text("utf-8"))
    runtime = args.runtime_dir.resolve()
    ev = args.evidence_dir.resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    ev.mkdir(parents=True, exist_ok=True)

    meta_url = evidence["launcher_entry"]["metadata_url"]
    metadata_bytes = get(meta_url)
    metadata_sha256 = digest(metadata_bytes, "sha256")
    expected_meta_sha = evidence["provenance"]["version_metadata_sha256"]
    if metadata_sha256 != expected_meta_sha:
        raise RuntimeError(f"version metadata SHA-256 mismatch: {metadata_sha256} != {expected_meta_sha}")
    metadata = json.loads(metadata_bytes)

    (ev / "version-metadata-summary.json").write_text(json.dumps({
        "id": metadata["id"],
        "mainClass": metadata["mainClass"],
        "type": metadata.get("type"),
        "assetIndex": metadata.get("assetIndex"),
        "metadata_url": meta_url,
        "metadata_sha256": metadata_sha256,
        "javaVersion": metadata.get("javaVersion"),
    }, indent=2, sort_keys=True) + "\n")

    libraries_dir = runtime / "libraries"
    natives_dir = runtime / "natives"
    assets_dir = runtime / "assets"
    game_dir = runtime / "game"
    client_dir = runtime / "versions" / metadata["id"]
    for p in (libraries_dir, natives_dir, assets_dir / "indexes", assets_dir / "objects", game_dir, client_dir):
        p.mkdir(parents=True, exist_ok=True)

    client = metadata["downloads"]["client"]
    client_jar = client_dir / f'{metadata["id"]}.jar'
    fetch_verified(client["url"], client_jar, sha1=client["sha1"], size=client["size"])

    classpath = [str(client_jar)]
    features = {
        "is_demo_user": False,
        "has_custom_resolution": True,
        "has_quick_plays_support": True,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": True,
        "is_quick_play_realms": False,
    }

    downloaded_libraries = []
    native_jars = []
    for lib in metadata.get("libraries", []):
        if not allowed(lib, features):
            continue
        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact:
            dest = libraries_dir / artifact["path"]
            fetch_verified(artifact["url"], dest, sha1=artifact.get("sha1"), size=artifact.get("size"))
            classpath.append(str(dest))
            downloaded_libraries.append({"name": lib.get("name"), "path": artifact["path"], "sha1": artifact.get("sha1")})

        native_key = (lib.get("natives") or {}).get("linux")
        if native_key:
            classifier = native_key.replace("${arch}", "64")
            native = (downloads.get("classifiers") or {}).get(classifier)
            if native:
                native_path = libraries_dir / pathlib.Path(native["url"].split("/")[-1])
                fetch_verified(native["url"], native_path, sha1=native.get("sha1"), size=native.get("size"))
                native_jars.append(native_path)

    for jar in native_jars:
        with zipfile.ZipFile(jar) as zf:
            for info in zf.infolist():
                name = info.filename
                if name.endswith("/") or name.startswith("META-INF/"):
                    continue
                target = natives_dir / pathlib.PurePosixPath(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    asset_index_info = metadata["assetIndex"]
    asset_index_bytes = get(asset_index_info["url"])
    if digest(asset_index_bytes, "sha1") != asset_index_info["sha1"]:
        raise RuntimeError("asset index SHA-1 mismatch")
    asset_index_path = assets_dir / "indexes" / f'{asset_index_info["id"]}.json'
    asset_index_path.write_bytes(asset_index_bytes)
    asset_index = json.loads(asset_index_bytes)

    objects = asset_index.get("objects", {})
    def hydrate_asset(item: tuple[str, dict[str, Any]]) -> tuple[str, int]:
        logical, info = item
        h = info["hash"]
        dest = assets_dir / "objects" / h[:2] / h
        fetch_verified(
            "https://resources.download.minecraft.net/" + h[:2] + "/" + h,
            dest,
            sha1=h,
            size=info.get("size"),
        )
        return logical, info.get("size", 0)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        asset_results = list(pool.map(hydrate_asset, objects.items()))

    username = args.username
    vars = {
        "auth_player_name": username,
        "version_name": metadata["id"],
        "game_directory": str(game_dir),
        "assets_root": str(assets_dir),
        "assets_index_name": asset_index_info["id"],
        "auth_uuid": offline_uuid(username),
        "auth_access_token": "0",
        "clientid": "0",
        "auth_xuid": "0",
        "user_type": "legacy",
        "version_type": metadata.get("type", "release"),
        "resolution_width": str(args.width),
        "resolution_height": str(args.height),
        "quickPlayMultiplayer": args.server,
        "launcher_name": "supracraft-worldgen-benchmark",
        "launcher_version": "1",
        "natives_directory": str(natives_dir),
        "library_directory": str(libraries_dir),
        "classpath_separator": os.pathsep,
        "classpath": os.pathsep.join(classpath),
    }

    arguments = metadata.get("arguments", {})
    jvm_args = collect_args(arguments.get("jvm", []), features, vars)
    game_args = collect_args(arguments.get("game", []), features, vars)

    jvm_args = [a for a in jvm_args if not a.startswith("-Xmx")]
    jvm_args = ["-Xms512M", "-Xmx3G", "-Djava.library.path=" + str(natives_dir)] + jvm_args

    logging = (metadata.get("logging") or {}).get("client")
    logging_record = None
    if logging and logging.get("file"):
        lf = logging["file"]
        log_path = runtime / "logging" / lf["id"]
        fetch_verified(lf["url"], log_path, sha1=lf.get("sha1"), size=lf.get("size"))
        jvm_args.append(expand(logging["argument"], {"path": str(log_path)}))
        logging_record = {"id": lf["id"], "sha1": lf.get("sha1")}

    if "--quickPlayMultiplayer" not in game_args:
        game_args += ["--quickPlayMultiplayer", args.server]
    if "--width" not in game_args:
        game_args += ["--width", str(args.width), "--height", str(args.height)]

    command = ["java"] + jvm_args + [metadata["mainClass"]] + game_args
    launch = {
        "schema": "supracraft-mojang-client-runtime/1",
        "minecraft_version": metadata["id"],
        "protocol": evidence["artifact_version_json"]["protocol_version"],
        "client_sha1": client["sha1"],
        "client_sha256": evidence["client_artifact"]["sha256"],
        "metadata_sha256": metadata_sha256,
        "asset_index_id": asset_index_info["id"],
        "asset_index_sha1": asset_index_info["sha1"],
        "asset_count": len(asset_results),
        "asset_bytes_reported": sum(size or 0 for _, size in asset_results),
        "library_count": len(downloaded_libraries),
        "native_jar_count": len(native_jars),
        "logging": logging_record,
        "main_class": metadata["mainClass"],
        "username": username,
        "offline_uuid": vars["auth_uuid"],
        "server": args.server,
        "command": command,
    }
    (ev / "client-runtime.json").write_text(json.dumps(launch, indent=2, sort_keys=True) + "\n")
    (runtime / "launch-command.json").write_text(json.dumps(command, indent=2) + "\n")
    print(json.dumps({k: v for k, v in launch.items() if k != "command"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
