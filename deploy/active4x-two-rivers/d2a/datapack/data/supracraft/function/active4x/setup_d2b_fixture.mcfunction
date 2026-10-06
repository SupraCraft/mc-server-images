fill -12 69 -3 12 69 3 minecraft:stone
setblock -10 70 0 minecraft:barrel
setblock 10 70 0 minecraft:barrel
item replace block -10 70 0 container.0 with minecraft:wheat 4
data modify storage supracraft:active4x d2b_fixture set value {initialized:1,version:"d2b"}
say SUPRACRAFT_D2B_FIXTURE_READY
