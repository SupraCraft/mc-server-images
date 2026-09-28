const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const port = Number(process.env.MC_PORT || '25567')
const readyFile = process.env.BOT_READY_FILE
const resultFile = process.env.BOT_RESULT_FILE
const itemName = process.env.BOT_ITEM_NAME || 'stone'
const expectedBlockName = process.env.BOT_EXPECTED_BLOCK_NAME || itemName

if (!readyFile || !resultFile) {
  throw new Error('BOT_READY_FILE and BOT_RESULT_FILE are required')
}

const result = {
  schema: 'supracraft.mineflayer-placement/v0.1',
  mineflayer_version: require('mineflayer/package.json').version,
  minecraft_data_version: require('minecraft-data/package.json').version,
  minecraft_protocol_version: require('minecraft-protocol/package.json').version,
  requested_version: '26.3',
  support_features: {
    clientTickEndPacket: mineflayer.supportFeature('clientTickEndPacket', '26.3')
  },
  item_name: itemName,
  expected_block_name: expectedBlockName,
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
    username: 'SupraCraftProbe',
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
    bot.quit('probe complete')
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

const checkpoint = setInterval(() => {
  writeResult()
}, 1000)
checkpoint.unref()

bot.once('spawn', async () => {
  result.milestones.spawn = Date.now()
  result.negotiated_version = bot.version
  result.protocol_version = bot.protocolVersion
  fs.writeFileSync(readyFile, 'spawned\n')

  try {
    const deadline = Date.now() + 30000
    let probeItem = null
    while (Date.now() < deadline) {
      probeItem = bot.inventory.items().find(item => item.name === itemName)
      const p = bot.entity.position
      if (probeItem && Math.abs(p.x - 2) < 2 && Math.abs(p.z) < 2) break
      await bot.waitForTicks(2)
    }

    if (!probeItem) throw new Error(itemName + ' item never appeared in bot inventory')

    await bot.equip(probeItem, 'hand')
    await bot.waitForTicks(5)

    const reference = bot.blockAt(new Vec3(0, 69, 0))
    if (!reference || reference.name !== 'stone') {
      throw new Error('reference support block is not stone')
    }

    const before = bot.blockAt(new Vec3(0, 70, 0))
    result.before = before ? before.name : null
    result.bot_position = bot.entity.position.floored().toArray()

    await bot.placeBlock(reference, new Vec3(0, 1, 0))
    await bot.waitForTicks(10)

    const after = bot.blockAt(new Vec3(0, 70, 0))
    result.after = after ? after.name : null
    result.placed = result.after === expectedBlockName

    if (!result.placed) {
      throw new Error('Mineflayer placeBlock returned without target becoming ' + expectedBlockName)
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
