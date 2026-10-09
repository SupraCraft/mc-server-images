const fs = require('fs')
const path = require('path')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const stateDir = process.env.HIL_STATE_DIR || '/hil-state'
const host = process.env.MC_HOST || 'minecraft'
const port = Number(process.env.MC_PORT || '25565')
const version = process.env.MC_VERSION || '26.3'
const mode = process.env.HIL_MODE || 'interact'
const username = process.env.HIL_USER || 'TwoRiversHIL'
const caravanUser = process.env.CARAVAN_USER || 'TwoRiversD2B'

fs.mkdirSync(stateDir, { recursive: true })
const readyFile = path.join(stateDir, 'ready.json')
const goFile = path.join(stateDir, 'go')
const resultFile = path.join(stateDir, `result-${mode}.json`)

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function atomicWrite (file, value) {
  const tmp = file + '.tmp'
  fs.writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n')
  fs.renameSync(tmp, file)
}

async function waitFile (file, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (fs.existsSync(file)) return
    await sleep(100)
  }
  throw new Error('timeout waiting for ' + file)
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
  let last = null
  while (Date.now() < deadline) {
    const block = bot.blockAt(pos)
    if (block) {
      last = block.name
      if (block.name === expectedName) return block
    }
    await sleep(100)
  }
  throw new Error(`timeout waiting for ${expectedName} at ${pos}; last=${last}`)
}

async function waitForBlockName (bot, pos, expectedName, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs
  let last = null
  while (Date.now() < deadline) {
    const block = bot.blockAt(pos)
    last = block ? block.name : null
    if (last === expectedName) return last
    await sleep(100)
  }
  throw new Error(
    `block settlement timeout at ${pos}; expected=${expectedName}; last=${last}`
  )
}

async function walkNear (bot, target, stopDistance = 1.35, timeoutMs = 30000) {
  const started = bot.entity.position.clone()
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const pos = bot.entity.position
    if (pos.distanceTo(target) <= stopDistance) {
      bot.setControlState('forward', false)
      return started.distanceTo(pos)
    }
    await bot.lookAt(target.offset(0, 0.5, 0), true)
    bot.setControlState('forward', true)
    await sleep(100)
  }
  bot.setControlState('forward', false)
  throw new Error('walk timeout to ' + target.toString())
}

// Keep the no-pathfinder HIL actor physically grounded before a mining
// action. Upstream Mineflayer measures dig time before its internal lookAt;
// the official server measures at packet receipt. Movement/airborne transitions
// can therefore make Mineflayer's local predicted air premature.
async function settleOnGround (bot, timeoutMs = 5000) {
  bot.setControlState('forward', false)
  let stable = 0
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (bot.entity?.onGround === true) {
      stable++
      if (stable >= 5) return
    } else {
      stable = 0
    }
    await sleep(50)
  }
  throw new Error('ground settlement timeout before dig')
}

// One bounded CI-only timing hypothesis: Mineflayer locally predicts block air
// when its timer elapses, while vanilla server break progress is tick-driven.
// Retain Mineflayer's native packet sequence; delay only its FINISH timer by
// 25 percent. Never infer server acceptance from this client-side promise.
async function digWithBoundedMargin (bot, block, target) {
  const original = bot.digTime
  const estimated = original(block)
  const buffered = Math.ceil(estimated * 1.25)
  if (!Number.isFinite(estimated) || estimated <= 0 || buffered > 20000) {
    throw new Error('D3 bounded dig-time admission rejected')
  }
  bot.digTime = candidate => Math.ceil(original(candidate) * 1.25)
  try {
    console.log('D3_DIG_TIME_TREATMENT ' + JSON.stringify({
      target, base_ms: estimated, margin_ms: buffered
    }))
    await bot.dig(block, true, 'raycast')
  } finally {
    bot.digTime = original
  }
}

function invCount (bot, name) {
  return bot.inventory.items()
    .filter(item => item.name === name)
    .reduce((sum, item) => sum + item.count, 0)
}

function containerCount (container, name) {
  return container.containerItems()
    .filter(item => item.name === name)
    .reduce((sum, item) => sum + item.count, 0)
}

