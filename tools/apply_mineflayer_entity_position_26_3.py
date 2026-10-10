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


# Source-exact 26.3 movement packet schema from protocol 777. Older Mineflayer
# accesses packet.dX/dY/dZ on rel_entity_move/entity_move_look, whereas the
# pinned node-minecraft-protocol codec exposes packet.move.steps.
DELTA_HELPER = """  // Exact 26.3 codec: entityDelta={onGround, steps:[{dX,dY,dZ,ticks}]}.
  // The deltas are chained, each on the established 1/4096 block scale.
  // This helper is invoked ONLY for Java 26.3.
  function applyEntityDelta26_3 (entity, packet) {
    const steps = packet.move?.steps
    if (!Array.isArray(steps) || steps.length === 0 || steps.length > 128) {
      throw new Error('26.3 entityDelta missing or unbounded steps')
    }
    for (const step of steps) {
      if (![step.dX, step.dY, step.dZ].every(Number.isInteger)) {
        throw new Error('26.3 entityDelta contains noninteger displacement')
      }
      entity.position.translate(step.dX / 4096, step.dY / 4096, step.dZ / 4096)
    }
    entity.onGround = Boolean(packet.move.onGround)
  }

"""

REL_ANCHOR = """  bot._client.on('rel_entity_move', (packet) => {
    // entity relative move
    const entity = fetchEntity(packet.entityId)
    if (bot.supportFeature('fixedPointDelta')) {
"""

REL_PATCH = """  bot._client.on('rel_entity_move', (packet) => {
    // entity relative move
    const entity = fetchEntity(packet.entityId)
    if (bot.version === '26.3') {
      applyEntityDelta26_3(entity, packet)
    } else if (bot.supportFeature('fixedPointDelta')) {
"""

LOOK_ANCHOR = """  bot._client.on('entity_move_look', (packet) => {
    // entity look and relative move
    const entity = fetchEntity(packet.entityId)
    if (bot.supportFeature('fixedPointDelta')) {
"""

LOOK_PATCH = """  bot._client.on('entity_move_look', (packet) => {
    // entity look and relative move
    const entity = fetchEntity(packet.entityId)
    if (bot.version === '26.3') {
      applyEntityDelta26_3(entity, packet)
    } else if (bot.supportFeature('fixedPointDelta')) {
"""

# The 26.3 position synchronization packet can carry a linear position or a
# stepped array of absolute positions. Unlike old versions it has no dx/dy/dz.
SYNC_ANCHOR = """  bot._client.on('sync_entity_position', (packet) => {
    const entity = fetchEntity(packet.entityId)
    entity.position.set(packet.x, packet.y, packet.z)
    entity.velocity.set(packet.dx, packet.dy, packet.dz)
"""

SYNC_PATCH = """  bot._client.on('sync_entity_position', (packet) => {
    const entity = fetchEntity(packet.entityId)
    if (bot.version === '26.3') {
      const position = Array.isArray(packet.steps) ? packet.steps.at(-1) : packet
      if (!position || ![position.x, position.y, position.z].every(Number.isFinite)) {
        throw new Error('26.3 entity position sync has no finite absolute position')
      }
      entity.position.set(position.x, position.y, position.z)
      // Protocol 777 sync contains no dx/dy/dz; retain known velocity.
    } else {
      entity.position.set(packet.x, packet.y, packet.z)
      entity.velocity.set(packet.dx, packet.dy, packet.dz)
    }
"""

def replace_exact(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"entity motion {label} source drift: {count} matches; expected one")
    return text.replace(old, new, 1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entities_js", type=Path)
    path = parser.parse_args().entities_js
    text = path.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise SystemExit(f"entity-position exact-source drift: {count} matches, expected 1")
    text = text.replace(OLD, NEW)
    text = replace_exact(text, REL_ANCHOR, DELTA_HELPER + REL_PATCH, "relative move")
    text = replace_exact(text, LOOK_ANCHOR, LOOK_PATCH, "relative look/move")
    text = replace_exact(text, SYNC_ANCHOR, SYNC_PATCH, "position synchronization")
    path.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
