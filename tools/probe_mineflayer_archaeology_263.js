// Barsoom buried-harbor: player-only traversal, container withdrawal and repair.
// No console teleport, /give, creative flight, fabricated inventory, or pathfinder mod.
// The server must run exactly vanilla Java 26.3 with barsoom_arch datapack.
'use strict'
const fs = require('fs')
const mineflayer = require('mineflayer')
const { Vec3 } = require('vec3')
const port = Number(process.env.MC_PORT || '25597')
const out = process.env.BARSOOM_ARCH_BOT_RESULT
if (!out || !Number.isInteger(port)) throw new Error('BARSOOM_ARCH_BOT_RESULT / MC_PORT required')
const bot = mineflayer.createBot({ host: '127.0.0.1', port, username: 'SupraArchProbe', auth: 'offline', version: '26.3' })
const rec = {schema:'barsoom.archaeology.physical-player/v0.1', version:'26.3', protocol:null,
  stages:[], points:[], actual_container_withdrawal:false, console_player_positioned:false,
  console_player_item_granted:false, stock_client_qualified:false, error:null}
function snap(label) {
  const p = bot.entity?.position
  if (p) rec.points.push({label, x:+p.x.toFixed(2), y:+p.y.toFixed(2), z:+p.z.toFixed(2)})
  fs.writeFileSync(out, JSON.stringify(rec, null, 2)+'\n')
}
const idle = async t => bot.waitForTicks(t)
function clear() { for (const s of ['forward','back','left','right','jump','sneak','sprint']) bot.setControlState(s,false) }
async function walkTo(x,z,limit=25,tol=1.0) {
  const deadline=Date.now()+limit*1000
  let stuck=0, old=null
  while (Date.now() < deadline) {
    const p=bot.entity.position, distance=Math.hypot(p.x-x,p.z-z)
    if (distance<tol) { clear(); return }
    await bot.lookAt(new Vec3(x,p.y+1.62,z),true)
    bot.setControlState('forward',true)
    if (old && Math.hypot(p.x-old.x,p.z-old.z)<0.05) stuck++; else stuck=0
    bot.setControlState('jump',stuck>10 && stuck<26)
    if (stuck>=45) {clear();throw new Error(`horizontal movement obstructed en route ${x},${z}; at ${p}`)}
    old=p.clone()
    await idle(3)
  }
  clear(); throw new Error(`horizontal waypoint timeout for ${x},${z}; at ${bot.entity.position}`)
}
async function descendLadder(base,limit=30) {
  const deadline=Date.now()+limit*1000
  let minY=Infinity,maxY=-Infinity
  clear()
  while(Date.now()<deadline) {
    const p=bot.entity.position
    minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y)
    if(p.y < base.y-9.5) {clear();rec.ladder_descent={minY,maxY,endY:p.y};return}
    // Pressing FORWARD against a ladder is the climbing actuator. Earlier
    // bot treatment combined forward+sneak and climbed two blocks above the
    // entrance instead of descending. Free-fall while contacting the ladder
    // lets vanilla apply its native limited downward velocity.
    bot.setControlState('forward',false)
    bot.setControlState('sneak',false)
    bot.setControlState('jump',false)
    await idle(3)
    if(Math.abs(p.x-(base.x+.5))>1.1 || Math.abs(p.z-(base.z+4.5))>1.8) {
      clear();rec.ladder_descent={minY,maxY,endY:p.y}
      throw new Error(`left ladder gallery at ${p}`)
    }
  }
  clear();rec.ladder_descent={minY,maxY,endY:bot.entity.position.y}
  throw new Error(`ladder descent timed out at ${bot.entity.position}`)
}
async function ascendLadder(base,limit=35) {
  const deadline=Date.now()+limit*1000
  while(Date.now()<deadline) {
    const p=bot.entity.position
    if(p.y > base.y-0.3) {clear();return}
    await bot.lookAt(new Vec3(base.x+.5,p.y+1.4,base.z+3.0),true)
    bot.setControlState('forward',true)
    bot.setControlState('jump',true)
    await idle(3)
  }
  clear();throw new Error(`ladder ascent timed out at ${bot.entity.position}`)
}
function waitUntil(pred,timeoutSec=12) {
  return new Promise(async (resolve,reject)=>{
    const deadline=Date.now()+timeoutSec*1000
    while(Date.now()<deadline){if(pred()){resolve();return} await idle(3)}
    reject(new Error('condition timeout'))
  })
}
let ended=false
function finish(code) {
  if(ended)return;ended=true;clear();rec.status=code===0?'PASS':'FAIL';snap('finish')
  try{bot.quit('bounded archaeology qualification')}catch{}
  setTimeout(()=>process.exit(code),400)
}
bot.on('error', e=>{rec.error=rec.error||String(e);snap('error')})
bot.on('kicked',e=>{rec.error=rec.error||'kicked: '+String(e);snap('kicked')})
bot.once('spawn', async ()=>{
  try {
    rec.protocol=bot.protocolVersion
    if(bot.version!=='26.3'||bot.protocolVersion!==777)throw new Error('incorrect 26.3 / 777 bot')
    // Let the game's tick-load function enable vanilla /trigger objectives.
    await idle(16)
    const p=bot.entity.position.clone()
    const prebuilt=process.env.BARSOOM_ARCH_PREBUILT==='1'
    const base=prebuilt?{x:0,y:83,z:0}:{x:Math.floor(p.x),y:Math.floor(p.y),z:Math.floor(p.z)}
    rec.base=base;snap('initial_spawn')
    if (prebuilt) {
      // Exact-version vanilla may move the player from setworldspawn onto
      // another nearby valid cell. Admit ONLY the separately built bridge,
      // with inspected solid footing, not an unbounded distance tolerance.
      const footing=bot.blockAt(new Vec3(Math.floor(p.x),Math.floor(p.y-1),Math.floor(p.z)))
      const withinPad=p.x>=52 && p.x<77 && p.z>=-12 && p.z<13 && Math.abs(p.y-83)<1.25
      if (!withinPad || !footing || footing.name!=='cut_sandstone') {
        throw new Error('natural spawn was not on qualified arrival walkway: '+p+
          '; footing='+(footing?.name||'unloaded'))
      }
      rec.stages.push('entered_pre_materialized_world_on_verified_walkway')
    } else {
      bot.chat('/trigger barsoom_arch.start set 1')
      rec.stages.push('player_trigger_built_site')
    }
    await waitUntil(()=>bot.blockAt(new Vec3(base.x+0,base.y+0,base.z+4))?.name==='ladder',14)
    snap('site_loaded')

    // Walk along a *materialized* surface bridge from the external spawn pad.
    // No teleport or server-forced relocation of the actual player.
    if (prebuilt) {
      await walkTo(base.x+48.5,base.z+1.5,30)
      await walkTo(base.x+33.5,base.z+1.5,30)
      await walkTo(base.x+18.5,base.z+1.5,30)
      await walkTo(base.x+3.5,base.z+1.5,30)
      rec.stages.push('walked_from_natural_spawn_to_quay');snap('quay_arrival')
    }
    // Stay on the east-hand surface quay until next to the ladder. Walking
    // diagonally towards z+5 was observed to drop the player ten blocks into
    // the unguarded shaft on exact vanilla 26.3 (preserved first failure).
    await walkTo(base.x+2.5,base.z+1.5,14);snap('east_quay_approach')
    await walkTo(base.x+2.5,base.z+4.5,14);snap('shaft_east_edge')
    if (bot.entity.position.y < base.y-2) throw new Error('unsafe drop before ladder entry: '+bot.entity.position)
    await walkTo(base.x+.5,base.z+4.5,10,.35)
    rec.stages.push('walked_to_ladder_entrance');snap('ladder_entrance')
    await descendLadder(base,35)
    rec.stages.push('physically_descended_ladder');snap('bottom_of_shaft')
    await walkTo(base.x+.5,base.z+12.5,20)
    await walkTo(base.x+3.0,base.z+16.0,20)
    const chestPos=new Vec3(base.x+4,base.y-10,base.z+17)
    const distance=bot.entity.position.distanceTo(chestPos.offset(.5,.5,.5))
    if(distance>4.2)throw new Error('cannot reach chest from player position '+distance)
    const chest=bot.blockAt(chestPos)
    if(!chest||chest.name!=='chest')throw new Error('archive chest absent from client world cache')
    rec.stages.push('walked_to_buried_chest');snap('chest_reached')
    const window=await bot.openContainer(chest)
    try {
      const contents=typeof window.containerItems==='function'?window.containerItems():window.items()
      const seal=contents.find(x=>x.name==='heart_of_the_sea')
      if(!seal)throw new Error('sea seal absent from chest')
      await window.withdraw(seal.type,null,1)
      await idle(6)
    } finally{window.close()}
    if(!bot.inventory.items().some(x=>x.name==='heart_of_the_sea'))throw new Error('seal not in player inventory')
    rec.actual_container_withdrawal=true
    rec.stages.push('actual_chest_transaction_and_seal_recovery');snap('recovered_seal')

    // Return through the same real tunnel and climb the ladder.
    await walkTo(base.x+.5,base.z+11.0,25)
    await walkTo(base.x+.5,base.z+4.5,25,.32)
    await ascendLadder(base,40)
    rec.stages.push('physically_ascended_ladder');snap('surface_return')
    // On leaving the ladder, move EAST onto the existing quay deck first.
    // Walking south into z+5.5 re-entered the open shaft on native 26.3.
    await walkTo(base.x+2.5,base.z+4.5,12)
    if (bot.entity.position.y < base.y-2) throw new Error('unsafe return from ladder: '+bot.entity.position)
    rec.stages.push('safely_exited_ladder_to_east_quay');snap('east_quay_return')
    await walkTo(base.x+2.5,base.z+1.5,12)
    await walkTo(base.x+1.5,base.z+.5,15)
    rec.stages.push('walked_back_to_well');snap('well_reached')
    bot.chat('/trigger barsoom_arch.restore set 1')
    await idle(14)
    if(bot.inventory.items().some(x=>x.name==='heart_of_the_sea'))throw new Error('restoration did not consume sea seal')
    rec.stages.push('player_trigger_restored_well_and_consumed_seal');snap('restored')
    // Keep the player online while the independent server checks inventory.
    // The authority is Minecraft's live /execute if items, not bot inference.
    const liveReady=process.env.BARSOOM_ARCH_LIVE_READY
    const liveAck=process.env.BARSOOM_ARCH_LIVE_ACK
    if (!liveReady||!liveAck)throw new Error('live inventory oracle synchronization paths unavailable')
    fs.writeFileSync(liveReady,'awaiting-native-oracle\n')
    await waitUntil(()=>fs.existsSync(liveAck),25)
    rec.stages.push('native_server_confirmed_seal_absence_while_connected')
    finish(0)
  }catch(e){rec.error=String(e&&e.stack?e.stack:e);finish(1)}
})
setTimeout(()=>{rec.error=rec.error||'physical-player timeout';finish(2)},160000)
