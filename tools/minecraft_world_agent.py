#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib, shutil, sys

def tree_hash(root):
    root=pathlib.Path(root); h=hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel=p.relative_to(root).as_posix().encode()
        h.update(len(rel).to_bytes(4,"big")); h.update(rel)
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def receipt(verb, **kw):
    print(json.dumps({"schema":"minecraft-world-agent-receipt/1","verb":verb,**kw},sort_keys=True))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("verb",choices=["status","hash","stage","activate","restore"])
    ap.add_argument("--root",required=True)
    ap.add_argument("--release")
    ap.add_argument("--source")
    a=ap.parse_args(); root=pathlib.Path(a.root).resolve()
    releases=root/"releases"; active=root/"active"; releases.mkdir(parents=True,exist_ok=True)
    if a.verb=="status":
        target=os.readlink(active) if active.is_symlink() else None
        receipt("status",active=target); return
    if a.verb=="hash":
        if not active.is_symlink(): raise SystemExit("no active world")
        target=(active.parent/os.readlink(active)).resolve()
        receipt("hash",active=os.readlink(active),sha256=tree_hash(target)); return
    if not a.release or "/" in a.release or a.release in (".",".."): raise SystemExit("--release required and must be a simple id")
    dest=(releases/a.release).resolve()
    if dest.parent != releases.resolve(): raise SystemExit("release escaped root")
    if a.verb=="stage":
        if not a.source: raise SystemExit("--source required")
        src=pathlib.Path(a.source).resolve()
        if dest.exists(): raise SystemExit("release already staged")
        shutil.copytree(src,dest)
        receipt("stage",release=a.release,sha256=tree_hash(dest)); return
    if not dest.is_dir(): raise SystemExit("release not staged")
    tmp=root/".active.next"
    if tmp.exists() or tmp.is_symlink(): tmp.unlink()
    os.symlink(os.path.relpath(dest,root),tmp)
    os.replace(tmp,active)
    receipt(a.verb,release=a.release,sha256=tree_hash(dest))
if __name__=="__main__": main()
