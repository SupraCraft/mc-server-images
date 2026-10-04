#!/usr/bin/env python3
"""Patch Prismarine Viewer so Java 26.3 uses pinned 26.1 render assets only.

Minecraft semantics still come from the exact 26.3 Mineflayer/world connection.
This patch changes only the presentation adapter's texture/model asset selection.
"""

from __future__ import annotations

import argparse
from pathlib import Path

OLD = """function getVersion (version) {
  if (supportedVersions.indexOf(version) !== -1) return version
  const major = toMajor(version)
  if (lastOfMajor[major] === undefined) {
    return null
  }
  return lastOfMajor[toMajor(version)]
}
"""

NEW = """function getVersion (version) {
  if (supportedVersions.indexOf(version) !== -1) return version
  // SupraCraft visual qualification: exact 26.3 protocol/world state is
  // rendered with the closest pinned 26.x asset bundle currently shipped by
  // prismarine-viewer. This is presentation-only and must never be used as a
  // semantic oracle.
  if (version === '26.3') return '26.1'
  const major = toMajor(version)
  if (lastOfMajor[major] === undefined) {
    return null
  }
  return lastOfMajor[toMajor(version)]
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("viewer_root", type=Path)
    args = ap.parse_args()
    path = args.viewer_root / "viewer/lib/version.js"
    text = path.read_text("utf-8")
    if NEW in text:
        print("viewer 26.3 asset fallback already applied")
        return 0
    if OLD not in text:
        raise RuntimeError("unexpected prismarine-viewer version.js; refusing to patch")
    path.write_text(text.replace(OLD, NEW), "utf-8")
    verify = path.read_text("utf-8")
    if "if (version === '26.3') return '26.1'" not in verify:
        raise RuntimeError("viewer fallback patch verification failed")
    print("applied exact-26.3 -> 26.1 presentation asset fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
