const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const port = Number(process.env.MC_PORT || '25569')
const readyFile = process.env.BOT_READY_FILE
const resultFile = process.env.BOT_RESULT_FILE

if (!readyFile || !resultFile) {
  throw new Error('BOT_READY_FILE and BOT_RESULT_FILE are required')
}

const EXPECTED = {
  hanging: 'false',
  waterlogged: 'false'
}

const result = {
  schema: 'supracraft.mineflayer-upright-lantern/v0.1',
  mineflayer_version: require('mineflayer/package.json').version,
  minecraft_data_version: require('minecraft-data/package.json').version,
  minecraft_protocol_version: require('minecraft-protocol/package.json').version,
  requested_version: '26.3',
  requested_state: 'minecraft:lantern[hanging=false,waterlogged=false]',
  placed: false,
  milestones: {},
  packet_count: 0,
  last_packet: null
}

let bot

function writeResult () {
  fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n')
}

try {
  bot = mineflayer.createBot({
    host: '127.0.0.1',
    port,
    username: 'SupraLantern',
    auth: 'offline',
    version: '26.3'
  })
} catch (err) {
  result.error = String(err && err.stack ? err.stack : err)
  writeResult()
  process.exit(1)
}

function saveAndQuit (exitCode = 0) {
  writeResult()
  try {
    bot.quit('upright lantern probe complete')
  } catch {}
  setTimeout(() => process.exit(exitCode), 250)
}

bot.on('connect', () => {
  result.milestones.connect = Date.now()
  writeResult()
})

bot.on('login', () => {
  result.milestones.login = Date.now()
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
  writeResult()
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

const checkpoint = setInterval(() => writeResult(), 1000)
checkpoint.unref()

bot.once('spawn', async () => {
  result.milestones.spawn = Date.now()
  result.negotiated_version = bot.version
  result.protocol_version = bot.protocolVersion
  fs.writeFileSync(readyFile, 'spawned\n')

  try {
    const deadline = Date.now() + 30000
    let lantern = null
    while (Date.now() < deadline) {
      lantern = bot.inventory.items().find(item => item.name === 'lantern')
      const p = bot.entity.position
      if (lantern && Math.abs(p.x - 2) < 1.5 && Math.abs(p.z) < 1.5) break
      await bot.waitForTicks(2)
    }

    if (!lantern) throw new Error('lantern item never appeared in bot inventory')

    await bot.equip(lantern, 'hand')
    await bot.waitForTicks(5)

    const reference = bot.blockAt(new Vec3(0, 69, 0))
    if (!reference || reference.name !== 'stone') {
      throw new Error('reference support block is not stone')
    }

    const before = bot.blockAt(new Vec3(0, 70, 0))
    result.before = before ? before.name : null
    result.bot_position = bot.entity.position.toArray()
    result.bot_yaw = bot.entity.yaw
    result.bot_pitch = bot.entity.pitch

    await bot.placeBlock(reference, new Vec3(0, 1, 0))
    await bot.waitForTicks(10)

    const after = bot.blockAt(new Vec3(0, 70, 0))
    result.after = after ? after.name : null
    result.after_state_id = after ? after.stateId : null
    const props = after && typeof after.getProperties === 'function'
      ? after.getProperties()
      : {}
    result.after_properties = props

    const normalized = {}
    for (const [key, value] of Object.entries(props)) normalized[key] = String(value)
    result.after_properties_normalized = normalized

    result.placed = (
      result.after === 'lantern' &&
      Object.entries(EXPECTED).every(([key, value]) => normalized[key] === value)
    )

    if (!result.placed) {
      throw new Error(
        'Mineflayer placeBlock did not produce requested upright lantern state: ' +
        JSON.stringify({ expected: EXPECTED, observed: normalized })
      )
    }

    saveAndQuit(0)
  } catch (err) {
    result.error = String(err && err.stack ? err.stack : err)
    saveAndQuit(1)
  }
})

setTimeout(() => {
  result.error = result.error || 'probe timed out'
  saveAndQuit(2)
}, 60000)
