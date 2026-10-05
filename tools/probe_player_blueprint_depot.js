const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25576')
const username = process.env.MC_USER || 'SupraBuilder'
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

bot.on('login', () => console.log('PLAYER_DEPOT_STAGE login'))
bot.on('spawn', () => console.log('PLAYER_DEPOT_STAGE spawn'))
bot.on('kicked', reason => console.log('PLAYER_DEPOT_KICKED ' + JSON.stringify(reason)))
bot.on('error', err => console.log('PLAYER_DEPOT_ERROR ' + String(err && err.stack ? err.stack : err)))
bot.on('end', reason => console.log('PLAYER_DEPOT_END ' + String(reason)))

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

  // Use normal container interaction for the player-facing work site.
  // This is the intended low-ceremony UX: open the registered depot and deposit
  // the required materials. The builder still evaluates only the bounded work
  // site and aggregate bill of materials.
  await bot.lookAt(new Vec3(0.5, 70.5, 2.5), true)
  const container = await bot.openContainer(hopper)
  const cauldron = bot.registry.itemsByName.cauldron
  const waterBucket = bot.registry.itemsByName.water_bucket
  if (!cauldron || !waterBucket) throw new Error('registry missing required BOM item')
  await container.deposit(cauldron.id, null, 2, null)
  await container.deposit(waterBucket.id, null, 2, null)
  await container.close()
  await sleep(500)

  const remaining = bot.inventory.items().map(item => ({
    name: item.name,
    count: item.count,
    slot: item.slot
  }))

  fs.writeFileSync(resultFile, JSON.stringify({
    schema: 'supracraft.player-depot-client-rdte/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    client: 'mineflayer exact-26.3',
    initiation: 'player_material_delivery',
    delivery_mode: 'container_deposit_into_registered_hopper',
    depot: { block: 'minecraft:hopper', at: [0, 70, 2] },
    deposited: [
      { name: 'cauldron', count: 2 },
      { name: 'water_bucket', count: 2 }
    ],
    remaining_inventory: remaining,
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
