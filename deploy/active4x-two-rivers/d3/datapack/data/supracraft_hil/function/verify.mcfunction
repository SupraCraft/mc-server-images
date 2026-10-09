# D3 read-only fixed-coordinate reach probes: one marker each, no semantic changes.
execute if entity @a[name=TwoRiversHIL,x=2,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_obstruction_near:1} run say SUPRACRAFT_D3_DIAG_OBSTRUCT_NEAR
execute if entity @a[name=TwoRiversHIL,x=2,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_obstruction_near:1} run data modify storage supracraft:active4x hil.diagnostic_obstruction_near set value 1
execute if entity @a[name=TwoRiversHIL,x=6,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_damage_near:1} run say SUPRACRAFT_D3_DIAG_DAMAGE_NEAR
execute if entity @a[name=TwoRiversHIL,x=6,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_damage_near:1} run data modify storage supracraft:active4x hil.diagnostic_damage_near set value 1
scoreboard players set trade_count supracraft_hil 0
scoreboard players set build_count supracraft_hil 0
execute store result score trade_count supracraft_hil run data get block -6 70 12 Items[{Slot:0b}].count 1
execute store result score build_count supracraft_hil run data get block 0 70 12 Items[{Slot:0b}].count 1
execute if score trade_count supracraft_hil matches 2.. unless data storage supracraft:active4x hil{trade_done:1} run function supracraft_hil:complete_trade
execute if score build_count supracraft_hil matches 4.. unless data storage supracraft:active4x hil{build_help_done:1} run function supracraft_hil:complete_build
execute if block 2 70 16 minecraft:air unless data storage supracraft:active4x hil{obstruct_done:1} run function supracraft_hil:complete_obstruct
execute if block 6 70 16 minecraft:air unless data storage supracraft:active4x hil{damage_done:1} run function supracraft_hil:complete_damage
execute if data storage supracraft:active4x hil{trade_done:1,build_help_done:1,obstruct_done:1,damage_done:1} unless data storage supracraft:active4x hil{phase1_complete:1} run function supracraft_hil:complete_phase1
execute unless data storage supracraft:active4x hil{phase1_complete:1} run schedule function supracraft_hil:verify 10t replace
