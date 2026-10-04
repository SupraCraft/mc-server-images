const fs = require('fs')
const path = require('path')
const net = require('net')
const mineflayer = require('mineflayer')
const headlessViewer = require('prismarine-viewer').headless
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25571')
const username = process.env.MC_USER || 'SupraCraftVisual'
const readyFile = process.env.BOT_READY_FILE
const opReadyFile = process.env.OP_READY_FILE
const outputDir = process.env.VISUAL_OUTPUT_DIR
const resultFile = process.env.VISUAL_RESULT_FILE

if (!readyFile || !opReadyFile || !outputDir || !resultFile) {
  throw new Error('required visual-probe environment is missing')
}

fs.mkdirSync(outputDir, { recursive: true })

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function stage (name) {
  console.log('VISUAL_STAGE ' + name)
}

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

function pos () {
  const p = bot.entity.position
  return [Number(p.x.toFixed(3)), Number(p.y.toFixed(3)), Number(p.z.toFixed(3))]
}

async function teleportAndLook (xyz, target) {
  bot.chat('/tp @s ' + xyz.join(' '))
  await sleep(900)
  await bot.lookAt(new Vec3(target[0], target[1], target[2]), true)
  await sleep(500)
}

async function captureOneFrame (name) {
  const out = path.join(outputDir, name + '.jpg')
  stage('capture:' + name + ':listen')

  let server
  const framePromise = new Promise((resolve, reject) => {
    server = net.createServer(socket => {
      let buffer = Buffer.alloc(0)
      let expected = null
      socket.on('data', chunk => {
        buffer = Buffer.concat([buffer, chunk])
        if (expected === null && buffer.length >= 4) {
          expected = buffer.readUInt32LE(0)
          buffer = buffer.subarray(4)
        }
        if (expected !== null && buffer.length >= expected) {
          const jpeg = buffer.subarray(0, expected)
          fs.writeFileSync(out, jpeg)
          resolve({ bytes: jpeg.length })
          socket.destroy()
        }
      })
      socket.on('error', reject)
    })
    server.on('error', reject)
  })

  await new Promise((resolve, reject) => {
    server.listen(0, '127.0.0.1', resolve)
    server.once('error', reject)
  })
  const address = server.address()
  const renderPort = address.port

  stage('capture:' + name + ':render')
  let client
  try {
    client = headlessViewer(bot, {
      output: '127.0.0.1:' + renderPort,
      frames: 1,
      width: 640,
      height: 360,
      viewDistance: 2,
      jpegOptions: { quality: 0.95 }
    })
    if (!client) throw new Error('headless viewer rejected exact bot version')
  } catch (err) {
    server.close()
    throw err
  }

  const frame = await Promise.race([
    framePromise,
    sleep(30000).then(() => { throw new Error('headless frame timeout: ' + name) })
  ])
  server.close()
  if (client && typeof client.destroy === 'function') client.destroy()

  if (frame.bytes < 5000) {
    throw new Error('headless frame unexpectedly small: ' + name + ' bytes=' + frame.bytes)
  }

  stage('capture:' + name + ':done')
  return { name, path: out, bytes: frame.bytes, bot_position: pos() }
}

async function main () {
  stage('spawn:wait')
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })

  stage('spawn:ready')
  fs.writeFileSync(readyFile, JSON.stringify({ spawned: true, position: pos() }) + '\n')
  await waitFile(opReadyFile, 30000)
  stage('op:ready')

  const views = []

  await teleportAndLook([0, 72, 24], [0, 76, 0])
  views.push(await captureOneFrame('01_approach'))

  const walkStart = pos()
  stage('walk:start')
  bot.setControlState('forward', true)
  await sleep(1800)
  bot.setControlState('forward', false)
  await sleep(500)
  const walkEnd = pos()
  stage('walk:end')
  views.push(await captureOneFrame('02_after_walk'))

  await teleportAndLook([16, 75, 16], [0, 76, 0])
  views.push(await captureOneFrame('03_three_quarter'))

  await teleportAndLook([0, 73, 1], [0, 74, 0])
  views.push(await captureOneFrame('04_interior'))

  await teleportAndLook([0, 84, 42], [0, 76, 0])
  views.push(await captureOneFrame('05_landmark_distance'))

  const dx = walkEnd[0] - walkStart[0]
  const dy = walkEnd[1] - walkStart[1]
  const dz = walkEnd[2] - walkStart[2]
  const walkDistance = Math.sqrt(dx * dx + dy * dy + dz * dz)

  const result = {
    schema: 'supracraft.named-place-visual-smoke/v0.2',
    minecraft: { edition: 'java', version: '26.3' },
    renderer: {
      name: 'prismarine-viewer-headless',
      semantic_authority: false,
      client_world_source: 'mineflayer exact-26.3 connection',
      asset_policy: 'viewer 26.x compatible assets',
      capture: 'node-canvas-webgl JPEG stream'
    },
    traversal: {
      start: walkStart,
      end: walkEnd,
      distance: Number(walkDistance.toFixed(3)),
      passed: walkDistance >= 1.0
    },
    views,
    result: walkDistance >= 1.0 ? 'qualified_render_smoke' : 'failed_traversal'
  }

  fs.writeFileSync(resultFile, JSON.stringify(result, null, 2) + '\n')
  if (!result.traversal.passed) process.exitCode = 2
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.named-place-visual-smoke/v0.2',
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(async () => {
    try { bot.clearControlStates() } catch {}
    bot.quit('done')
  })
