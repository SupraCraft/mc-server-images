#!/usr/bin/env node
'use strict'

const crypto = require('crypto')
const fs = require('fs')
const mineflayer = require('mineflayer')

const argv = process.argv.slice(2)
function arg (name, fallback = null) {
  const i = argv.indexOf(name)
  return i >= 0 ? argv[i + 1] : fallback
}

const host = arg('--host', '127.0.0.1')
const port = Number(arg('--port', '25579'))
const username = arg('--username', 'SupraPlateBot')
const readyPath = arg('--ready')
const observationPath = arg('--observation')
const observeRaw = [arg('--observe-x'), arg('--observe-y'), arg('--observe-z')]
const observePos = observeRaw.every(v => v !== null)
  ? observeRaw.map(Number)
  : null
if (!readyPath) throw new Error('--ready is required')
if (observePos && !observationPath) throw new Error('--observation is required with --observe-*')

let settled = false
let observationTimer = null
const observation = observePos
  ? {
      schema: 'supracraft-legacy-player-block-observation/1',
      position: observePos,
      sample_count: 0,
      positive_metadata_observed: false,
      max_legacy_metadata: null,
      last_legacy_metadata: null,
      sources: [],
      client_feedback: {
        message_events: [],
        protocol_chat_events: [],
        self_effect_events: [],
        truncated: false
      }
    }
  : null

function persistObservation () {
  if (!observation || !observationPath) return
  const tmpPath = observationPath + '.tmp'
  fs.writeFileSync(tmpPath, JSON.stringify(observation, null, 2) + '\n')
  fs.renameSync(tmpPath, observationPath)
}

function observeBlock (block, source) {
  if (!observation || !block || !block.position) return
  if (
    block.position.x !== observePos[0] ||
    block.position.y !== observePos[1] ||
    block.position.z !== observePos[2]
  ) return
  const metadata = Number(block.metadata)
  if (!Number.isFinite(metadata)) return
  observation.sample_count += 1
  observation.last_legacy_metadata = metadata
  observation.max_legacy_metadata = observation.max_legacy_metadata === null
    ? metadata
    : Math.max(observation.max_legacy_metadata, metadata)
  observation.positive_metadata_observed =
    observation.positive_metadata_observed || metadata > 0
  if (!observation.sources.includes(source)) observation.sources.push(source)
  persistObservation()
}

function appendFeedbackEvent (field, row) {
  if (!observation || !observation.client_feedback) return
  const events = observation.client_feedback[field]
  if (!Array.isArray(events)) return
  if (events.length >= 64) {
    observation.client_feedback.truncated = true
    persistObservation()
    return
  }
  events.push(row)
  persistObservation()
}

function recordMessage (message, messagePosition) {
  if (!observation) return
  appendFeedbackEvent('message_events', {
    sha256: crypto.createHash('sha256').update(String(message)).digest('hex'),
    position: messagePosition === undefined || messagePosition === null
      ? null
      : String(messagePosition),
    observed_at_epoch_ms: Date.now()
  })
}

function classifyProtocolChat (packet) {
  const raw = packet && packet.message !== undefined && packet.message !== null
    ? String(packet.message)
    : ''
  let componentKind = 'unparsed'
  let semanticClass = 'unparsed'
  let commandVerb = null

  try {
    const component = JSON.parse(raw)
    if (typeof component === 'string') {
      componentKind = 'string'
      semanticClass = 'literal_text'
    } else if (Array.isArray(component)) {
      componentKind = 'array'
      semanticClass = 'composite'
    } else if (component && typeof component === 'object') {
      if (typeof component.translate === 'string') {
        componentKind = 'translate'
        const key = component.translate
        if (key.startsWith('commands.')) {
          semanticClass = 'command_feedback'
          const parts = key.split('.')
          commandVerb = parts.length > 1 && /^[a-z0-9_-]+$/i.test(parts[1])
            ? parts[1].toLowerCase()
            : null
        } else if (key.startsWith('death.')) {
          semanticClass = 'death'
        } else if (key.startsWith('achievement.')) {
          semanticClass = 'achievement'
        } else if (key.startsWith('chat.')) {
          semanticClass = 'chat'
        } else if (key.startsWith('gameMode.')) {
          semanticClass = 'gamemode'
        } else if (key.startsWith('multiplayer.')) {
          semanticClass = 'multiplayer'
        } else {
          semanticClass = 'translated_other'
        }
      } else if (Object.prototype.hasOwnProperty.call(component, 'text')) {
        componentKind = 'text'
        semanticClass = 'literal_text'
      } else {
        componentKind = 'object'
        semanticClass = 'other_component'
      }
    }
  } catch (_) {}

  return {
    sha256: crypto.createHash('sha256').update(raw).digest('hex'),
    position: packet && packet.position !== undefined && packet.position !== null
      ? Number(packet.position)
      : null,
    component_kind: componentKind,
    semantic_class: semanticClass,
    command_verb: commandVerb,
    observed_at_epoch_ms: Date.now()
  }
}

