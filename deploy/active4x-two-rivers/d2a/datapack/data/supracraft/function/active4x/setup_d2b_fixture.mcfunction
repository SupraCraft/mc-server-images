fill -16 69 -8 16 69 8 minecraft:stone
setworldspawn 0 70 0
setblock -10 70 0 minecraft:barrel
setblock 10 70 0 minecraft:barrel
item replace block -10 70 0 container.0 with minecraft:wheat 4
execute if block -10 70 0 minecraft:barrel if block 10 70 0 minecraft:barrel run data modify storage supracraft:active4x d2b_fixture set value {initialized:1,version:"d2b"}
execute if data storage supracraft:active4x d2b_fixture{initialized:1} run say SUPRACRAFT_D2B_FIXTURE_READY
