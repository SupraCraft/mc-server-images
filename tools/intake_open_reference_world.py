#!/usr/bin/env python3
"""Hydrate and provenance-bind an openly licensed reference Minecraft world."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

import nbtlib


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, *, user_agent: str = "SupraCraft-reference-world-calibration/1") -> bytes:
    req=urllib.request.Request(url, headers={"User-Agent":user_agent})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def resolve_mediafire(page_url: str) -> str:
    text=fetch(page_url).decode("utf-8", errors="replace")
    # MediaFire exposes a generated download*.mediafire.com URL in the page.
    candidates=re.findall(r'https://download[^"\'<> ]+?\.zip(?:\?[^"\'<> ]*)?', text)
    if not candidates:
        # fallback around id=downloadButton href
        m=re.search(r'id=["\']downloadButton["\'][^>]*href=["\']([^"\']+)', text)
        if m:
            candidates=[html.unescape(m.group(1))]
    if not candidates:
        raise RuntimeError("MediaFire page did not expose a direct ZIP URL")
    return html.unescape(candidates[0]).replace("&amp;","&")


def locate_world_root(extract_root: Path) -> Path:
    matches=sorted(extract_root.rglob("level.dat"))
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one level.dat, found {len(matches)}: {matches}")
    return matches[0].parent


def inspect_level(world_root: Path) -> dict:
    level=nbtlib.load(world_root/"level.dat")
    data=level.get("Data", level)
    def scalar(key, default=None):
        val=data.get(key, default) if hasattr(data,"get") else default
        try:
            return val.unpack() if hasattr(val,"unpack") else val
        except Exception:
            return str(val)
    return {
        "level_name":str(scalar("LevelName","")),
        "data_version":scalar("DataVersion"),
        "version_compound":str(scalar("Version")) if scalar("Version") is not None else None,
        "last_played":scalar("LastPlayed"),
        "game_type":scalar("GameType"),
        "generator_name":str(scalar("generatorName")) if scalar("generatorName") is not None else None,
        "generator_version":scalar("generatorVersion"),
        "region_file_count":len(list((world_root/"region").glob("r.*.*.mca"))) if (world_root/"region").is_dir() else 0,
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-id", required=True)
    ap.add_argument("--mediafire-page", required=True)
    ap.add_argument("--license", required=True)
    ap.add_argument("--attribution", required=True)
    ap.add_argument("--source-page", required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args=ap.parse_args()

    out=args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    source_zip=out/"original-world.zip"

    direct=resolve_mediafire(args.mediafire_page)
    req=urllib.request.Request(direct,headers={"User-Agent":"SupraCraft-reference-world-calibration/1"})
    with urllib.request.urlopen(req,timeout=300) as r, source_zip.open("wb") as f:
        shutil.copyfileobj(r,f)

    with zipfile.ZipFile(source_zip) as zf:
        bad=zf.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failure at {bad}")
        zf.extractall(out/"extracted")
    world_root=locate_world_root(out/"extracted")
    level_info=inspect_level(world_root)

    attribution=(
        f"# Reference-world attribution\n\n"
        f"- World ID: {args.world_id}\n"
        f"- Source: {args.source_page}\n"
        f"- Artifact download page: {args.mediafire_page}\n"
        f"- License: {args.license}\n"
        f"- Attribution: {args.attribution}\n\n"
        "This benchmark intake preserves the original artifact as a calibration input. "
        "Any upgraded or modified copy is a distinct treatment and must preserve applicable license conditions.\n"
    )
    (out/"ATTRIBUTION.md").write_text(attribution,encoding="utf-8")

    receipt={
        "schema":"supracraft-reference-world-intake/1",
        "world_id":args.world_id,
        "source_page":args.source_page,
        "download_page":args.mediafire_page,
        "resolved_provider_host":urllib.request.urlparse(direct).hostname if hasattr(urllib.request,"urlparse") else "download.mediafire.com",
        "license":args.license,
        "original_sha256":sha256(source_zip),
        "original_bytes":source_zip.stat().st_size,
        "level_dat":level_info,
        "analysis_blind":True,
        "human_feedback_labels_loaded":False,
        "treatment":"original-artifact-intake-only"
    }
    # urllib.request has no urlparse; don't retain a transient signed direct URL.
    receipt["resolved_provider_host"]="mediafire-download"
    (out/"intake-receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
