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
const { getVersion } = require(path.join(viewerRoot, 'viewer/lib/version'))

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25571')
const username = process.env.MC_USER || 'SupraCraftVisual'
const readyFile = process.env.BOT_READY_FILE
const opReadyFile = process.env.OP_READY_FILE
const outputDir = process.env.VISUAL_OUTPUT_DIR
const resultFile = process.env.VISUAL_RESULT_FILE
const routeFile = process.env.VISUAL_ROUTE_FILE

if (!readyFile || !opReadyFile || !outputDir || !resultFile || !routeFile) {
  throw new Error('required visual-probe environment is missing')
}

const visualRoute = JSON.parse(fs.readFileSync(routeFile, 'utf8'))
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

function lerp (a, b, t) {
  return a + (b - a) * t
}

function lerpVec (a, b, t) {
  return [
    lerp(a[0], b[0], t),
    lerp(a[1], b[1], t),
    lerp(a[2], b[2], t)
  ]
}

function setDirectCamera (session, cameraPosition, target) {
  const position = new Vec3(cameraPosition[0], cameraPosition[1], cameraPosition[2])
  const angles = inspectionAngles(
    position,
    new Vec3(target[0], target[1], target[2]),
    session.viewer.playerHeight
  )
  session.viewer.camera.position.set(
    position.x,
    position.y + session.viewer.playerHeight,
    position.z
  )
  session.viewer.camera.rotation.set(angles.pitch, angles.yaw, 0, 'ZYX')
  session.viewer.update()
  return position
}

function setDirectBotCamera (session) {
  const position = bot.entity.position.clone()
  session.viewer.camera.position.set(
    position.x,
    position.y + session.viewer.playerHeight,
    position.z
  )
  session.viewer.camera.rotation.set(bot.entity.pitch, bot.entity.yaw, 0, 'ZYX')
  session.viewer.update()
  return position
}

async function writeSequenceFrame (
  session,
  dirName,
  frameIndex,
  cameraPosition = null,
  target = null,
  useBotCamera = false
) {
  const renderedFrom = useBotCamera
    ? setDirectBotCamera(session)
    : setDirectCamera(session, cameraPosition, target)

  session.renderer.render(session.viewer.scene, session.viewer.camera)
  const imageStream = session.canvas.createJPEGStream({
    bufsize: 4096,
    quality: 0.9,
    progressive: false
  })
  const jpeg = await getBufferFromStream(imageStream)
  const framesDir = path.join(outputDir, dirName)
  fs.mkdirSync(framesDir, { recursive: true })
  const out = path.join(framesDir, String(frameIndex).padStart(4, '0') + '.jpg')
  fs.writeFileSync(out, jpeg)
  return {
    path: out,
    bytes: jpeg.length,
    camera_position: [
      Number(renderedFrom.x.toFixed(3)),
      Number(renderedFrom.y.toFixed(3)),
      Number(renderedFrom.z.toFixed(3))
    ]
  }
}

async function captureGroundedProofWalk (session, durationMs, fps) {
  const frames = []
  const intervalMs = 1000 / fps
  const started = Date.now()
  const deadline = started + durationMs
  let frameIndex = 0
  let nextCapture = started

  stage('walk:start')
  bot.setControlState('forward', true)
  const stopWalkTimer = setTimeout(() => bot.setControlState('forward', false), durationMs)

  while (Date.now() < deadline) {
    frames.push(await writeSequenceFrame(
      session,
      'proof-walk-frames',
      frameIndex,
      null,
      null,
      true
    ))
    frameIndex += 1
    nextCapture += intervalMs
    const delay = nextCapture - Date.now()
    if (delay > 0) await sleep(delay)
  }

  clearTimeout(stopWalkTimer)
  bot.setControlState('forward', false)
  if (Date.now() < deadline) await sleep(deadline - Date.now())
  await sleep(300)
  stage('walk:end')
  return frames
}

async function captureShot (session, shot, dirName, startIndex) {
  let frameIndex = startIndex
  const frameCount = Number(shot.frames)
  if (!Number.isInteger(frameCount) || frameCount < 2) {
    throw new Error('shot must request at least two frames: ' + shot.id)
  }

  stage('cinematic:' + shot.id + ':start')
  for (let i = 0; i < frameCount; i++) {
    const denominator = shot.closed_loop ? frameCount : Math.max(1, frameCount - 1)
    const t = i / denominator
    let cameraPosition
    let target

    if (shot.kind === 'linear') {
      cameraPosition = lerpVec(shot.from, shot.to, t)
      target = lerpVec(shot.target_from, shot.target_to, t)
    } else if (shot.kind === 'pan') {
      cameraPosition = shot.position
      target = lerpVec(shot.target_from, shot.target_to, t)
    } else if (shot.kind === 'orbit') {
      const degrees = lerp(Number(shot.start_degrees), Number(shot.end_degrees), t)
      const radians = degrees * Math.PI / 180
      cameraPosition = [
        Number(shot.center[0]) + Math.cos(radians) * Number(shot.radius),
        Number(shot.camera_y),
        Number(shot.center[2]) + Math.sin(radians) * Number(shot.radius)
      ]
      target = shot.look_at
    } else {
      throw new Error('unsupported cinematic shot kind: ' + shot.kind)
    }

    await writeSequenceFrame(
      session,
      dirName,
      frameIndex,
      cameraPosition,
      target,
      false
    )
    frameIndex += 1
  }
  stage('cinematic:' + shot.id + ':done')
  return frameIndex
}

