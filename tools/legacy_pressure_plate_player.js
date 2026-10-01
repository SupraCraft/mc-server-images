#!/usr/bin/env node
'use strict'

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
      sources: []
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
      : null
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
