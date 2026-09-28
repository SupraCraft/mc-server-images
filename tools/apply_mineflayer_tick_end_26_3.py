#!/usr/bin/env python3
"""Apply the minimal upstream Mineflayer #4128 tick-end semantics to the pinned #4130 tree.

This adapter is intentionally exact-source and fail-closed: every replacement
must match once, otherwise the experimental stack has drifted and qualification
stops.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("physics_js", type=Path)
    args = parser.parse_args()
    path = args.physics_js
    text = path.read_text("utf-8")

    text = replace_once(
        text,
        """  const positionUpdateSentEveryTick = bot.supportFeature('positionUpdateSentEveryTick')
  const hasConfigurationState = bot.supportFeature('hasConfigurationState') // 1.20.2+
""",
        """  const positionUpdateSentEveryTick = bot.supportFeature('positionUpdateSentEveryTick')
  const hasConfigurationState = bot.supportFeature('hasConfigurationState') // 1.20.2+
  const hasClientTickEndPacket = bot.supportFeature('clientTickEndPacket') // 1.21.3+
""",
        "feature flag",
    )

    text = replace_once(
        text,
        """  let lastPhysicsFrameTime = null
  let shouldUsePhysics = false
  bot.physicsEnabled = physicsEnabled ?? true
""",
        """  let lastPhysicsFrameTime = null
  let shouldUsePhysics = false
  let positionSentSinceTickEnd = false
  bot.physicsEnabled = physicsEnabled ?? true
""",
        "tick state",
    )

    text = replace_once(
        text,
        """  function tickPhysics (now) {
    if (bot._client.state !== 'play') return // do nothing outside of the play state (e.g. server transfer configuration phase)
    flushReplies()
    if (!bot.entity?.position || !Number.isFinite(bot.entity.position.x)) return // entity not ready
""",
        """  function tickPhysics (now) {
    if (bot._client.state !== 'play') return // do nothing outside of the play state (e.g. server transfer configuration phase)
    flushReplies()
    runPhysicsTick(now)
    // Java 26.3 closes each client tick with tick_end.
    sendTickEnd()
  }

  function runPhysicsTick (now) {
    if (!bot.entity?.position || !Number.isFinite(bot.entity.position.x)) return // entity not ready
""",
        "tick split",
    )

    text = replace_once(
        text,
        """    if (shouldUsePhysics) {
      updatePosition(now)
    }
  }

  // remove this when 'physicTick' is removed
""",
        """    if (shouldUsePhysics) {
      updatePosition(now)
    }
  }

  function sendTickEnd () {
    if (!hasClientTickEndPacket) return
    positionSentSinceTickEnd = false
    bot._client.write('tick_end', {})
  }

  function beforePositionPacket () {
    if (positionSentSinceTickEnd) sendTickEnd()
  }

  // remove this when 'physicTick' is removed
""",
        "tick helpers",
    )

    text = replace_once(
        text,
        """    lastSent.onGround = onGround
    lastSent.flags = { onGround, hasHorizontalCollision: undefined } // 1.21.3+
    bot._client.write('position', lastSent)
    bot.emit('move', oldPos)
""",
        """    lastSent.onGround = onGround
    lastSent.flags = { onGround, hasHorizontalCollision: undefined } // 1.21.3+
    lastSent.time = performance.now()
    beforePositionPacket()
    bot._client.write('position', lastSent)
    positionSentSinceTickEnd = true
    bot.emit('move', oldPos)
""",
        "position packet",
    )

    text = replace_once(
        text,
        """    lastSent.onGround = onGround
    lastSent.flags = { onGround, hasHorizontalCollision: undefined } // 1.21.3+
    bot._client.write('position_look', lastSent)
    bot.emit('move', oldPos)
""",
        """    lastSent.onGround = onGround
    lastSent.flags = { onGround, hasHorizontalCollision: undefined } // 1.21.3+
    lastSent.time = performance.now()
    beforePositionPacket()
    bot._client.write('position_look', lastSent)
    positionSentSinceTickEnd = true
    bot.emit('move', oldPos)
""",
        "position-look packet",
    )

    path.write_text(text, "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
