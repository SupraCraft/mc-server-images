const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25578')
const username = process.env.MC_USER || 'SupraBuilder'
const readyFile = process.env.BUILDER_READY_FILE
const goFile = process.env.BUILDER_GO_FILE
const resultFile = process.env.BUILDER_RESULT_FILE

if (!readyFile || !goFile || !resultFile) {
  throw new Error('required physical-builder environment is missing')
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

async function walkNear (bot, target, stopDistance = 1.5, timeoutMs = 18000) {
  const started = bot.entity.position.clone()
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const pos = bot.entity.position
    if (pos.distanceTo(target) <= stopDistance) {
      bot.setControlState('forward', false)
      return {
        start: [started.x, started.y, started.z],
        end: [pos.x, pos.y, pos.z],
        distance: started.distanceTo(pos)
      }
    }
    await bot.lookAt(target.offset(0, 0.5, 0), true)
    bot.setControlState('forward', true)
    await sleep(100)
  }
  bot.setControlState('forward', false)
  throw new Error('walk timeout to ' + target.toString())
}

async function buildWateringPoint (bot, supportPos, targetPos) {
  await walkNear(bot, supportPos.offset(1, 0, 0), 1.35)

  const support = bot.blockAt(supportPos)
  if (!support || support.name !== 'stone_bricks') {
    throw new Error('support block not visible at ' + supportPos.toString())
  }

  const cauldronItem = bot.registry.itemsByName.cauldron
  const waterBucketItem = bot.registry.itemsByName.water_bucket
  if (!cauldronItem || !waterBucketItem) throw new Error('registry missing builder BOM')

  await bot.equip(cauldronItem.id, 'hand')
  await bot.placeBlock(support, new Vec3(0, 1, 0))
  await sleep(250)

  let placed = bot.blockAt(targetPos)
  if (!placed || placed.name !== 'cauldron') {
    throw new Error('cauldron placement not confirmed at ' + targetPos.toString())
  }

  await bot.equip(waterBucketItem.id, 'hand')
  await bot.lookAt(targetPos.offset(0.5, 0.5, 0.5), true)
  await bot.activateBlock(placed)
  await sleep(350)

  placed = bot.blockAt(targetPos)
  if (!placed || placed.name !== 'water_cauldron') {
    throw new Error('water cauldron activation not confirmed at ' + targetPos.toString())
  }

  return {
    support: [supportPos.x, supportPos.y, supportPos.z],
    target: [targetPos.x, targetPos.y, targetPos.z],
    result: 'water_cauldron_complete'
  }
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  version: '26.3',
  auth: 'offline'
})

bot.on('kicked', reason => console.log('PHYSICAL_BUILDER_KICKED ' + JSON.stringify(reason)))
bot.on('error', err => console.log('PHYSICAL_BUILDER_ERROR ' + String(err && err.stack ? err.stack : err)))

async function main () {
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })

  fs.writeFileSync(readyFile, JSON.stringify({
    username,
    spawned: true,
    position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
  }) + '\n')

  await waitFile(goFile, 30000)

  const depotPos = new Vec3(0, 70, 2)
  const depot = bot.blockAt(depotPos)
  if (!depot || depot.name !== 'hopper') throw new Error('registered depot not visible')

  const cauldron = bot.registry.itemsByName.cauldron
  const waterBucket = bot.registry.itemsByName.water_bucket
  if (!cauldron || !waterBucket) throw new Error('registry missing builder BOM')

  const container = await bot.openContainer(depot)
  await container.withdraw(cauldron.id, null, 2, null)
  await container.withdraw(waterBucket.id, null, 2, null)
  await sleep(500)
  await container.close()
  await sleep(350)

  const afterWithdraw = bot.inventory.items().filter(item =>
    item.name === 'cauldron' || item.name === 'water_bucket'
  ).map(item => ({ name: item.name, count: item.count }))

  const first = await buildWateringPoint(
    bot,
    new Vec3(-5, 70, -5),
    new Vec3(-5, 71, -5)
  )
  const second = await buildWateringPoint(
    bot,
    new Vec3(5, 70, -5),
    new Vec3(5, 71, -5)
  )

  const remaining = bot.inventory.items().filter(item =>
    item.name === 'cauldron' || item.name === 'water_bucket'
  ).map(item => ({ name: item.name, count: item.count }))

  fs.writeFileSync(resultFile, JSON.stringify({
    schema: 'supracraft.physical-builder-client-rdte/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    client: 'mineflayer exact-26.3',
    username,
    realization_path: 'physical_builder_client',
    withdrew: afterWithdraw,
    components: [first, second],
    remaining_bom_inventory: remaining,
    result: 'built'
  }, null, 2) + '\n')
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.physical-builder-client-rdte/v0.1',
      username,
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(() => bot.quit('done'))
