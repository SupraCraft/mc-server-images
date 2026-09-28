const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const port = Number(process.env.MC_PORT || '25567')
const readyFile = process.env.BOT_READY_FILE
const resultFile = process.env.BOT_RESULT_FILE

if (!readyFile || !resultFile) {
  throw new Error('BOT_READY_FILE and BOT_RESULT_FILE are required')
}

const result = {
  schema: 'supracraft.mineflayer-placement/v0.1',
  mineflayer_version: require('mineflayer/package.json').version,
  requested_version: '26.3',
  placed: false
}

const bot = mineflayer.createBot({
  host: '127.0.0.1',
  port,
  username: 'SupraCraftProbe',
  auth: 'offline',
  version: '26.3'
})

function saveAndQuit (exitCode = 0) {
  fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n')
  try {
    bot.quit('probe complete')
  } catch {}
  setTimeout(() => process.exit(exitCode), 250)
}

bot.on('error', (err) => {
  result.error = String(err && err.stack ? err.stack : err)
})

bot.on('kicked', (reason) => {
  result.kicked = String(reason)
})

bot.once('spawn', async () => {
  result.negotiated_version = bot.version
  result.protocol_version = bot.protocolVersion
  fs.writeFileSync(readyFile, 'spawned\n')

  try {
    const deadline = Date.now() + 30000
    let stone = null
    while (Date.now() < deadline) {
      stone = bot.inventory.items().find(item => item.name === 'stone')
      const p = bot.entity.position
      if (stone && Math.abs(p.x - 2) < 2 && Math.abs(p.z) < 2) break
      await bot.waitForTicks(2)
    }

    if (!stone) throw new Error('stone item never appeared in bot inventory')

    await bot.equip(stone, 'hand')
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
    result.placed = result.after === 'stone'

    if (!result.placed) {
      throw new Error('Mineflayer placeBlock returned without target becoming stone')
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
