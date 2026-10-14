#!/usr/bin/env node
'use strict'

const fs = require('fs')
const path = require('path')
const mineflayer = require('mineflayer')

const argv = process.argv.slice(2)
function arg (name, fallback = null) {
  const i = argv.indexOf(name)
  return i >= 0 ? argv[i + 1] : fallback
}
const host = arg('--host', '127.0.0.1')
const port = Number(arg('--port', '25571'))
const outputDir = arg('--output-dir', 'camera-output')
const manifestPath = arg('--manifest')
const mode = arg('--mode', 'probe')
const rconPassword = arg('--rcon-password', 'supracraft-local')
fs.mkdirSync(outputDir, { recursive: true })

const receiptPath = path.join(outputDir, 'camera-receipt.json')
const started = Date.now()
let settled = false

function finish (status, extra = {}, code = 0) {
  if (settled) return
  settled = true
  const receipt = {
    schema: 'supracraft-worldgen-camera-qualification/1',
    status,
    mode,
    mineflayer_version: require('mineflayer/package.json').version,
    host,
    port,
    elapsed_seconds: (Date.now() - started) / 1000,
    ...extra
  }
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + '\n')
  console.log(JSON.stringify(receipt, null, 2))
  try { bot.quit('camera qualification complete') } catch (_) {}
  setTimeout(() => process.exit(code), 200)
}

const bot = mineflayer.createBot({
  host,
  port,
  username: 'SupraCraftTourBot',
  auth: 'offline',
  version: false,
  hideErrors: false,
  checkTimeoutInterval: 5000
})

const timer = setTimeout(() => {
  finish('blocked', { blocker: 'mineflayer-spawn-timeout', spawned: false }, 0)
}, 35000)

bot.on('kicked', reason => {
  if (!settled) finish('blocked', { blocker: 'minecraft-kicked', kicked: String(reason), spawned: false }, 0)
})
bot.on('error', err => {
  if (!settled) finish('blocked', { blocker: 'mineflayer-error', error: String(err && err.stack ? err.stack : err), spawned: false }, 0)
})
bot.on('end', reason => {
  if (!settled) finish('blocked', { blocker: 'mineflayer-ended-before-completion', end_reason: String(reason), spawned: false }, 0)
})

bot.once('spawn', async () => {
  clearTimeout(timer)
  const base = {
    spawned: true,
    minecraft_version: bot.version,
    protocol_version: bot._client && bot._client.protocolVersion,
    position: bot.entity && bot.entity.position ? bot.entity.position.toArray() : null
  }

  if (mode === 'probe') {
    return finish('success', base, 0)
  }

  let viewer
  let Rcon
  try {
    viewer = require('prismarine-viewer').headless
    Rcon = require('rcon-client').Rcon
  } catch (err) {
    return finish('blocked', { ...base, blocker: 'renderer-dependencies-unavailable', error: String(err) }, 0)
  }

  let manifest
  try {
    manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  } catch (err) {
    return finish('failed', { ...base, blocker: 'invalid-tour-manifest', error: String(err) }, 2)
  }

  const sites = (manifest.sites || []).slice(0, 6)
  if (!sites.length) {
    return finish('failed', { ...base, blocker: 'tour-manifest-has-no-sites' }, 2)
  }

  let rcon
  try {
    rcon = await Rcon.connect({ host, port: 25572, password: rconPassword })
    await rcon.send('gamemode spectator SupraCraftTourBot')
    await rcon.send('effect give SupraCraftTourBot minecraft:night_vision infinite 0 true')
  } catch (err) {
    return finish('blocked', { ...base, blocker: 'local-rcon-control-failed', error: String(err) }, 0)
  }

  const output = path.join(outputDir, 'tour.mp4')
  let renderer
  try {
    renderer = viewer(bot, { output, frames: 900, width: 640, height: 360, viewDistance: 5, logFFMPEG: true })
  } catch (err) {
    try { await rcon.end() } catch (_) {}
    return finish('blocked', { ...base, blocker: 'headless-renderer-threw', error: String(err) }, 0)
  }
  if (!renderer) {
    try { await rcon.end() } catch (_) {}
    return finish('blocked', {
      ...base,
      blocker: 'prismarine-viewer-does-not-support-bot-version',
      prismarine_viewer_version: require('prismarine-viewer/package.json').version
    }, 0)
  }

  const visited = []
  let i = 0
  async function visit () {
    if (i >= sites.length) return
    const site = sites[i++]
    const p = site.position
    const look = site.look_at
    let cmd = `tp SupraCraftTourBot ${p[0]} ${p[1]} ${p[2]}`
    if (look) cmd += ` facing ${look[0]} ${look[1]} ${look[2]}`
    try {
      await rcon.send(cmd)
      visited.push({ site_id: site.site_id, category: site.category, position: p, look_at: look || null })
    } catch (err) {
      console.error('tour teleport failed', err)
    }
  }

  await visit()
  const visitTimer = setInterval(() => { visit().catch(console.error) }, 2200)

  renderer.once('close', async code => {
    clearInterval(visitTimer)
    try { await rcon.end() } catch (_) {}
    const exists = fs.existsSync(output)
    const size = exists ? fs.statSync(output).size : 0
    if (!exists || size < 1024) {
      return finish('blocked', {
        ...base,
        blocker: 'renderer-produced-no-usable-mp4',
        ffmpeg_exit_code: code,
        visited_sites: visited,
        output_size: size,
        prismarine_viewer_version: require('prismarine-viewer/package.json').version
      }, 0)
    }
    return finish('success', {
      ...base,
      prismarine_viewer_version: require('prismarine-viewer/package.json').version,
      rcon_client_version: require('rcon-client/package.json').version,
      ffmpeg_exit_code: code,
      output: 'tour.mp4',
      output_size: size,
      visited_sites: visited
    }, 0)
  })
})
