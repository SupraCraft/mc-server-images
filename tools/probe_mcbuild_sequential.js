const fs = require('fs')
const readline = require('readline')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const port = Number(process.env.MC_PORT || '25571')
const planPath = process.env.MCBUILD_PLAN
const resultPath = process.env.BOT_RESULT_FILE
if (!planPath || !resultPath) throw new Error('MCBUILD_PLAN and BOT_RESULT_FILE are required')

const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'))
const result = {
  schema: 'supracraft.fixture-assisted-mcbuild-worker/v0.1',
  requested_version: '26.3',
  mineflayer_version: require('mineflayer/package.json').version,
  minecraft_data_version: require('minecraft-data/package.json').version,
  minecraft_protocol_version: require('minecraft-protocol/package.json').version,
  packet_count: 0,
  actions: [],
  completed: false
}

function emitControl (obj) {
  process.stdout.write(JSON.stringify(obj) + '\n')
}
function save () {
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2) + '\n')
}
function normProps (block) {
  const raw = block && typeof block.getProperties === 'function' ? block.getProperties() : {}
  const out = {}
  for (const [k, v] of Object.entries(raw)) out[k] = String(v)
  return out
}

const rl = readline.createInterface({ input: process.stdin })
const messages = []
const waiters = []
rl.on('line', line => {
  let msg
  try { msg = JSON.parse(line) } catch { return }
  const waiter = waiters.shift()
  if (waiter) waiter(msg)
  else messages.push(msg)
})
function nextMessage () {
  if (messages.length) return Promise.resolve(messages.shift())
  return new Promise(resolve => waiters.push(resolve))
}
async function waitPrepared (id) {
  while (true) {
    const msg = await nextMessage()
    if (msg && msg.type === 'prepared' && msg.id === id) return msg
    if (msg && msg.type === 'abort') throw new Error('controller aborted: ' + (msg.reason || 'unknown'))
  }
}
async function waitForPreparation (action) {
  const deadline = Date.now() + 15000
  while (Date.now() < deadline) {
    const item = bot.inventory.items().find(x => x.name === action.item)
    const p = bot.entity.position
    const target = action.bot_position
    const positioned = Math.abs(p.x - target[0]) < 0.8 &&
      Math.abs(p.y - target[1]) < 1.1 &&
      Math.abs(p.z - target[2]) < 0.8
    if (item && positioned) return item
    await bot.waitForTicks(2)
  }
  throw new Error('controller preparation did not converge for ' + action.id)
}

const bot = mineflayer.createBot({
  host: '127.0.0.1',
  port,
  username: 'SupraBuildProbe',
  auth: 'offline',
  version: '26.3'
})

bot.on('error', err => {
  result.error = String(err && err.stack ? err.stack : err)
  save()
})
bot.on('kicked', reason => {
  result.kicked = String(reason)
  save()
})
if (bot._client) {
  bot._client.on('packet', (_data, meta) => {
    result.packet_count += 1
    result.last_packet = { name: meta && meta.name, state: meta && meta.state }
  })
}

bot.once('spawn', async () => {
  result.negotiated_version = bot.version
  result.protocol_version = bot.protocolVersion
  emitControl({ type: 'ready', version: bot.version, protocol: bot.protocolVersion })

  try {
    for (let index = 0; index < plan.actions.length; index++) {
      const action = plan.actions[index]
      emitControl({
        type: 'prepare',
        index,
        id: action.id,
        item: action.item,
        bot_position: action.bot_position
      })
      await waitPrepared(action.id)
      const item = await waitForPreparation(action)
      await bot.equip(item, 'hand')
      await bot.waitForTicks(2)

      const ref = new Vec3(...action.reference.at)
      const face = new Vec3(...action.reference.face)
      const target = new Vec3(...action.at)
      const reference = bot.blockAt(ref)
      if (!reference || reference.name === 'air') {
        throw new Error('reference unavailable for ' + action.id + ' at ' + ref)
      }

      const before = bot.blockAt(target)
      const receipt = {
        index,
        id: action.id,
        at: action.at,
        reference: action.reference,
        item: action.item,
        desired_state: action.desired_state,
        before: before ? before.name : null,
        bot_position_before: bot.entity.position.toArray()
      }

      await bot.placeBlock(reference, face)
      await bot.waitForTicks(6)

      const after = bot.blockAt(target)
      receipt.after = after ? after.name : null
      receipt.after_state_id = after ? after.stateId : null
      receipt.after_properties = normProps(after)
      receipt.bot_position_after = bot.entity.position.toArray()

      const blockOk = receipt.after === action.expected_block
      const propsOk = Object.entries(action.expected_properties || {})
        .every(([k, v]) => receipt.after_properties[k] === String(v))
      receipt.qualified = blockOk && propsOk
      result.actions.push(receipt)
      save()

      if (!receipt.qualified) {
        throw new Error('action did not realize requested state: ' + JSON.stringify(receipt))
      }
      emitControl({ type: 'placed', index, id: action.id, state_id: receipt.after_state_id })
    }

    result.completed = true
    result.action_count = result.actions.length
    save()
    emitControl({ type: 'complete', actions: result.actions.length, packet_count: result.packet_count })
    try { bot.quit('fixture-assisted build complete') } catch {}
    setTimeout(() => process.exit(0), 250)
  } catch (err) {
    result.error = String(err && err.stack ? err.stack : err)
    save()
    emitControl({ type: 'error', error: result.error })
    try { bot.quit('fixture-assisted build failed') } catch {}
    setTimeout(() => process.exit(1), 250)
  }
})

setTimeout(() => {
  if (!result.completed) {
    result.error = result.error || 'fixture-assisted build timed out'
    save()
    emitControl({ type: 'error', error: result.error })
    process.exit(2)
  }
}, 120000)
