// Public-safe Java 26.3 player cursor custody probe. No chat/OP/admin commands.
const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')

const files = {
  ready: process.env.CURSOR_BOT_READY,
  start: process.env.CURSOR_BOT_START,
  held: process.env.CURSOR_BOT_HELD,
  release: process.env.CURSOR_BOT_RELEASE,
  done: process.env.CURSOR_BOT_DONE,
  receipt: process.env.CURSOR_BOT_RESULT
}
for (const [key, value] of Object.entries(files)) {
  if (!value) throw new Error('missing CURSOR_BOT_' + key.toUpperCase() + ' environment')
}
const receipt = { schema: 'supracraft.cursor-hold-probe/v0.1', milestones: {}, version: '26.3' }
function store () { fs.writeFileSync(files.receipt, JSON.stringify(receipt, null, 2) + '\n') }
const bot = mineflayer.createBot({host: '127.0.0.1', port: 25575, username: 'SupraCraftProbe', auth: 'offline', version: '26.3'})
// Bounded metadata-only diagnostics: no packet payloads, credentials or worlds.
receipt.interaction_packets = []
if (bot._client) {
  bot._client.on('packet', (_data, meta) => {
    const name = meta && meta.name
    if (!name || !/window|screen|container|block|position|teleport|slot/i.test(name)) return
    receipt.interaction_packets.push({ name, state: meta.state, at: Date.now() })
    if (receipt.interaction_packets.length > 24) receipt.interaction_packets.shift()
  })
}
bot.on('windowOpen', w => { receipt.window_open_event = { at: Date.now(), type: w.type || null }; store() })
let finished = false
function finish (code) {
  if (finished) return
  finished = true
  store()
  try { bot.quit('cursor-hold probe complete') } catch {}
  setTimeout(() => process.exit(code), 300)
}
async function awaitGate (file, label) {
  const until = Date.now() + 30000
  while (Date.now() < until && !fs.existsSync(file)) await bot.waitForTicks(2)
  if (!fs.existsSync(file)) throw new Error('timed out: ' + label)
}
bot.on('error', e => { receipt.error = String(e.stack || e); store() })
bot.on('kicked', reason => { receipt.kicked = String(reason); store() })
bot.on('end', reason => { receipt.end = String(reason); store() })
bot.once('spawn', async () => {
  receipt.milestones.spawn = Date.now()
  receipt.negotiated_version = bot.version
  receipt.protocol_version = bot.protocolVersion
  store()
  fs.writeFileSync(files.ready, 'ready\n')
  try {
    await awaitGate(files.start, 'official source and player setup')
    // The controller's teleport command and source readiness marker may
    // precede the client-side position update. Do not open a remote chest.
    const positionedDeadline = Date.now() + 30000
    let positioned = false
    while (Date.now() < positionedDeadline) {
      const p = bot.entity.position
      if (Math.abs(p.x - 0.5) < 3 && Math.abs(p.z - 2.5) < 3) {
        positioned = true
        break
      }
      await bot.waitForTicks(2)
    }
    if (!positioned) throw new Error('controller teleport not observed by player')
    await bot.waitForTicks(3)
    const chest = bot.blockAt(new Vec3(0, 70, 0))
    if (!chest || chest.name !== 'chest') throw new Error('keeper chest missing')
    receipt.preopen = {
      at: Date.now(),
      player_position: bot.entity.position.toArray(),
      chest_position: chest.position.toArray(),
      chest_name: chest.name,
      above_chest_name: (bot.blockAt(new Vec3(0, 71, 0)) || {}).name || null,
      distance_to_chest_block: bot.entity.position.distanceTo(chest.position),
      can_see_chest: typeof bot.canSeeBlock === 'function' ? bot.canSeeBlock(chest) : null
    }
    receipt.milestones.open_attempt = Date.now()
    store()
    const window = await bot.openContainer(chest)
    receipt.milestones.open_returned = Date.now()
    store()
    const original = (typeof window.containerItems === 'function' ? window.containerItems() : window.items())
      .find(item => item.name === 'redstone_block')
    if (!original || original.slot !== 0) throw new Error('core not in chest slot 0: ' + JSON.stringify(original || null))
    receipt.window = {inventory_start: window.inventoryStart, original_slot: original.slot}
    await bot.clickWindow(original.slot, 0, 0)
    await bot.waitForTicks(5)
    receipt.milestones.cursor_held = Date.now()
    store()
    fs.writeFileSync(files.held, 'held\n')
    await awaitGate(files.release, 'official server cursor and chest predicates')
    if (typeof window.inventoryStart !== 'number') throw new Error('unknown inventoryStart')
    // Deposit the exact original cursor-held item in an empty main inventory slot.
    await bot.clickWindow(window.inventoryStart, 0, 0)
    await bot.waitForTicks(5)
    const playerCore = bot.inventory.items().some(item => item.name === 'redstone_block')
    if (!playerCore) throw new Error('cursor deposit did not reach player inventory')
    window.close()
    receipt.milestones.core_deposited = Date.now()
    receipt.player_inventory_has_core = playerCore
    store()
    fs.writeFileSync(files.done, 'done\n')
    finish(0)
  } catch (e) {
    receipt.error = String(e.stack || e)
    finish(1)
  }
})
setTimeout(() => {receipt.error = receipt.error || 'probe timeout'; finish(2)}, 105000)
