const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const port = Number(process.env.MC_PORT || '25573')
const readyFile = process.env.BOT_READY_FILE
const firstFile = process.env.BOT_FIRST_FILE
const secondFile = process.env.BOT_SECOND_FILE
const doneFile = process.env.BOT_DONE_FILE
const resultFile = process.env.BOT_RESULT_FILE

if (!readyFile || !firstFile || !secondFile || !doneFile || !resultFile) {
  throw new Error(
    'BOT_READY_FILE, BOT_FIRST_FILE, BOT_SECOND_FILE, BOT_DONE_FILE and BOT_RESULT_FILE are required'
  )
}

const CORE_ITEM = 'redstone_block'
const CHEST = new Vec3(0, 70, 0)
const result = {
  schema: 'supracraft.mineflayer-core-container/v0.1',
  mineflayer_version: require('mineflayer/package.json').version,
  minecraft_data_version: require('minecraft-data/package.json').version,
  minecraft_protocol_version: require('minecraft-protocol/package.json').version,
  requested_version: '26.3',
  milestones: {},
  acquisitions: [],
  packet_count: 0,
  last_packet: null
}

let bot

function writeResult () {
  fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n')
}

function coreInInventory () {
  return bot.inventory.items().some(item => item.name === CORE_ITEM)
}

async function withdrawCore (label) {
  const block = bot.blockAt(CHEST)
  if (!block || block.name !== 'chest') {
    throw new Error(`${label}: source block is not chest`)
  }

  const container = await bot.openContainer(block)
  try {
    const items = typeof container.containerItems === 'function'
      ? container.containerItems()
      : container.items()
    const core = items.find(item => item.name === CORE_ITEM)
    if (!core) throw new Error(`${label}: core absent from source container`)

    await container.withdraw(core.type, null, 1)
    await bot.waitForTicks(5)
  } finally {
    container.close()
  }

  if (!coreInInventory()) {
    throw new Error(`${label}: withdraw returned without core in inventory`)
  }

  result.acquisitions.push({
    label,
    at: Date.now(),
    bot_position: bot.entity.position.toArray(),
    core_in_inventory: true
  })
  result.milestones[label] = Date.now()
  writeResult()
}

function finish (exitCode = 0) {
  writeResult()
  try {
    bot.quit('container acquisition probe complete')
  } catch {}
  setTimeout(() => process.exit(exitCode), 250)
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
    // Controller positions the player and fills the source after spawn.
    const positionedDeadline = Date.now() + 30000
    while (Date.now() < positionedDeadline) {
      const p = bot.entity.position
      if (Math.abs(p.x - 0.5) < 3 && Math.abs(p.z - 2.5) < 3) break
      await bot.waitForTicks(2)
    }

    await withdrawCore('first_acquisition')
    fs.writeFileSync(firstFile, 'first-acquired\n')

    // Wait for the controller's deliberate-loss treatment.
    const lossDeadline = Date.now() + 30000
    while (Date.now() < lossDeadline && coreInInventory()) {
      await bot.waitForTicks(2)
    }
    if (coreInInventory()) {
      throw new Error('controlled loss was not observed in player inventory')
    }
    result.milestones.controlled_loss_observed = Date.now()
    writeResult()

    // The controller refills the same keeper source after the loss.
    const refillDeadline = Date.now() + 30000
    let refilled = false
    while (Date.now() < refillDeadline) {
      const block = bot.blockAt(CHEST)
      if (block && block.name === 'chest') {
        try {
          const container = await bot.openContainer(block)
          const items = typeof container.containerItems === 'function'
            ? container.containerItems()
            : container.items()
          refilled = items.some(item => item.name === CORE_ITEM)
          container.close()
          if (refilled) break
        } catch {}
      }
      await bot.waitForTicks(2)
    }
    if (!refilled) throw new Error('replacement core never appeared in source')

    await withdrawCore('reacquisition')
    fs.writeFileSync(secondFile, 'second-acquired\n')

    const releaseDeadline = Date.now() + 30000
    while (Date.now() < releaseDeadline && !fs.existsSync(doneFile)) {
      await bot.waitForTicks(2)
    }
    if (!fs.existsSync(doneFile)) {
      throw new Error('controller did not release worker after reacquisition')
    }
    result.milestones.controller_verified_reacquisition = Date.now()
    finish(0)
  } catch (err) {
    result.error = String(err && err.stack ? err.stack : err)
    finish(1)
  }
})

setTimeout(() => {
  result.error = result.error || 'probe timed out'
  finish(2)
}, 90000)
