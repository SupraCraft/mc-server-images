fill -32 69 -32 32 69 32 minecraft:stone
setworldspawn 0 70 0
setblock -10 70 0 minecraft:barrel
setblock 10 70 0 minecraft:barrel
item replace block -10 70 0 container.0 with minecraft:wheat 4
data modify storage supracraft:active4x d2b_fixture set value {initialized:1,version:"d2b"}
execute if block -10 70 0 minecraft:barrel if block 10 70 0 minecraft:barrel run say SUPRACRAFT_D2B_FIXTURE_READY
