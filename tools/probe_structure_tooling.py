#!/usr/bin/env python3
"""Public-safe headless primitive qualification for Minecraft structure tooling.

The probe intentionally uses only a synthetic 1x1x1 cube and public metadata.
It measures whether an engine can be invoked headlessly, construct a primitive,
persist/reload an artifact, and retain Minecraft-like semantic metadata where
that engine has a native mechanism. Results are JSON and contain no private data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MC_ID = "probe/voxel/0001"
MC_BLOCK = "minecraft:stone"
EXPECTED_BOUNDS = [1.0, 1.0, 1.0]


def cmd_version(cmd, args):
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        p = subprocess.run([exe, *args], text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=30, check=False)
        line = (p.stdout or "").strip().splitlines()
        return line[0][:300] if line else f"{cmd}:available"
    except Exception as exc:
        return f"{cmd}:version-error:{type(exc).__name__}"


def base(tool):
    return {
        "schema": "supracraft.structure-tooling-probe/v0.1",
        "tool": tool,
        "fixture": {
            "kind": "unit-cube",
            "size": EXPECTED_BOUNDS,
            "voxel_id": MC_ID,
            "block": MC_BLOCK,
        },
        "headless": True,
        "available": False,
        "geometry_roundtrip": False,
        "semantic_roundtrip": False,
        "semantic_strategy": "unknown",
        "deterministic_input": True,
        "elapsed_ms": None,
        "notes": [],
    }


def probe_trimesh(work):
    r = base("trimesh")
    try:
        import trimesh
        r["available"] = True
        r["version"] = getattr(trimesh, "__version__", "unknown")
        mesh = trimesh.creation.box(extents=EXPECTED_BOUNDS)
        path = work / "cube.glb"
        scene = trimesh.Scene()
        scene.add_geometry(mesh, node_name=MC_ID, geom_name=MC_ID,
                           metadata={"mc_voxel_id": MC_ID, "mc_block": MC_BLOCK})
        path.write_bytes(scene.export(file_type="glb"))
        loaded = trimesh.load(path, force="scene")
        ext = [round(float(v), 6) for v in loaded.extents]
        r["geometry_roundtrip"] = ext == EXPECTED_BOUNDS
        r["semantic_strategy"] = "scene/node metadata; glTF extras require explicit validation"
        # Do not claim metadata fidelity until the exported glTF representation proves it.
        r["semantic_roundtrip"] = False
        r["artifact"] = {"format": "glb", "bytes": path.stat().st_size, "extents": ext}
    except Exception as exc:
        r["notes"].append(f"{type(exc).__name__}: {exc}")
    return r


def probe_cadquery(work):
    r = base("cadquery")
    try:
        import cadquery as cq
        from cadquery import exporters, importers
        r["available"] = True
        r["version"] = getattr(cq, "__version__", "unknown")
        shape = cq.Workplane("XY").box(1, 1, 1)
        path = work / "cube.step"
        exporters.export(shape, str(path))
        loaded = importers.importStep(str(path))
        bb = loaded.val().BoundingBox()
        ext = [round(float(bb.xlen), 6), round(float(bb.ylen), 6), round(float(bb.zlen), 6)]
        r["geometry_roundtrip"] = ext == EXPECTED_BOUNDS
        r["semantic_strategy"] = "MCVOX sidecar/stable object mapping unless native metadata path is qualified"
        r["semantic_roundtrip"] = False
        r["artifact"] = {"format": "step", "bytes": path.stat().st_size, "extents": ext}
    except Exception as exc:
        r["notes"].append(f"{type(exc).__name__}: {exc}")
    return r


def probe_openscad(work):
    r = base("openscad")
    version = cmd_version("openscad", ["--version"])
    if version is None:
        r["notes"].append("openscad command not found")
        return r
    r["available"] = True
    r["version"] = version
    scad = work / "cube.scad"
    out = work / "cube.stl"
    scad.write_text("cube([1,1,1], center=false);\n", encoding="utf-8")
    try:
        p = subprocess.run(["openscad", "-o", str(out), str(scad)], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=120, check=False)
        if p.returncode != 0 or not out.exists():
            r["notes"].append((p.stdout or "")[-1000:])
            return r
        import trimesh
        loaded = trimesh.load(out, force="mesh")
        ext = [round(float(v), 6) for v in loaded.extents]
        r["geometry_roundtrip"] = ext == EXPECTED_BOUNDS
        r["semantic_strategy"] = "sidecar required for STL; SCAD source can carry comments/parameters but not Minecraft semantics portably"
        r["semantic_roundtrip"] = False
        r["artifact"] = {"format": "stl", "bytes": out.stat().st_size, "extents": ext}
    except Exception as exc:
        r["notes"].append(f"{type(exc).__name__}: {exc}")
    return r


def probe_blender(work):
    r = base("blender")
    version = cmd_version("blender", ["--version"])
    if version is None:
        r["notes"].append("blender command not found")
        return r
    r["available"] = True
    r["version"] = version
    report = work / "blender-inner.json"
    blend = work / "cube.blend"
    py = work / "blender_probe.py"
    py.write_text(f"""import bpy, json
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.5,0.5,0.5))
obj=bpy.context.active_object
obj.name={MC_ID!r}
obj["mc_voxel_id"]={MC_ID!r}
obj["mc_block"]={MC_BLOCK!r}
bpy.ops.wm.save_as_mainfile(filepath={str(blend)!r})
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.open_mainfile(filepath={str(blend)!r})
obj=bpy.data.objects[{MC_ID!r}]
dims=[round(float(v),6) for v in obj.dimensions]
result={{"dims":dims,
"voxel_id":obj.get("mc_voxel_id"),
"block":obj.get("mc_block")}}
Path({str(report)!r}).write_text(json.dumps(result), encoding="utf-8")
""", encoding="utf-8")
    try:
        p = subprocess.run(["blender", "--background", "--python", str(py)], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=180, check=False)
        if p.returncode != 0 or not report.exists():
            r["notes"].append((p.stdout or "")[-1500:])
            return r
        inner = json.loads(report.read_text(encoding="utf-8"))
        r["geometry_roundtrip"] = inner["dims"] == EXPECTED_BOUNDS
        r["semantic_roundtrip"] = inner["voxel_id"] == MC_ID and inner["block"] == MC_BLOCK
        r["semantic_strategy"] = "Blender custom properties; glTF extras is a candidate interchange projection"
        r["artifact"] = {"format": "blend", "bytes": blend.stat().st_size, "extents": inner["dims"]}
    except Exception as exc:
        r["notes"].append(f"{type(exc).__name__}: {exc}")
    return r


def probe_freecad(work):
    r = base("freecad")
    command = shutil.which("FreeCADCmd") or shutil.which("freecadcmd") or shutil.which("freecad") or shutil.which("FreeCAD")
    if not command:
        r["notes"].append("FreeCADCmd/freecadcmd/freecad command not found")
        return r
    r["available"] = True
    r["version"] = cmd_version(os.path.basename(command), ["--version"])
    report = work / "freecad-inner.json"
    fcstd = work / "cube.FCStd"
    py = work / "freecad_probe.py"
    py.write_text(f"""import FreeCAD as App, Part, json
