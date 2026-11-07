#!/usr/bin/env node
'use strict'

const crypto = require('crypto')
const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const argv = process.argv.slice(2)
function arg (name, fallback = null) {
  const i = argv.indexOf(name)
  return i >= 0 ? argv[i + 1] : fallback
}

const host = arg('--host', '127.0.0.1')
const port = Number(arg('--port', '25579'))
const username = arg('--username', 'SupraChestBot')
const readyPath = arg('--ready')
const observationPath = arg('--observation')
const activate = String(arg('--activate', 'false')).toLowerCase() === 'true'
const target = [
  Number(arg('--target-x')),
  Number(arg('--target-y')),
  Number(arg('--target-z'))
]
if (!readyPath) throw new Error('--ready is required')
if (!observationPath) throw new Error('--observation is required')
if (target.some(v => !Number.isFinite(v))) throw new Error('--target-x/y/z are required')

let settled = false
let openTimer = null
let opening = false
let openedChest = null

const observation = {
  schema: 'supracraft-legacy-trapped-chest-observation/1',
  position: target,
  event_count: 0,
  max_open_count: 0,
  open_observed: false,
  open_call_status: activate ? 'pending' : 'not_requested',
  open_error_sha256: null
}

function persistObservation () {
  const tmpPath = observationPath + '.tmp'
  fs.writeFileSync(tmpPath, JSON.stringify(observation, null, 2) + '\n')
  fs.renameSync(tmpPath, observationPath)
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

function targetMatch (block) {
  if (!block || !block.position) return false
  return block.position.x === target[0] &&
    block.position.y === target[1] &&
    block.position.z === target[2]
}

function recordLidEvent (block, count, block2) {
  if (!targetMatch(block) && !targetMatch(block2)) return
  const openCount = Number(count)
  if (!Number.isFinite(openCount)) return
  observation.event_count += 1
  observation.max_open_count = Math.max(observation.max_open_count, openCount)
  observation.open_observed = observation.open_observed || openCount > 0
  persistObservation()
}

persistObservation()

const bot = mineflayer.createBot({
  host,
  port,
  username,
  auth: 'offline',
  version: '1.8.8',
  hideErrors: false,
  checkTimeoutInterval: 5000
})

bot.on('chestLidMove', (block, isOpen, block2) => {
  recordLidEvent(block, isOpen, block2)
})

async function tryOpenTarget () {
  if (!activate || opening || openedChest || !bot.entity) return
  const center = new Vec3(target[0] + 0.5, target[1] + 0.5, target[2] + 0.5)
  if (bot.entity.position.distanceTo(center) > 5.5) return
  const block = bot.blockAt(new Vec3(...target))
  if (!block) return
  opening = true
  observation.open_call_status = 'attempted'
  persistObservation()
  try {
    openedChest = await bot.openChest(block)
    observation.open_call_status = 'opened'
    persistObservation()
  } catch (err) {
    observation.open_call_status = 'blocked'
    observation.open_error_sha256 = crypto
      .createHash('sha256')
      .update(String(err))
      .digest('hex')
    persistObservation()
  }
}

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
  if (activate) {
    openTimer = setInterval(() => {
      tryOpenTarget().catch(() => {})
    }, 50)
  }
})

bot.on('kicked', reason => {
  if (!settled) writeReceipt('blocked', {
    blocker: 'kicked',
    detail_sha256: crypto.createHash('sha256').update(String(reason)).digest('hex')
  })
})

bot.on('error', err => {
  if (!settled) writeReceipt('blocked', {
    blocker: 'client_error',
    detail_sha256: crypto.createHash('sha256').update(String(err)).digest('hex')
  })
})

process.on('SIGTERM', () => {
  if (openTimer) clearInterval(openTimer)
  persistObservation()
  try {
    if (openedChest) openedChest.close()
  } catch (_) {}
  try { bot.quit('probe complete') } catch (_) {}
  setTimeout(() => process.exit(0), 100)
})
