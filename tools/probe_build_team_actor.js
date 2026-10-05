const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25577')
const username = process.env.MC_USER
const role = process.env.ACTOR_ROLE
const goFile = process.env.ACTOR_GO_FILE
const readyFile = process.env.ACTOR_READY_FILE
const resultFile = process.env.ACTOR_RESULT_FILE

if (!username || !role || !goFile || !readyFile || !resultFile) {
  throw new Error('required build-team actor environment is missing')
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

async function walkNear (bot, target, stopDistance = 1.6, timeoutMs = 15000) {
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

async function runHauler (bot) {
  const sourcePos = new Vec3(-8, 70, 2)
  const depotPos = new Vec3(0, 70, 2)

  const source = bot.blockAt(sourcePos)
  if (!source || source.name !== 'barrel') throw new Error('source barrel not visible')
  const sourceContainer = await bot.openContainer(source)

  const cauldron = bot.registry.itemsByName.cauldron
  const waterBucket = bot.registry.itemsByName.water_bucket
  if (!cauldron || !waterBucket) throw new Error('registry missing BOM items')

  await sourceContainer.withdraw(cauldron.id, null, 2, null)
  await sourceContainer.withdraw(waterBucket.id, null, 2, null)
  await sourceContainer.close()

  const afterWithdraw = bot.inventory.items().filter(item =>
    item.name === 'cauldron' || item.name === 'water_bucket'
  ).map(item => ({ name: item.name, count: item.count }))

  const walk = await walkNear(bot, depotPos.offset(-1, 0, 0), 1.25)

  const depot = bot.blockAt(depotPos)
  if (!depot || depot.name !== 'hopper') throw new Error('registered hopper not visible')
  const depotContainer = await bot.openContainer(depot)
  await depotContainer.deposit(cauldron.id, null, 2, null)
  await depotContainer.deposit(waterBucket.id, null, 2, null)

  // Wait for the exact-version window state to settle before disconnecting.
  // The first embodiment rep closed and quit immediately; the client-side
  // inventory was empty but the server-side hopper remained empty, indicating
  // the final window transactions had not been durably acknowledged.
  await sleep(750)
  const depotItems = depotContainer.containerItems().map(item => ({
    name: item.name,
    count: item.count
  }))
  await depotContainer.close()
  await sleep(500)

  const remaining = bot.inventory.items().filter(item =>
    item.name === 'cauldron' || item.name === 'water_bucket'
  ).map(item => ({ name: item.name, count: item.count }))

  return {
    role: 'hauler',
    withdrew: afterWithdraw,
    walk,
    depot_items_observed_before_close: depotItems,
    remaining_inventory: remaining,
    result: remaining.length === 0 ? 'delivered' : 'incomplete'
  }
}

async function runBuilder (bot) {
  const controlPos = new Vec3(1, 70, 0)
  const walk = await walkNear(bot, controlPos.offset(1, 0, 0), 1.25)

  const lever = bot.blockAt(controlPos)
  if (!lever || lever.name !== 'lever') throw new Error('build-start lever not visible')
  await bot.lookAt(controlPos.offset(0.5, 0.5, 0.5), true)
  await bot.activateBlock(lever)
  await sleep(300)

  return {
    role: 'builder',
    walk,
    controller: { block: 'minecraft:lever', at: [1, 70, 0] },
    result: 'start_requested'
  }
}

const bot = mineflayer.createBot({
  host,
  port,
  username,
  version: '26.3',
  auth: 'offline'
})

bot.on('kicked', reason => console.log('BUILD_TEAM_KICKED ' + JSON.stringify(reason)))
bot.on('error', err => console.log('BUILD_TEAM_ERROR ' + String(err && err.stack ? err.stack : err)))

async function main () {
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })

  fs.writeFileSync(readyFile, JSON.stringify({
    role,
    username,
    spawned: true,
    position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
  }) + '\n')

  await waitFile(goFile, 30000)
  const result = role === 'hauler'
    ? await runHauler(bot)
    : role === 'builder'
      ? await runBuilder(bot)
      : (() => { throw new Error('unsupported actor role ' + role) })()

  fs.writeFileSync(resultFile, JSON.stringify({
    schema: 'supracraft.build-team-actor-rdte/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    client: 'mineflayer exact-26.3',
    username,
    ...result
  }, null, 2) + '\n')
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.build-team-actor-rdte/v0.1',
      role,
      username,
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(() => bot.quit('done'))