async function capturePresentationSequences (session, standard) {
  if (!standard || standard.schema !== 'supracraft.realestate-walkthrough/v0.1') {
    throw new Error('missing real-estate walkthrough standard')
  }

  // Center the presentation world view once. All authored camera motion remains
  // within this loaded four-chunk envelope; only the camera moves after this.
  await session.worldView.updatePosition(new Vec3(0, 74, 4), true)
  await session.viewer.waitForChunksToRender()

  let realestateFrames = 0
  for (const shot of standard.realestate_shots) {
    realestateFrames = await captureShot(
      session,
      shot,
      'realestate-frames',
      realestateFrames
    )
  }

  const loopFrames = await captureShot(
    session,
    standard.loop_shot,
    'loop-frames',
    0
  )

  return {
    standard: standard.schema,
    realestate_fps: Number(standard.realestate_fps),
    realestate_frames: realestateFrames,
    loop_fps: Number(standard.loop_fps),
    loop_frames: loopFrames,
    realestate_authority: 'presentation_only',
    loop_authority: 'presentation_only'
  }
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
    const walkDurationMs = Number(visualRoute.grounded_walk.target_duration_ms || 2500)
    const proofWalkFps = Number(visualRoute.grounded_walk.capture_fps || 12)
    const walkthroughFrames = await captureGroundedProofWalk(
      visualSession,
      walkDurationMs,
      proofWalkFps
    )
    const walkEnd = pos()
    views.push(await captureOneFrame(visualSession, '02_after_walk'))

    // Remaining views are presentation-only inspection cameras. Keep the
    // traversal actor grounded where it walked and move only the viewer camera.
    views.push(await captureOneFrame(
      visualSession, '03_three_quarter', [16, 75, 16], [0, 76, 0]
    ))
    views.push(await captureOneFrame(
      // Put the viewer just inside the south doorway and look down the central
      // aisle at eye level. This exposes use-space depth without the previous
      // steep upward composition.
      visualSession, '04_interior', [0, 70.1, 5], [0, 72, -3]
    ))
    views.push(await captureOneFrame(
      // Recognition-cue detail: from the threshold, turn across the working
      // bay so the required hay-storage cue is directly reviewable rather
      // than inferred from the model contract.
      visualSession, '04b_hay_storage', [0, 70.5, 5.5], [5, 71.5, 4]
    ))
    views.push(await captureOneFrame(
      visualSession, '05_landmark_distance', [0, 84, 42], [0, 76, 0]
    ))
    views.push(await captureOneFrame(
      visualSession, '06_terrain_probe', [0, 96, 16], [0, 69, 16]
    ))

    const presentation = await capturePresentationSequences(
      visualSession,
      visualRoute.presentation_standard
    )

    const dx = walkEnd[0] - walkStart[0]
    const dy = walkEnd[1] - walkStart[1]
    const dz = walkEnd[2] - walkStart[2]
    const walkDistance = Math.sqrt(dx * dx + dy * dy + dz * dz)

    const renderAssetVersion = getVersion(bot.version)
    const result = {
      schema: 'supracraft.named-place-visual-smoke/v0.5',
      subject: {
        class: visualRoute.subject_class,
        id: visualRoute.subject_id,
        display_name: visualRoute.display_name
      },
      minecraft: { edition: 'java', version: '26.3' },
      renderer: {
        name: 'prismarine-viewer-core',
        semantic_authority: false,
        client_world_source: 'mineflayer exact-26.3 connection',
        asset_policy: renderAssetVersion === bot.version
          ? 'exact-version viewer assets'
          : 'compatible viewer asset fallback',
        presentation_asset_version: renderAssetVersion,
        capture: 'node-canvas-webgl after explicit chunk-render completion',
        render_view_distance_chunks: 4,
        inspection_camera_policy: 'viewer-only; traversal actor remains grounded'
      },
      traversal: {
        start: walkStart,
        end: walkEnd,
        distance: Number(walkDistance.toFixed(3)),
        passed: walkDistance >= 1.0,
        walkthrough_frames: walkthroughFrames.length,
        walkthrough_target_duration_ms: walkDurationMs,
        proof_walk_fps: proofWalkFps,
        authority: 'grounded_traversal_evidence'
      },
      presentation: {
        ...presentation,
        expected_artifacts: {
          proof_walk_mp4: 'redroof-proof-walk.mp4',
          compatibility_alias_mp4: 'redroof-walkthrough.mp4',
          realestate_mp4: 'redroof-realestate-walkthrough.mp4',
          loop_gif: 'redroof-realestate-loop.gif'
        }
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
      schema: 'supracraft.named-place-visual-smoke/v0.5',
      result: 'error',
      error: String(err && err.stack ? err.stack : err)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(async () => {
    try { bot.clearControlStates() } catch {}
    bot.quit('done')
  })
