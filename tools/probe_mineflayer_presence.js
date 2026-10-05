const fs = require('fs')
const mineflayer = require('mineflayer')

const port = Number(process.env.MC_PORT || '25568')
const readyFile = process.env.BOT_READY_FILE
const resultFile = process.env.BOT_RESULT_FILE

if (!readyFile || !resultFile) {
  throw new Error('BOT_READY_FILE and BOT_RESULT_FILE are required')
}

const result = {
  schema: 'supracraft.mineflayer-presence/v0.1',
  mineflayer_version: require('mineflayer/package.json').version,
  minecraft_data_version: require('minecraft-data/package.json').version,
  minecraft_protocol_version: require('minecraft-protocol/package.json').version,
  requested_version: '26.3',
  milestones: {},
  packet_count: 0,
  last_packet: null
}

let bot
let spawned = false

function writeResult () {
  fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n')
}

function finish (code = 0) {
  writeResult()
  setTimeout(() => process.exit(code), 100)
}

try {
  bot = mineflayer.createBot({
    host: '127.0.0.1',
    port,
    username: 'SupraCraftProbe',
    auth: 'offline',
    version: '26.3'
  })
} catch (err) {
  result.error = String(err && err.stack ? err.stack : err)
  writeResult()
  process.exit(1)
}

bot.on('connect', () => {
  result.milestones.connect = Date.now()
  writeResult()
})

bot.on('login', () => {
  result.milestones.login = Date.now()
  writeResult()
})

bot.once('spawn', () => {
  spawned = true
  result.milestones.spawn = Date.now()
  result.negotiated_version = bot.version
  result.protocol_version = bot.protocolVersion
  result.spawn_position = bot.entity && bot.entity.position
    ? bot.entity.position.floored().toArray()
    : null
  fs.writeFileSync(readyFile, 'spawned\n')
  writeResult()
})

bot.on('error', (err) => {
  result.error = String(err && err.stack ? err.stack : err)
  writeResult()
})

bot.on('kicked', (reason) => {
  try {
    result.kicked = JSON.parse(JSON.stringify(reason))
  } catch {
    result.kicked = String(reason)
  }
  writeResult()
})

bot.on('end', (reason) => {
  result.end_reason = String(reason)
  result.milestones.end = Date.now()
  finish(spawned ? 0 : 1)
})

if (bot._client) {
  bot._client.on('packet', (_data, meta) => {
    result.packet_count += 1
    result.last_packet = {
      name: meta && meta.name,
      state: meta && meta.state
    }
  })
}

const checkpoint = setInterval(writeResult, 1000)
checkpoint.unref()

setTimeout(() => {
  result.error = result.error || 'presence probe timed out'
  try { bot.quit('probe timeout') } catch {}
  finish(2)
}, 90000)
