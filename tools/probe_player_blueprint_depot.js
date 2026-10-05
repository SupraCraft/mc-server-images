const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25576')
const username = process.env.MC_USER || 'SupraCraftBuilder'
const readyFile = process.env.BOT_READY_FILE
const goFile = process.env.BOT_GO_FILE
const resultFile = process.env.BOT_RESULT_FILE

if (!readyFile || !goFile || !resultFile) {
  throw new Error('required player-depot environment is missing')
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

async function waitFile (file, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (fs.existsSync(file)) return
    await sleep(100)
  }
  throw new Error('timeout waiting for ' + file)
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  version: '26.3',
  auth: 'offline'
})

async function transferOne (window, itemName, destSlot) {
  const item = bot.registry.itemsByName[itemName]
  if (!item) throw new Error('registry missing item ' + itemName)

  await bot.transfer({
    window,
    itemType: item.id,
    metadata: null,
    sourceStart: window.inventoryStart,
    sourceEnd: window.inventoryEnd,
    destStart: destSlot,
    destEnd: destSlot + 1,
    count: 1
  })
}

async function main () {
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })

  fs.writeFileSync(readyFile, JSON.stringify({
    spawned: true,
    position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
  }) + '\n')

  await waitFile(goFile, 30000)
  await sleep(500)

  const hopperPos = new Vec3(0, 70, 2)
  let hopper
  for (let i = 0; i < 20; i++) {
    hopper = bot.blockAt(hopperPos)
    if (hopper && hopper.name === 'hopper') break
    await sleep(200)
  }
  if (!hopper || hopper.name !== 'hopper') {
    throw new Error('registered material hopper not visible to player client')
  }

  const container = await bot.openContainer(hopper)

  // Exercise a real player inventory/container path. Explicit destination
  // slots keep the bounded RDTE bill-of-materials contract deterministic.
  await transferOne(container, 'cauldron', 0)
  await transferOne(container, 'cauldron', 1)
  await transferOne(container, 'water_bucket', 2)
  await transferOne(container, 'water_bucket', 3)

  await sleep(500)
  const deposited = container.containerItems().map(item => ({
    name: item.name,
    count: item.count,
    slot: item.slot
  }))

  await container.close()

  fs.writeFileSync(resultFile, JSON.stringify({
    schema: 'supracraft.player-depot-client-rdte/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    client: 'mineflayer exact-26.3',
    initiation: 'player_material_delivery',
    depot: { block: 'minecraft:hopper', at: [0, 70, 2] },
    deposited,
    result: 'deposited'
  }, null, 2) + '\n')
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.player-depot-client-rdte/v0.1',
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(() => {
    bot.quit('done')
  })
