const fs = require('fs')
const path = require('path')
const mineflayer = require('mineflayer')
const { mineflayer: mineflayerViewer } = require('prismarine-viewer')
const puppeteer = require('puppeteer-core')
const { Vec3 } = require('vec3')

const host = process.env.MC_HOST || '127.0.0.1'
const port = Number(process.env.MC_PORT || '25571')
const username = process.env.MC_USER || 'SupraCraftVisual'
const readyFile = process.env.BOT_READY_FILE
const opReadyFile = process.env.OP_READY_FILE
const outputDir = process.env.VISUAL_OUTPUT_DIR
const resultFile = process.env.VISUAL_RESULT_FILE
const chromePath = process.env.CHROME_PATH

if (!readyFile || !opReadyFile || !outputDir || !resultFile || !chromePath) {
  throw new Error('required visual-probe environment is missing')
}

fs.mkdirSync(outputDir, { recursive: true })

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

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

let browser
let page
let viewerStarted = false
const browserConsole = []
const browserErrors = []

function pos () {
  const p = bot.entity.position
  return [Number(p.x.toFixed(3)), Number(p.y.toFixed(3)), Number(p.z.toFixed(3))]
}

async function teleportAndLook (xyz, target) {
  bot.chat('/tp @s ' + xyz.join(' '))
  await sleep(750)
  await bot.lookAt(new Vec3(target[0], target[1], target[2]), true)
  await sleep(750)
}

async function renderState () {
  return await page.evaluate(() => {
    const canvases = [...document.querySelectorAll('canvas')].map(c => ({
      width: c.width,
      height: c.height,
      clientWidth: c.clientWidth,
      clientHeight: c.clientHeight
    }))
    return {
      readyState: document.readyState,
      title: document.title,
      bodyText: document.body ? document.body.innerText.slice(0, 500) : '',
      canvases
    }
  })
}

async function shot (name) {
  const out = path.join(outputDir, name + '.png')
  await page.screenshot({ path: out })
  const stat = fs.statSync(out)
  const state = await renderState()
  if (stat.size < 5000) {
    throw new Error('screenshot unexpectedly small: ' + out + '; diagnostics=' + JSON.stringify({
      bytes: stat.size,
      state,
      browserConsole: browserConsole.slice(-30),
      browserErrors: browserErrors.slice(-30)
    }))
  }
  return { name, path: out, bytes: stat.size, bot_position: pos(), render_state: state }
}

async function main () {
  await new Promise((resolve, reject) => {
    bot.once('spawn', resolve)
    bot.once('error', reject)
    setTimeout(() => reject(new Error('spawn timeout')), 30000)
  })

  fs.writeFileSync(readyFile, JSON.stringify({ spawned: true, position: pos() }) + '\n')
  await waitFile(opReadyFile, 30000)

  mineflayerViewer(bot, { port: 3007, firstPerson: true, viewDistance: 5 })
  viewerStarted = true
  await sleep(2500)

  browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--enable-webgl', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--use-angle=swiftshader']
  })
  page = await browser.newPage()
  page.on('console', msg => browserConsole.push(msg.type() + ': ' + msg.text()))
  page.on('pageerror', err => browserErrors.push(String(err && err.stack ? err.stack : err)))
  await page.setViewport({ width: 960, height: 540, deviceScaleFactor: 1 })
  await page.goto('http://127.0.0.1:3007', { waitUntil: 'domcontentloaded', timeout: 30000 })
  await sleep(3500)

  const views = []
  await teleportAndLook([0, 72, 24], [0, 75, 0])
  views.push(await shot('01_approach'))

  const walkStart = pos()
  bot.setControlState('forward', true)
  await sleep(1800)
  bot.setControlState('forward', false)
  await sleep(500)
  const walkEnd = pos()
  views.push(await shot('02_after_walk'))

  await teleportAndLook([16, 75, 16], [0, 75, 0])
  views.push(await shot('03_three_quarter'))

  await teleportAndLook([0, 73, 1], [0, 74, 0])
  views.push(await shot('04_interior'))

  await teleportAndLook([0, 84, 42], [0, 75, 0])
  views.push(await shot('05_landmark_distance'))

  const dx = walkEnd[0] - walkStart[0]
  const dy = walkEnd[1] - walkStart[1]
  const dz = walkEnd[2] - walkStart[2]
  const walkDistance = Math.sqrt(dx * dx + dy * dy + dz * dz)

  const result = {
    schema: 'supracraft.named-place-visual-smoke/v0.1',
    minecraft: { edition: 'java', version: '26.3' },
    renderer: {
      name: 'prismarine-viewer',
      semantic_authority: false,
      client_world_source: 'mineflayer exact-26.3 connection',
      asset_fallback_policy: 'viewer closest-supported 26.x assets'
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
      schema: 'supracraft.named-place-visual-smoke/v0.1',
      result: 'error',
      error: String(err && err.stack ? err.stack : err),
      browser_console: browserConsole.slice(-50),
      browser_errors: browserErrors.slice(-50)
    }, null, 2) + '\n')
    process.exitCode = 1
  })
  .finally(async () => {
    try { bot.clearControlStates() } catch {}
    if (browser) await browser.close().catch(() => {})
    if (viewerStarted && bot.viewer) bot.viewer.close()
    bot.quit('done')
  })
