const fs = require('fs')
const path = require('path')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const stateDir = process.env.ACTOR_STATE_DIR || '/actor-state'
const taskFile = path.join(stateDir, 'task.json')
const resultFile = path.join(stateDir, 'result.json')
const completedFile = path.join(stateDir, 'completed.json')
const readyFile = path.join(stateDir, 'service-ready.json')
const witnessFile = path.join(stateDir, 'visual-witness.json')
const host = process.env.MC_HOST || 'minecraft'
const port = Number(process.env.MC_PORT || '25565')
const version = process.env.MC_VERSION || '26.3'
const maxConcurrent = Number(process.env.ACTOR_MAX_CONCURRENT || '1')

if (maxConcurrent !== 1) {
  throw new Error('D2B bounded RDTE requires ACTOR_MAX_CONCURRENT=1')
}

fs.mkdirSync(stateDir, { recursive: true })

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function readJson (file, fallback = null) {
  if (!fs.existsSync(file)) return fallback
  return JSON.parse(fs.readFileSync(file, 'utf8'))
}

function atomicWrite (file, value) {
  const tmp = file + '.tmp'
  fs.writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n')
  fs.renameSync(tmp, file)
}

function loadCompleted () {
  const value = readJson(completedFile, { operation_ids: [] })
  return new Set(value.operation_ids || [])
}

function saveCompleted (set) {
  atomicWrite(completedFile, { operation_ids: [...set].sort() })
}

async function waitSpawn (bot, timeoutMs = 30000) {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('spawn timeout')), timeoutMs)
    bot.once('spawn', () => {
      clearTimeout(timer)
      resolve()
    })
    bot.once('error', err => {
      clearTimeout(timer)
      reject(err)
    })
  })
}

async function waitForBlock (bot, pos, expectedName, timeoutMs = 10000) {
  const deadline = Date.now() + timeoutMs
  let lastName = null
  while (Date.now() < deadline) {
    const block = bot.blockAt(pos)
    if (block) {
      lastName = block.name
      if (block.name === expectedName) return block
    }
    await sleep(100)
  }
  throw new Error(
    'timed out waiting for ' + expectedName + ' at ' + pos.toString() +
    '; last=' + String(lastName)
  )
}

function inventoryItemCount (bot, itemName) {
  return bot.inventory.items()
    .filter(row => row.name === itemName)
    .reduce((sum, row) => sum + row.count, 0)
}

function containerItemCount (container, itemName) {
  return container.containerItems()
    .filter(row => row.name === itemName)
    .reduce((sum, row) => sum + row.count, 0)
}

async function waitForInventoryCount (bot, itemName, expected, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs
  let last = inventoryItemCount(bot, itemName)
  while (Date.now() < deadline) {
    last = inventoryItemCount(bot, itemName)
    if (last === expected) return last
    await sleep(100)
  }
  throw new Error(
    'inventory settlement timeout for ' + itemName +
    '; expected=' + expected + '; last=' + last
  )
}

async function waitForDepositSettlement (
  bot,
  container,
  itemName,
  expectedContainerCount,
  timeoutMs = 5000
) {
  const deadline = Date.now() + timeoutMs
  let lastContainer = containerItemCount(container, itemName)
  let lastInventory = inventoryItemCount(bot, itemName)
  while (Date.now() < deadline) {
    lastContainer = containerItemCount(container, itemName)
    lastInventory = inventoryItemCount(bot, itemName)
    if (lastContainer >= expectedContainerCount && lastInventory === 0) {
      return { container: lastContainer, inventory: lastInventory }
    }
    await sleep(100)
  }
  throw new Error(
    'deposit settlement timeout for ' + itemName +
    '; container=' + lastContainer + '; inventory=' + lastInventory
  )
}

