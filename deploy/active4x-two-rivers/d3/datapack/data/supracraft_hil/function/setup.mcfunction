forceload add -16 0 16 32
gamerule minecraft:respawn_radius 0
gamerule minecraft:spawn_monsters false
fill -10 69 8 10 69 20 minecraft:stone
setworldspawn 0 70 10
setblock -8 70 12 minecraft:barrel
item replace block -8 70 12 container.0 with minecraft:wheat 2
item replace block -8 70 12 container.1 with minecraft:bricks 4
# Bounded vanilla mining-tool diagnostic; retains original marker blocks and server oracle.
item replace block -8 70 12 container.2 with minecraft:diamond_pickaxe 1
setblock -6 70 12 minecraft:barrel
setblock -4 70 12 minecraft:barrel
setblock 0 70 12 minecraft:barrel
setblock 3 70 16 minecraft:glass
setblock 2 70 16 minecraft:red_concrete
setblock 6 70 16 minecraft:cobblestone
fill -1 70 18 1 72 18 minecraft:air
scoreboard objectives add supracraft_hil dummy
data modify storage supracraft:active4x hil set value {initialized:1,trade_done:0,build_help_done:0,obstruct_done:0,damage_done:0,phase1_complete:0}
say SUPRACRAFT_D3_HIL_READY
schedule function supracraft_hil:verify 10t replace
forceload remove -16 0 16 32
