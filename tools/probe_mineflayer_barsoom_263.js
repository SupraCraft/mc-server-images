// Bounded Barsoom offline-player command probe, uses existing pinned OP4E 26.3 runtime.
// Receives only /trigger commands from an isolated temporary-world controller.
const fs = require('fs')
const mineflayer = require('mineflayer')
const root = process.env.BARSOOM_PROBE_ROOT
const port = Number(process.env.MC_PORT || '25593')
if (!root || !Number.isInteger(port)) throw new Error('BARSOOM_PROBE_ROOT and MC_PORT required')
const file = name => `${root}/${name}`
const bot = mineflayer.createBot({host: '127.0.0.1',port,username:'SupraCraftProbe',auth:'offline',version:'26.3'})
let connected = false
let error = null
const milestones = {}
function status () {
  fs.writeFileSync(file('bot-status.json'), JSON.stringify({
    schema:'supracraft-barsoom-player/v0.1',connected,error,milestones,
    minecraft_version:bot.version, protocol_version:bot.protocolVersion,
    position:bot.entity?.position?.toArray?.() || null
  })+'\n')
}
bot.on('connect',()=>{milestones.connect=Date.now();status()})
bot.on('login',()=>{milestones.login=Date.now();status()})
bot.on('error',e=>{error=String(e);status()})
bot.on('kicked',e=>{error='kicked: '+JSON.stringify(e);status()})
bot.on('end',r=>{connected=false;status()})
bot.once('spawn',()=>{connected=true;milestones.spawn=Date.now();status();fs.writeFileSync(file('bot.ready'),'ready\n')})
let last=0
const poll=setInterval(()=>{
  if (!connected) return
  const reqFile=file('bot-request.json')
  if (!fs.existsSync(reqFile)) return
  try {
    const req=JSON.parse(fs.readFileSync(reqFile,'utf8'))
    fs.unlinkSync(reqFile)
    if (!Number.isInteger(req.id) || req.id <= last || !/^\/trigger barsoom\.(start|guide|repair) set 1$/.test(req.command)) throw new Error('unadmitted command')
    last=req.id
    bot.chat(req.command)
    fs.writeFileSync(file('bot-ack.json'), JSON.stringify({id:req.id,command:req.command,at:Date.now()})+'\n')
  } catch (e) {error='command: '+String(e);status()}
},125)
setTimeout(()=>{if (connected) bot.quit('Barsoom disposable probe completed');clearInterval(poll);status();process.exit(error?1:0)},210000)