async function walkNear (bot, target, stopDistance = 1.35, timeoutMs = 30000) {
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

async function executeTask (task) {
  if (task.schema !== 'supracraft.active4x-actor-task/v0.1') {
    throw new Error('unsupported task schema')
  }
  if (task.minecraft_version !== version) {
    throw new Error('task/client version mismatch')
  }
  if (task.amount !== 4 || task.minecraft_item !== 'wheat') {
    throw new Error('bounded D2B rep expects four wheat')
  }

  const bot = mineflayer.createBot({
    host,
    port,
    username: task.username || 'TwoRiversActor',
    version,
    auth: 'offline'
  })

  bot.on('kicked', reason => console.log('D2B_ACTOR_KICKED ' + JSON.stringify(reason)))
  bot.on('error', err => console.log('D2B_ACTOR_ERROR ' + String(err && err.stack ? err.stack : err)))

  const witness = { schema: 'supracraft.active4x-visual-witness/v0.1', operation_id: task.operation_id, samples: [] }
  let witnessPhase = 'connecting'
  const sampleWitness = () => {
    if (!bot.entity || !bot.entity.position) return
    const p = bot.entity.position
    witness.samples.push({ t_ms: Date.now(), phase: witnessPhase, position: [p.x, p.y, p.z] })
    if (witness.samples.length > 600) witness.samples.shift()
    atomicWrite(witnessFile, witness)
  }
  const witnessTimer = setInterval(sampleWitness, 250)

  try {
    await waitSpawn(bot)
    witnessPhase = 'spawned'; sampleWitness()
    await sleep(500)

    const sourcePos = new Vec3(...task.source_position)
    const destinationPos = new Vec3(...task.destination_position)
    const item = bot.registry.itemsByName[task.minecraft_item]
    if (!item) throw new Error('registry missing item ' + task.minecraft_item)

    witnessPhase = 'to_source'; sampleWitness()
    const toSource = await walkNear(bot, sourcePos.offset(1, 0, 0))
    const source = await waitForBlock(bot, sourcePos, 'barrel')

    let carried = inventoryItemCount(bot, task.minecraft_item)
    if (carried > task.amount) {
      throw new Error('actor carries more task cargo than expected: ' + carried)
    }

    if (carried < task.amount) {
      witnessPhase = 'source_interaction'; sampleWitness()
      const sourceContainer = await bot.openContainer(source)
      const remainingToWithdraw = task.amount - carried
      await sourceContainer.withdraw(item.id, null, remainingToWithdraw, null)
      // Exact-26.3 Mineflayer does not reliably project the player inventory
      // until the container window closes. Preserve the W3-qualified ordering:
      // settle the transaction, close the window, then inspect inventory.
      await sleep(500)
      await sourceContainer.close()
      await sleep(350)
      carried = await waitForInventoryCount(
        bot,
        task.minecraft_item,
        task.amount,
        5000
      )
    }

    witnessPhase = 'to_destination'; sampleWitness()
    const toDestination = await walkNear(bot, destinationPos.offset(-1, 0, 0))
    const destination = await waitForBlock(bot, destinationPos, 'barrel')

    witnessPhase = 'destination_interaction'; sampleWitness()
    const destinationContainer = await bot.openContainer(destination)
    const destinationBefore = containerItemCount(
      destinationContainer,
      task.minecraft_item
    )
    await destinationContainer.deposit(item.id, null, task.amount, null)
    // The container view is authoritative for the destination while the
    // window is open; the player inventory settles after the window closes.
    await sleep(750)
    const destinationCount = containerItemCount(
      destinationContainer,
      task.minecraft_item
    )
    await destinationContainer.close()
    await sleep(500)

    const remaining = await waitForInventoryCount(
      bot,
      task.minecraft_item,
      0,
      5000
    )

    return {
      schema: 'supracraft.active4x-actor-result/v0.1',
      operation_id: task.operation_id,
      task_id: task.task_id,
      cargo_id: task.cargo_id,
      actor_group_id: task.actor_group_id,
      semantic_resource: task.semantic_resource,
      minecraft_item: 'minecraft:' + task.minecraft_item,
      amount: task.amount,
      minecraft: { edition: 'java', version },
      client: 'mineflayer exact-26.3',
      source: task.source,
      destination: task.destination,
      movement: {
        to_source: toSource.distance,
        to_destination: toDestination.distance,
        total_grounded_distance: toSource.distance + toDestination.distance
      },
      destination_count_observed: destinationCount,
      remaining_inventory: remaining,
      result: (
        destinationCount === task.amount && remaining === 0
          ? 'delivered'
          : 'incomplete'
      )
    }
  } finally {
    witnessPhase = 'finished'; sampleWitness()
    clearInterval(witnessTimer)
    bot.quit('done')
  }
}

async function main () {
  let completed = loadCompleted()

  // Recover the normal restart window where a durable result exists but the
  // completed-set write did not occur yet.
  const existingTask = readJson(taskFile)
  const existingResult = readJson(resultFile)
  if (
    existingTask &&
    existingResult &&
    existingTask.operation_id === existingResult.operation_id &&
    existingResult.result === 'delivered'
  ) {
    completed.add(existingTask.operation_id)
    saveCompleted(completed)
  }

  atomicWrite(readyFile, {
    ready: true,
    minecraft_version: version,
    max_concurrent_actors: maxConcurrent,
    completed_operation_ids: [...completed].sort()
  })

  while (true) {
    const task = readJson(taskFile)
    if (!task) {
      await sleep(250)
      continue
    }

    if (completed.has(task.operation_id)) {
      await sleep(250)
      continue
    }

    try {
      const result = await executeTask(task)
      atomicWrite(resultFile, result)
      if (result.result !== 'delivered') {
        throw new Error('task did not reach delivered state')
      }
      completed.add(task.operation_id)
      saveCompleted(completed)
      atomicWrite(readyFile, {
        ready: true,
        minecraft_version: version,
        max_concurrent_actors: maxConcurrent,
        completed_operation_ids: [...completed].sort()
      })
    } catch (err) {
      const errorText = String(err && err.stack ? err.stack : err)
      console.error('D2B_TASK_ERROR ' + errorText)
      atomicWrite(resultFile, {
        schema: 'supracraft.active4x-actor-result/v0.1',
        operation_id: task.operation_id,
        task_id: task.task_id,
        cargo_id: task.cargo_id,
        result: 'error',
        error: errorText
      })
      await sleep(1000)
    }

    await sleep(250)
  }
}

main().catch(err => {
  console.error(err && err.stack ? err.stack : err)
  process.exit(1)
})
