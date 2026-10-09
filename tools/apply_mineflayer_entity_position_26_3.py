#!/usr/bin/env python3
"""Apply one exact-source, Java 26.3-only Mineflayer player-position correction.

The pinned 26.3 protocol encodes ClientboundAddEntityPacket coordinates as
f64 x/y/z. Some experimental feature-admission tables do not yet report
doublePosition, leaving remotely spawned player positions uninitialized.
No other Minecraft versions are affected.
"""
from pathlib import Path
import argparse

OLD = """    } else if (bot.supportFeature('doublePosition')) {
      entity.position.set(pos.x, pos.y, pos.z)
    }
"""

NEW = """    } else if (bot.supportFeature('doublePosition') || bot.version === '26.3') {
      // Exact Java 26.3 spawn_entity coordinates are f64; preserve upstream
      // behavior for every other version. Never invent a position from chat.
      entity.position.set(pos.x, pos.y, pos.z)
    }
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entities_js", type=Path)
    path = parser.parse_args().entities_js
    text = path.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f"entity-position exact-source drift: {count} matches, expected 1")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")

if __name__ == "__main__":
    main()