async function waitInv (bot, name, expected, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs
  let last = invCount(bot, name)
  while (Date.now() < deadline) {
    last = invCount(bot, name)
    if (last === expected) return
    await sleep(100)
  }
  throw new Error(`inventory timeout ${name}: expected=${expected} last=${last}`)
}

async function waitCaravan (bot, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs
  let minDistance = null
  while (Date.now() < deadline) {
    const entity = bot.players[caravanUser] && bot.players[caravanUser].entity
    if (entity) {
      const d = bot.entity.position.distanceTo(entity.position)
      minDistance = minDistance === null ? d : Math.min(minDistance, d)
      if (d <= 32) return { seen: true, min_distance: minDistance }
    }
    await sleep(100)
  }
  return { seen: false, min_distance: minDistance }
}

async function main () {
  const bot = mineflayer.createBot({
    host,
    port,
    username,
    version,
    auth: 'offline'
  })
  bot.on('kicked', reason => console.log('D3_REHEARSAL_KICKED ' + JSON.stringify(reason)))
  bot.on('error', err => console.log('D3_REHEARSAL_ERROR ' + String(err && err.stack ? err.stack : err)))

  try {
    await waitSpawn(bot)
    await sleep(500)
    atomicWrite(readyFile, {
      ready: true,
      mode,
      username,
      minecraft_version: version,
      position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z]
    })

    if (mode === 'rejoin') {
      atomicWrite(resultFile, {
        schema: 'supracraft.active4x-d3-rehearsal-client/v0.1',
        mode,
        username,
        minecraft: { edition: 'java', version },
        joined: true,
        result: 'PASS'
      })
      return
    }

    // D3-R1 read-only post-failure diagnostic: a fresh client observes streamed
    // world blocks, independent of the original client's optimistic dig state.
    // These observations are advisory; the stock server markers remain authority.
    if (mode === 'diagnose') {
      const targets = {
        obstruction: new Vec3(2, 70, 16),
        damage: new Vec3(6, 70, 16)
      }
      const blocks = {}
      for (const [name, pos] of Object.entries(targets)) {
        const deadline = Date.now() + 10000
        let block = null
        while (Date.now() < deadline) {
          block = bot.blockAt(pos)
          if (block) break
          await sleep(100)
        }
        blocks[name] = {
          position: [pos.x, pos.y, pos.z],
          name: block ? block.name : null,
          observed: Boolean(block)
        }
      }
      atomicWrite(resultFile, {
        schema: 'supracraft.active4x-d3-fresh-client-diagnostic/v0.1',
        mode,
        minecraft: { edition: 'java', version },
        blocks,
        note: 'Fresh chunk/block observation only; not stock-client acceptance',
        result: Object.values(blocks).every(x => x.observed) ? 'OBSERVED' : 'INCOMPLETE'
      })
      return
    }

    await waitFile(goFile, 60000)

    const starterPos = new Vec3(-8, 70, 12)
    const tradeInputPos = new Vec3(-6, 70, 12)
    const tradeOutputPos = new Vec3(-4, 70, 12)
    const buildInputPos = new Vec3(0, 70, 12)
    const obstructPos = new Vec3(2, 70, 16)
    const damagePos = new Vec3(6, 70, 16)

    const wheat = bot.registry.itemsByName.wheat
    const bricks = bot.registry.itemsByName.bricks
    if (!wheat || !bricks) throw new Error('exact-26.3 registry missing HIL items')

    const movement = { total: 0 }
    movement.total += await walkNear(bot, starterPos.offset(1, 0, 0))
    const starter = await waitForBlock(bot, starterPos, 'barrel')
    const starterContainer = await bot.openContainer(starter)
    await starterContainer.withdraw(wheat.id, null, 2, null)
    await sleep(300)
    await starterContainer.withdraw(bricks.id, null, 4, null)
    await sleep(500)
    await starterContainer.close()
    await sleep(350)
    await waitInv(bot, 'wheat', 2)
    await waitInv(bot, 'bricks', 4)

    const caravan = await waitCaravan(bot)

    movement.total += await walkNear(bot, tradeInputPos.offset(1, 0, 0))
    const tradeInput = await waitForBlock(bot, tradeInputPos, 'barrel')
    const tradeContainer = await bot.openContainer(tradeInput)
    await tradeContainer.deposit(wheat.id, null, 2, null)
    await sleep(500)
    await tradeContainer.close()
    await sleep(350)
    await waitInv(bot, 'wheat', 0)

    // The trade-output barrel lies directly between the trade and build bays.
    // Take the authored clear aisle, rather than driving the forward-only
    // actor through a solid container or scanning the world for a path.
    movement.total += await walkNear(bot, new Vec3(-5, 70, 10), 0.65)
    movement.total += await walkNear(bot, new Vec3(1, 70, 10), 0.65)
    movement.total += await walkNear(bot, buildInputPos.offset(1, 0, 0))
    const buildInput = await waitForBlock(bot, buildInputPos, 'barrel')
    const buildContainer = await bot.openContainer(buildInput)
    await buildContainer.deposit(bricks.id, null, 4, null)
    await sleep(500)
    await buildContainer.close()
    await sleep(350)
    await waitInv(bot, 'bricks', 0)

    movement.total += await walkNear(bot, obstructPos.offset(0, 0, -1))
    const obstruction = await waitForBlock(bot, obstructPos, 'red_concrete')
    await settleOnGround(bot)
    console.log('D3_DIG_ATTEMPT ' + JSON.stringify({
      target: 'obstruction',
      player_position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z],
      target_position: [obstructPos.x, obstructPos.y, obstructPos.z],
      on_ground: bot.entity.onGround,
      game_mode: bot.game.gameMode,
      estimated_ms: bot.digTime(obstruction)
    }))
    await digWithBoundedMargin(bot, obstruction, 'obstruction')
    await waitForBlockName(bot, obstructPos, 'air', 5000)

    movement.total += await walkNear(bot, damagePos.offset(0, 0, -1))
    const damage = await waitForBlock(bot, damagePos, 'cobblestone')
    await settleOnGround(bot)
    console.log('D3_DIG_ATTEMPT ' + JSON.stringify({
      target: 'damage',
      player_position: [bot.entity.position.x, bot.entity.position.y, bot.entity.position.z],
      target_position: [damagePos.x, damagePos.y, damagePos.z],
      on_ground: bot.entity.onGround,
      game_mode: bot.game.gameMode,
      estimated_ms: bot.digTime(damage)
    }))
    await digWithBoundedMargin(bot, damage, 'damage')
    await waitForBlockName(bot, damagePos, 'air', 5000)

    const outputDeadline = Date.now() + 10000
    let tradeOutputCount = 0
    while (Date.now() < outputDeadline) {
      movement.total += await walkNear(bot, tradeOutputPos.offset(1, 0, 0))
      const output = await waitForBlock(bot, tradeOutputPos, 'barrel')
      const outputContainer = await bot.openContainer(output)
      await sleep(250)
      tradeOutputCount = containerCount(outputContainer, 'bricks')
      await outputContainer.close()
      if (tradeOutputCount >= 2) break
      await sleep(250)
    }
    if (tradeOutputCount < 2) {
      throw new Error('trade output did not materialize')
    }

    atomicWrite(resultFile, {
      schema: 'supracraft.active4x-d3-rehearsal-client/v0.1',
      mode,
      username,
      minecraft: { edition: 'java', version },
      caravan,
      movement,
      trade_output_bricks: tradeOutputCount,
      final_inventory: {
        wheat: invCount(bot, 'wheat'),
        bricks: invCount(bot, 'bricks')
      },
      actions: {
        trade_deposit: true,
        build_supply: true,
        obstruction_break: true,
        damage_break: true
      },
      result: caravan.seen ? 'PASS' : 'FAIL'
    })
  } finally {
    bot.quit('done')
  }
}

main().catch(err => {
  atomicWrite(resultFile, {
    schema: 'supracraft.active4x-d3-rehearsal-client/v0.1',
    mode,
    result: 'ERROR',
    error: String(err && err.stack ? err.stack : err)
  })
  console.error(err && err.stack ? err.stack : err)
  process.exit(1)
})