function recordProtocolChat (packet) {
  if (!observation) return
  appendFeedbackEvent('protocol_chat_events', classifyProtocolChat(packet))
}

function recordSelfEffect (event, entity, effect) {
  if (!observation || !bot.entity || !entity || entity.id !== bot.entity.id || !effect) return
  const id = Number(effect.id)
  const amplifier = Number(effect.amplifier)
  const duration = Number(effect.duration)
  if (![id, amplifier, duration].every(Number.isFinite)) return
  appendFeedbackEvent('self_effect_events', {
    event,
    id,
    amplifier,
    duration,
    observed_at_epoch_ms: Date.now()
  })
}

function writeReceipt (status, extra = {}) {
  if (settled) return
  settled = true
  const receipt = {
    schema: 'supracraft-legacy-player-actor/1',
    status,
    minecraft_version: '1.8.8',
    mineflayer_version: require('mineflayer/package.json').version,
    username,
    ...extra
  }
  fs.writeFileSync(readyPath, JSON.stringify(receipt, null, 2) + '\n')
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  auth: 'offline',
  version: '1.8.8',
  hideErrors: false,
  checkTimeoutInterval: 5000
})

bot.on('blockUpdate', (oldBlock, newBlock) => {
  observeBlock(newBlock, 'block_update')
})

bot.on('messagestr', (message, messagePosition) => {
  recordMessage(message, messagePosition)
})

bot._client.on('chat', packet => {
  recordProtocolChat(packet)
})

bot.on('entityEffect', (entity, effect) => {
  recordSelfEffect('start', entity, effect)
})

bot.on('entityEffectEnd', (entity, effect) => {
  recordSelfEffect('end', entity, effect)
})

const timer = setTimeout(() => {
  writeReceipt('blocked', { blocker: 'spawn_timeout' })
  try { bot.quit('timeout') } catch (_) {}
  setTimeout(() => process.exit(2), 100)
}, 25000)

bot.once('spawn', () => {
  clearTimeout(timer)
  writeReceipt('ready', {
    protocol_version: Number(bot.protocolVersion),
    initial_position: bot.entity && bot.entity.position
      ? bot.entity.position.toArray().map(x => Number(x.toFixed(3)))
      : null,
    spawned_at_epoch_ms: Date.now()
  })
  if (observation) {
    observationTimer = setInterval(() => {
      try {
        const Vec3 = require('vec3').Vec3
        observeBlock(bot.blockAt(new Vec3(...observePos)), 'poll')
      } catch (_) {}
    }, 25)
  }
})

bot.on('kicked', reason => {
  if (!settled) writeReceipt('blocked', { blocker: 'kicked', reason: String(reason).slice(0, 240) })
})

bot.on('error', err => {
  if (!settled) writeReceipt('blocked', { blocker: 'client_error', error: String(err).slice(0, 240) })
})

process.on('SIGTERM', () => {
  if (observationTimer) clearInterval(observationTimer)
  persistObservation()
  try { bot.quit('probe complete') } catch (_) {}
  setTimeout(() => process.exit(0), 100)
})
