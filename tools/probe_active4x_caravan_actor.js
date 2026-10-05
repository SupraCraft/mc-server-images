const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25580')
const username = process.env.MC_USER || 'TwoRiversCaravan'
const readyFile = process.env.CARAVAN_READY_FILE
const goFile = process.env.CARAVAN_GO_FILE
const resultFile = process.env.CARAVAN_RESULT_FILE
const taskId = process.env.CARAVAN_TASK_ID
const cargoId = process.env.CARAVAN_CARGO_ID
const actorGroupId = process.env.CARAVAN_ACTOR_GROUP_ID

if (!readyFile || !goFile || !resultFile || !taskId || !cargoId || !actorGroupId) {
  throw new Error('required caravan environment is missing')
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

async function walkNear (bot, target, stopDistance = 1.4, timeoutMs = 25000) {
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

const bot = mineflayer.createBot({
  host,
  port,
  username,
  version: '26.3',
  auth: 'offline'
})

bot.on('kicked', reason => console.log('CARAVAN_KICKED ' + JSON.stringify(reason)))
bot.on('error', err => console.log('CARAVAN_ERROR ' + String(err && err.stack ? err.stack : err)))

async function main () {
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })
  await sleep(500)

  fs.writeFileSync(readyFile, JSON.stringify({
    username,
    spawned: true,
    task_id: taskId,
    cargo_id: cargoId,
    actor_group_id: actorGroupId,
    position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
  }) + '\n')

  await waitFile(goFile, 30000)

  const sourcePos = new Vec3(-10, 70, 0)
  const destinationPos = new Vec3(10, 70, 0)
  const wheat = bot.registry.itemsByName.wheat
  if (!wheat) throw new Error('registry missing wheat item')

  const source = bot.blockAt(sourcePos)
  if (!source || source.name !== 'barrel') throw new Error('source barrel not visible')
  const sourceContainer = await bot.openContainer(source)
  await sourceContainer.withdraw(wheat.id, null, 4, null)
  await sleep(500)
  const withdrew = bot.inventory.items()
    .filter(item => item.name === 'wheat')
    .map(item => ({ name: item.name, count: item.count }))
  await sourceContainer.close()
  await sleep(350)

  const walk = await walkNear(bot, destinationPos.offset(-1, 0, 0), 1.35)

  const destination = bot.blockAt(destinationPos)
  if (!destination || destination.name !== 'barrel') {
    throw new Error('destination barrel not visible')
  }
  const destinationContainer = await bot.openContainer(destination)
  await destinationContainer.deposit(wheat.id, null, 4, null)
  await sleep(750)
  const observedDestination = destinationContainer.containerItems()
    .filter(item => item.name === 'wheat')
    .map(item => ({ name: item.name, count: item.count }))
  await destinationContainer.close()
  await sleep(500)

  const remaining = bot.inventory.items()
    .filter(item => item.name === 'wheat')
    .map(item => ({ name: item.name, count: item.count }))

  fs.writeFileSync(resultFile, JSON.stringify({
    schema: 'supracraft.active4x-caravan-actor-rdte/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    client: 'mineflayer exact-26.3',
    username,
    actor_group_id: actorGroupId,
    task_id: taskId,
    cargo_id: cargoId,
    semantic_resource: 'grain',
    minecraft_item: 'minecraft:wheat',
    amount: 4,
    withdrew,
    walk,
    destination_items_observed_before_close: observedDestination,
    remaining_inventory: remaining,
    result: remaining.length === 0 ? 'delivered' : 'incomplete'
  }, null, 2) + '\n')
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.active4x-caravan-actor-rdte/v0.1',
      task_id: taskId,
      cargo_id: cargoId,
      actor_group_id: actorGroupId,
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(() => bot.quit('done'))
