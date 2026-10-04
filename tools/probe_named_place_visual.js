const fs = require('fs')
const path = require('path')
const mineflayer = require('mineflayer')
const { Worker } = require('worker_threads')
const { Vec3 } = require('vec3')

const viewerRoot = path.dirname(require.resolve('prismarine-viewer/package.json'))
global.THREE = require(path.join(viewerRoot, 'node_modules/three'))
global.Worker = Worker

const { createCanvas } = require(path.join(viewerRoot, 'node_modules/node-canvas-webgl/lib'))
const { Viewer, WorldView, getBufferFromStream } = require('prismarine-viewer').viewer

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

async function createVisualSession () {
  stage('viewer:create')
  const canvas = createCanvas(640, 360)
  const renderer = new THREE.WebGLRenderer({ canvas })
  const viewer = new Viewer(renderer)

  if (!viewer.setVersion(bot.version)) {
    throw new Error('viewer rejected exact bot version')
  }

  const worldView = new WorldView(bot.world, 4, bot.entity.position)
  viewer.listen(worldView)
  await worldView.init(bot.entity.position)
  await viewer.waitForChunksToRender()

  stage('viewer:ready')
  return { canvas, renderer, viewer, worldView }
}

function inspectionAngles (position, target, playerHeight) {
  const eye = position.offset(0, playerHeight, 0)
  const delta = target.minus(eye)
  const yaw = Math.atan2(-delta.x, -delta.z)
  const groundDistance = Math.sqrt(delta.x * delta.x + delta.z * delta.z)
  const pitch = Math.atan2(delta.y, groundDistance)
  return { yaw, pitch }
}

async function syncVisualSession (session, cameraPosition = null, target = null) {
  const position = cameraPosition
    ? new Vec3(cameraPosition[0], cameraPosition[1], cameraPosition[2])
    : bot.entity.position.clone()
  const angles = cameraPosition
    ? inspectionAngles(position, new Vec3(target[0], target[1], target[2]), session.viewer.playerHeight)
    : { yaw: bot.entity.yaw, pitch: bot.entity.pitch }

  await session.worldView.updatePosition(position, true)
  await session.viewer.waitForChunksToRender()
  session.viewer.setFirstPersonCamera(position, angles.yaw, angles.pitch)

  // setFirstPersonCamera uses the viewer's normal camera tween. Let that tween
  // reach the requested position before taking the deterministic frame.
  await sleep(80)
  session.viewer.update()
  return position
}

async function captureOneFrame (session, name, cameraPosition = null, target = null) {
  const out = path.join(outputDir, name + '.jpg')
  stage('capture:' + name + ':sync')
  const renderedFrom = await syncVisualSession(session, cameraPosition, target)

  stage('capture:' + name + ':render')
  session.renderer.render(session.viewer.scene, session.viewer.camera)
  const imageStream = session.canvas.createJPEGStream({
    bufsize: 4096,
    quality: 0.95,
    progressive: false
  })
  const jpeg = await getBufferFromStream(imageStream)
  fs.writeFileSync(out, jpeg)

  if (jpeg.length < 5000) {
    throw new Error('rendered frame unexpectedly small: ' + name + ' bytes=' + jpeg.length)
  }

  stage('capture:' + name + ':done')
  return {
    name,
    path: out,
    bytes: jpeg.length,
    camera_position: [
      Number(renderedFrom.x.toFixed(3)),
      Number(renderedFrom.y.toFixed(3)),
      Number(renderedFrom.z.toFixed(3))
    ],
    bot_position: pos()
  }
}

async function closeVisualSession (session) {
  if (!session) return
  stage('viewer:close')
  for (const worker of session.viewer.world.workers) {
    if (worker && typeof worker.terminate === 'function') {
      await worker.terminate()
    }
  }
  // node-canvas-webgl does not provide the browser animation-frame hooks that
  // Three.js dispose() expects. The disposable qualification process owns this
  // renderer, so terminating the worker threads is the required bounded cleanup.
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
  let visualSession

  try {
    // The approach is a real grounded traversal rep, not a creative-flight
    // displacement. The presentation plane is at y=69, so feet belong at y=70.
    bot.chat('/gamemode survival @s')
    await sleep(500)
    await teleportAndLook([0, 70, 24], [0, 74, 0])
    visualSession = await createVisualSession()
    views.push(await captureOneFrame(visualSession, '01_approach'))

    const walkStart = pos()
    stage('walk:start')
    bot.setControlState('forward', true)
    await sleep(2500)
    bot.setControlState('forward', false)
    await sleep(500)
    const walkEnd = pos()
    stage('walk:end')
    views.push(await captureOneFrame(visualSession, '02_after_walk'))

    // Remaining views are presentation-only inspection cameras. Keep the
    // traversal actor grounded where it walked and move only the viewer camera.
    views.push(await captureOneFrame(
      visualSession, '03_three_quarter', [16, 75, 16], [0, 76, 0]
    ))
    views.push(await captureOneFrame(
      visualSession, '04_interior', [0, 71, 2], [0, 74, 0]
    ))
    views.push(await captureOneFrame(
      visualSession, '05_landmark_distance', [0, 84, 42], [0, 76, 0]
    ))

    const dx = walkEnd[0] - walkStart[0]
    const dy = walkEnd[1] - walkStart[1]
    const dz = walkEnd[2] - walkStart[2]
    const walkDistance = Math.sqrt(dx * dx + dy * dy + dz * dz)

    const result = {
      schema: 'supracraft.named-place-visual-smoke/v0.3',
      minecraft: { edition: 'java', version: '26.3' },
      renderer: {
        name: 'prismarine-viewer-core',
        semantic_authority: false,
        client_world_source: 'mineflayer exact-26.3 connection',
        asset_policy: 'viewer 26.1 presentation assets via local compatibility bridge',
        capture: 'node-canvas-webgl after explicit chunk-render completion',
        render_view_distance_chunks: 4,
        inspection_camera_policy: 'viewer-only; traversal actor remains grounded'
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
  } finally {
    await closeVisualSession(visualSession)
  }
}

main()
  .catch(err => {
    fs.writeFileSync(resultFile, JSON.stringify({
      schema: 'supracraft.named-place-visual-smoke/v0.3',
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(async () => {
    try { bot.clearControlStates() } catch {}
    bot.quit('done')
  })
