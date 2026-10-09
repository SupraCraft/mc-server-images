# D3 read-only fixed-coordinate reach probes: one marker each, no semantic changes.
execute if entity @a[name=TwoRiversHIL,x=2,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_obstruction_near:1} run say SUPRACRAFT_D3_DIAG_OBSTRUCT_NEAR
execute if entity @a[name=TwoRiversHIL,x=2,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_obstruction_near:1} run data modify storage supracraft:active4x hil.diagnostic_obstruction_near set value 1
execute if entity @a[name=TwoRiversHIL,x=6,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_damage_near:1} run say SUPRACRAFT_D3_DIAG_DAMAGE_NEAR
execute if entity @a[name=TwoRiversHIL,x=6,y=70,z=15,distance=..3] unless data storage supracraft:active4x hil{diagnostic_damage_near:1} run data modify storage supracraft:active4x hil.diagnostic_damage_near set value 1
# Fixed-target official-server held-tool witnesses, only while in survival and
# within 2 blocks of the obstruction. Never change any equipment or game rules.
execute positioned 2 70 15 as @a[name=TwoRiversHIL,distance=..2,gamemode=survival] if items entity @s weapon.mainhand minecraft:diamond_pickaxe unless data storage supracraft:active4x hil{diagnostic_tool_present:1} run say SUPRACRAFT_D3_DIAG_SERVER_TOOL_PRESENT
execute positioned 2 70 15 as @a[name=TwoRiversHIL,distance=..2,gamemode=survival] if items entity @s weapon.mainhand minecraft:diamond_pickaxe unless data storage supracraft:active4x hil{diagnostic_tool_present:1} run data modify storage supracraft:active4x hil.diagnostic_tool_present set value 1
execute positioned 2 70 15 as @a[name=TwoRiversHIL,distance=..2,gamemode=survival] unless items entity @s weapon.mainhand minecraft:diamond_pickaxe unless data storage supracraft:active4x hil{diagnostic_tool_absent:1} run say SUPRACRAFT_D3_DIAG_SERVER_TOOL_ABSENT
execute positioned 2 70 15 as @a[name=TwoRiversHIL,distance=..2,gamemode=survival] unless items entity @s weapon.mainhand minecraft:diamond_pickaxe unless data storage supracraft:active4x hil{diagnostic_tool_absent:1} run data modify storage supracraft:active4x hil.diagnostic_tool_absent set value 1
# Independent server-world placement control; never substitutes for mining gates.
execute if block 4 70 13 minecraft:stone unless data storage supracraft:active4x hil{diagnostic_place_done:1} run say SUPRACRAFT_D3_DIAG_PLACE_COMPLETE
execute if block 4 70 13 minecraft:stone unless data storage supracraft:active4x hil{diagnostic_place_done:1} run data modify storage supracraft:active4x hil.diagnostic_place_done set value 1
# Read-only acceptance marker for the diagnostic fast-break control.
execute if block 3 70 16 minecraft:air unless data storage supracraft:active4x hil{diagnostic_fastbreak_done:1} run say SUPRACRAFT_D3_DIAG_FASTBREAK_COMPLETE
execute if block 3 70 16 minecraft:air unless data storage supracraft:active4x hil{diagnostic_fastbreak_done:1} run data modify storage supracraft:active4x hil.diagnostic_fastbreak_done set value 1
# D3 read-only TPS witness: scheduled every ten official server ticks.
scoreboard players add diagnostic_clock supracraft_hil 10
execute if score diagnostic_clock supracraft_hil matches 200.. unless data storage supracraft:active4x hil{diagnostic_clock_200:1} run say SUPRACRAFT_D3_DIAG_CLOCK_200
execute if score diagnostic_clock supracraft_hil matches 200.. unless data storage supracraft:active4x hil{diagnostic_clock_200:1} run data modify storage supracraft:active4x hil.diagnostic_clock_200 set value 1
execute if score diagnostic_clock supracraft_hil matches 400.. unless data storage supracraft:active4x hil{diagnostic_clock_400:1} run say SUPRACRAFT_D3_DIAG_CLOCK_400
execute if score diagnostic_clock supracraft_hil matches 400.. unless data storage supracraft:active4x hil{diagnostic_clock_400:1} run data modify storage supracraft:active4x hil.diagnostic_clock_400 set value 1
execute if entity @a[name=TwoRiversHIL,gamemode=survival] unless data storage supracraft:active4x hil{diagnostic_server_survival:1} run say SUPRACRAFT_D3_DIAG_SERVER_SURVIVAL
execute if entity @a[name=TwoRiversHIL,gamemode=survival] unless data storage supracraft:active4x hil{diagnostic_server_survival:1} run data modify storage supracraft:active4x hil.diagnostic_server_survival set value 1
# Rehearsal-only diagnostic control for fixed fake player and glass; never
# accept creative-mode block breaking as survival/HIL qualification.
execute positioned 3 70 15 if entity @a[name=TwoRiversHIL,distance=..2,gamemode=survival] if block 3 70 16 minecraft:glass unless data storage supracraft:active4x hil{diagnostic_creative_started:1} run gamemode creative @a[name=TwoRiversHIL]
execute positioned 3 70 15 if entity @a[name=TwoRiversHIL,distance=..2,gamemode=creative] if block 3 70 16 minecraft:glass unless data storage supracraft:active4x hil{diagnostic_creative_started:1} run data modify storage supracraft:active4x hil.diagnostic_creative_started set value 1
execute if block 3 70 16 minecraft:air if data storage supracraft:active4x hil{diagnostic_creative_started:1} unless data storage supracraft:active4x hil{diagnostic_survival_restored:1} run gamemode survival @a[name=TwoRiversHIL]
execute if block 3 70 16 minecraft:air if data storage supracraft:active4x hil{diagnostic_creative_started:1} unless data storage supracraft:active4x hil{diagnostic_survival_restored:1} run data modify storage supracraft:active4x hil.diagnostic_survival_restored set value 1
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
