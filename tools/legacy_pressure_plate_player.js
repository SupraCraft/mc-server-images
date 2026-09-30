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
if (!readyPath) throw new Error('--ready is required')

let settled = false
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

const timer = setTimeout(() => {
  writeReceipt('blocked', { blocker: 'spawn_timeout' })
  try { bot.quit('timeout') } catch (_) {}
  setTimeout(() => process.exit(2), 100)
}, 25000)

bot.once('spawn', () => {
  clearTimeout(timer)
  writeReceipt('ready', {
    protocol_version: bot._client && bot._client.protocolVersion,
    initial_position: bot.entity && bot.entity.position
      ? bot.entity.position.toArray().map(x => Number(x.toFixed(3)))
      : null
  })
})

bot.on('kicked', reason => {
  if (!settled) writeReceipt('blocked', { blocker: 'kicked', reason: String(reason).slice(0, 240) })
})

bot.on('error', err => {
  if (!settled) writeReceipt('blocked', { blocker: 'client_error', error: String(err).slice(0, 240) })
})

process.on('SIGTERM', () => {
  try { bot.quit('probe complete') } catch (_) {}
  setTimeout(() => process.exit(0), 100)
})
