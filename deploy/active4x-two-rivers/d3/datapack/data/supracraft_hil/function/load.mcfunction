execute unless data storage supracraft:active4x hil{initialized:1} run function supracraft_hil:setup
execute if data storage supracraft:active4x hil{initialized:1,phase1_complete:1} run say SUPRACRAFT_D3_STATE_SURVIVED_RESTART
execute if data storage supracraft:active4x hil{initialized:1} unless data storage supracraft:active4x hil{phase1_complete:1} run schedule function supracraft_hil:verify 10t replace