doc=App.newDocument("Probe")
obj=doc.addObject("Part::Box","Voxel")
obj.Length=1; obj.Width=1; obj.Height=1
obj.addProperty("App::PropertyString","mc_voxel_id"); obj.mc_voxel_id={MC_ID!r}
obj.addProperty("App::PropertyString","mc_block"); obj.mc_block={MC_BLOCK!r}
doc.recompute()
doc.saveAs({str(fcstd)!r})
App.closeDocument("Probe")
doc=App.openDocument({str(fcstd)!r})
obj=doc.getObject("Voxel")
bb=obj.Shape.BoundBox
result={{"dims":[round(bb.XLength,6),round(bb.YLength,6),round(bb.ZLength,6)],
"voxel_id":obj.mc_voxel_id,"block":obj.mc_block}}
open({str(report)!r},"w",encoding="utf-8").write(json.dumps(result))
""", encoding="utf-8")
    try:
        argv = [command, str(py)]
        if os.path.basename(command).lower() == "freecad":
            argv = [command, "--console", str(py)]
        p = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=180, check=False)
        if p.returncode != 0 or not report.exists():
            r["notes"].append((p.stdout or "")[-1500:])
            return r
        inner = json.loads(report.read_text(encoding="utf-8"))
        r["geometry_roundtrip"] = inner["dims"] == EXPECTED_BOUNDS
        r["semantic_roundtrip"] = inner["voxel_id"] == MC_ID and inner["block"] == MC_BLOCK
        r["semantic_strategy"] = "FreeCAD custom properties on document objects"
        r["artifact"] = {"format": "FCStd", "bytes": fcstd.stat().st_size, "extents": inner["dims"]}
    except Exception as exc:
        r["notes"].append(f"{type(exc).__name__}: {exc}")
    return r


PROBES = {
    "trimesh": probe_trimesh,
    "cadquery": probe_cadquery,
    "openscad": probe_openscad,
    "blender": probe_blender,
    "freecad": probe_freecad,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tool", choices=sorted(PROBES))
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"supracraft-{args.tool}-") as td:
        result = PROBES[args.tool](Path(td))
    result["elapsed_ms"] = round((time.monotonic() - start) * 1000, 3)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
